from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Jsonb

from ..services.topic_structure import STRUCTURE_VERSION, source_hash, materialize, validate_response, apply_consolidation
from ..services.topic_structure import CONSOLIDATION_BATCH, CONSOLIDATION_PROFILE


class TopicStructureRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def ready_current(self, item: dict[str, Any]) -> dict[str, Any] | None:
        result = self.current(item)
        return result if result and result['topic_structure'].get('consolidation_status') == 'COMPLETED' else None

    def progress(self, item: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT s.status, count(b.id) FILTER (WHERE b.batch_index<100000 AND b.status='READY'), "
            "count(b.id) FILTER (WHERE b.batch_index=%s AND b.status='READY'), "
            "count(b.id) FILTER (WHERE b.batch_index=%s AND b.status='FAILED' AND b.request_snapshot->>'request_profile'=%s) "
            "FROM meeting_topic_structures s LEFT JOIN meeting_topic_structure_batches b ON b.structure_id=s.id "
            "WHERE s.meeting_brief_id=%s AND s.source_hash=%s AND s.version=%s GROUP BY s.id",
            (CONSOLIDATION_BATCH, CONSOLIDATION_BATCH, CONSOLIDATION_PROFILE, item['brief_id'], source_hash(item['brief']), STRUCTURE_VERSION),
        ).fetchone()
        if not row:
            return {'status': 'PENDING', 'completed_batches': 0}
        state, batches, final, failed = row
        if state == 'READY':
            structure = self.connection.execute(
                'SELECT id FROM meeting_topic_structures WHERE meeting_brief_id=%s AND source_hash=%s AND version=%s',
                (item['brief_id'], source_hash(item['brief']), STRUCTURE_VERSION),
            ).fetchone()
            from ..services.structure_retry import failed_batch_status
            history = self.batches(structure[0]) if structure else []
            retry_status = failed_batch_status(history)
            if retry_status:
                return {'status': retry_status, 'completed_batches': batches,
                        'consolidation_attempts': failed + final}
            # A repaired source batch invalidates consolidation over the old subset.
            from ..services.topic_structure import consolidation_input
            facets = [f for h in history if h['index'] < 100000 and h['status'] == 'READY'
                      for f in validate_response(h['response'], h['request']['atoms'])]
            issues = consolidation_input(facets)
            matching = [h for h in history if h['index'] == CONSOLIDATION_BATCH
                        and h['request'].get('issues') == issues
                        and h['request'].get('request_profile') == CONSOLIDATION_PROFILE]
            final = 0
            for h in history:
                if h['index'] != CONSOLIDATION_BATCH or h['status'] != 'READY':
                    continue
                try:
                    apply_consolidation(facets, h['response'])
                except ValueError:
                    continue
                final += 1
            failed = sum(h['status'] == 'FAILED' for h in matching)
            if not final:
                from ..services.topic_structure import preserve_unmergeable_issues
                for h in matching:
                    if h.get('error') not in {'INVALID_CONSOLIDATION_ID', 'CYCLIC_CONSOLIDATION'}:
                        continue
                    try:
                        apply_consolidation(facets, preserve_unmergeable_issues(facets, h['response']))
                    except ValueError:
                        continue
                    return {'status': 'PROCESSING', 'completed_batches': batches, 'consolidation_attempts': failed}
        return {'status': 'COMPLETED' if final else 'REVIEW_REQUIRED' if state == 'FAILED' or failed >= 3 else 'PROCESSING',
                'completed_batches': batches, 'consolidation_attempts': failed + final}

    def current(self, item: dict[str, Any]) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT id,source_snapshot,result FROM meeting_topic_structures WHERE meeting_brief_id=%s "
            "AND source_hash=%s AND version=%s AND status='READY'",
            (item['brief_id'], source_hash(item['brief']), STRUCTURE_VERSION),
        ).fetchone()
        if not row:
            return None
        structure_id, snapshot, result = row
        # Read projection upgrade does not overwrite the original analysis or model responses.
        facets = []
        responses = self.connection.execute(
            "SELECT batch_index,request_snapshot,response FROM meeting_topic_structure_batches "
            "WHERE structure_id=%s AND status='READY' ORDER BY batch_index,attempt", (structure_id,),
        ).fetchall()
        consolidated = False
        final_responses = []
        for index, request, response in responses:
            if index == CONSOLIDATION_BATCH:
                final_responses.append(response)
            elif index < 100000:
                facets.extend(validate_response(response, request['atoms']))
        base_facets = facets
        for response in final_responses:
            try:
                facets = apply_consolidation(base_facets, response)
                consolidated = True
            except ValueError:
                # An earlier consolidation may precede a repaired source batch.
                continue
        covered = {f['atom_id'] for f in base_facets}
        rejected = [{'atom_id': a['id'], 'evidence_id': a['evidence_id'], 'reason': 'MODEL_VALIDATION_REVIEW'}
                    for a in snapshot['atoms'] if a['id'] not in covered]
        from ..services.structure_review import apply_reviews as apply_structure_reviews, annotate_review_state, DOCUMENT_PROFILE, VERIFY_PROFILE
        facets, reviewed = apply_structure_reviews(facets, responses)
        projected = materialize(item['brief'], snapshot, facets, rejected, str(structure_id))
        reviewed_documents = {a['id'] for _, request, _ in responses
                              if request.get('profile') == DOCUMENT_PROFILE for a in request['atoms']}
        verified_atoms = {a['id'] for _, request, _ in responses
                          if request.get('profile') == VERIFY_PROFILE for a in request['atoms']}
        annotate_review_state(projected, reviewed, reviewed_documents, verified_atoms)
        projected['topic_structure']['consolidation_status'] = 'COMPLETED' if consolidated else 'PENDING'
        from ..services.meeting_topic_groups import _ontology_match, TARGET_ONTOLOGY
        from ..services.ontology_source_context import attach_ontology_source_context
        from ..services.ontology_semantic import apply_reviews
        pending_ids = {t['id'] for t in projected.get('topics', []) if not _ontology_match(t)}
        projected = attach_ontology_source_context(projected, snapshot, pending_ids)
        return apply_reviews(projected, responses, TARGET_ONTOLOGY)

    def start(self, item: dict[str, Any], snapshot: dict[str, Any]) -> Any:
        return self.connection.execute(
            "INSERT INTO meeting_topic_structures "
            "(id,meeting_brief_id,source_hash,version,status,source_snapshot) "
            "VALUES (%s,%s,%s,%s,'PROCESSING',%s) "
            "ON CONFLICT(meeting_brief_id,source_hash,version) DO UPDATE "
            "SET updated_at=now() RETURNING id",
            (uuid.uuid4(), item['brief_id'], source_hash(item['brief']),
             STRUCTURE_VERSION, Jsonb(snapshot)),
        ).fetchone()[0]

    def snapshot(self, structure_id: Any) -> dict[str, Any]:
        return self.connection.execute(
            "SELECT source_snapshot FROM meeting_topic_structures WHERE id=%s",
            (structure_id,),
        ).fetchone()[0]

    def batches(self, structure_id: Any) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT batch_index,attempt,status,response,error_code,request_snapshot,created_at FROM "
            "meeting_topic_structure_batches WHERE structure_id=%s ORDER BY batch_index,attempt",
            (structure_id,),
        ).fetchall()
        return [dict(zip(('index','attempt','status','response','error','request','created_at'), r, strict=True)) for r in rows]

    def record(self, structure_id: Any, index: int, attempt: int, request: dict[str, Any],
               response: dict[str, Any], metadata: dict[str, Any], error: str | None) -> None:
        self.connection.execute(
            "INSERT INTO meeting_topic_structure_batches "
            "(id,structure_id,batch_index,attempt,status,request_snapshot,response,usage_metadata,error_code) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uuid.uuid4(), structure_id, index, attempt, 'FAILED' if error else 'READY',
             Jsonb(request), Jsonb(response), Jsonb(metadata), error),
        )

    def finish(self, structure_id: Any, result: dict[str, Any]) -> None:
        self.connection.execute(
            "UPDATE meeting_topic_structures SET result=%s,status='READY',updated_at=now() "
            "WHERE id=%s AND status <> 'READY'", (Jsonb(result), structure_id),
        )

    def mark_review_required(self, structure_id: Any) -> None:
        self.connection.execute(
            "UPDATE meeting_topic_structures SET status='FAILED',updated_at=now() WHERE id=%s",
            (structure_id,),
        )
