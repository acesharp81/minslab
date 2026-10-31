"""Resume official payload deduplication after migration 0065 and verified backup.

Each bounded transaction locks its source rows and verifies every original JSON
field before committing. IDs, document versions, source locations and source
files stay intact. No model calls. A session lock prevents concurrent runners.
"""
from __future__ import annotations

import argparse
import json

from ..config import Settings
from ..db.connection import connect

JOBS = {
    'utterance_text': {
        'table': 'official_utterance_rows', 'column': 'text',
        'insert': "INSERT INTO official_text_payloads SELECT DISTINCT encode(sha256(convert_to(r.text,'UTF8')),'hex'),r.text FROM official_utterance_rows r JOIN storage_batch_ids b ON r.ctid=b.row_tid WHERE true ON CONFLICT DO NOTHING",
        'update': "UPDATE official_utterance_rows r SET text_key=encode(sha256(convert_to(r.text,'UTF8')),'hex'),text=NULL FROM storage_batch_ids b WHERE r.ctid=b.row_tid RETURNING r.id,r.ctid",
        'projection': "SELECT r.id,r.document_id,r.sequence_number,r.source_speaker_id,r.source_span_id,r.agenda_item_ref,r.speaker_name,r.speaker_role,COALESCE(r.text,p.text) AS text,r.text_hash,r.source_locator,r.created_at FROM storage_batch_ids b JOIN official_utterance_rows r ON r.ctid=b.row_tid LEFT JOIN official_text_payloads p USING(text_key)",
    },
    'annotation_payload': {
        'table': 'official_annotation_rows', 'column': 'evidence_keywords',
        'insert': "INSERT INTO official_annotation_payloads SELECT DISTINCT encode(sha256(convert_to(jsonb_build_array(r.evidence_keywords,r.topic_links,r.ministry_links)::text,'UTF8')),'hex'),r.evidence_keywords,r.topic_links,r.ministry_links FROM official_annotation_rows r JOIN storage_batch_ids b ON r.ctid=b.row_tid WHERE true ON CONFLICT DO NOTHING",
        'update': "UPDATE official_annotation_rows r SET payload_key=encode(sha256(convert_to(jsonb_build_array(r.evidence_keywords,r.topic_links,r.ministry_links)::text,'UTF8')),'hex'),evidence_keywords=NULL,topic_links=NULL,ministry_links=NULL FROM storage_batch_ids b WHERE r.ctid=b.row_tid RETURNING r.id,r.ctid",
        'projection': "SELECT r.id,r.utterance_id,r.generator_version,r.classification_method,r.topics,r.ministries,r.source_committee,r.authority_status,r.review_status,r.generated_at,r.evidence_text_hash,r.utterance_kind,COALESCE(r.evidence_keywords,p.evidence_keywords) AS evidence_keywords,COALESCE(r.topic_links,p.topic_links) AS topic_links,COALESCE(r.ministry_links,p.ministry_links) AS ministry_links FROM storage_batch_ids b JOIN official_annotation_rows r ON r.ctid=b.row_tid LEFT JOIN official_annotation_payloads p USING(payload_key)",
    },
}


def normalize(*, blocks: int = 2048, database_url: str | None = None) -> None:
    url = database_url or Settings().database_url
    with connect(url) as lease:
        if not lease.execute("SELECT pg_try_advisory_lock(hashtext('official-storage-normalization'))").fetchone()[0]:
            raise RuntimeError('NORMALIZATION_ALREADY_RUNNING')
        lease.commit()  # Retain session lock without keeping an old MVCC snapshot.
        try:
            for job, spec in JOBS.items():
                table, column = spec['table'], spec['column']
                with connect(url) as c:
                    c.execute('INSERT INTO storage_normalization_jobs(job) VALUES(%s) ON CONFLICT DO NOTHING', (job,))
                    stop = c.execute('SELECT (pg_relation_size(%s)+8191)/8192', (table,)).fetchone()[0]
                while True:
                    with connect(url) as c:
                        c.execute("SET LOCAL lock_timeout='3s'")
                        c.execute("SET LOCAL statement_timeout='180s'")
                        c.execute("SET LOCAL work_mem='64MB'")
                        cursor, total, status = c.execute('SELECT cursor_block,verified_rows,status FROM storage_normalization_jobs WHERE job=%s FOR UPDATE', (job,)).fetchone()
                        if status == 'COMPLETED':
                            break
                        if cursor >= stop:
                            left = c.execute(f'SELECT count(*) FROM {table} WHERE {column} IS NOT NULL').fetchone()[0]
                            if left:
                                raise RuntimeError(f'UNPROCESSED_ROWS:{job}:{left}')
                            c.execute("UPDATE storage_normalization_jobs SET status='COMPLETED',updated_at=now() WHERE job=%s", (job,))
                            print(json.dumps({'job': job, 'status': 'COMPLETED', 'verified_rows': total}), flush=True)
                            break
                        end = min(stop, cursor + blocks)
                        c.execute('CREATE TEMP TABLE storage_batch_ids(id uuid PRIMARY KEY,row_tid tid) ON COMMIT DROP')
                        # Page-range scans keep IO sequential; the locks make CTIDs
                        # stable until our update. Save new CTIDs from RETURNING.
                        c.execute(f'INSERT INTO storage_batch_ids SELECT id,ctid FROM {table} WHERE ctid >= %s::tid AND ctid < %s::tid AND {column} IS NOT NULL FOR UPDATE', (f'({cursor},0)', f'({end},0)'))
                        c.execute('ANALYZE storage_batch_ids')
                        c.execute('SET LOCAL enable_hashjoin=off')
                        c.execute('SET LOCAL enable_mergejoin=off')

                        def fingerprint():
                            return c.execute("SELECT count(*),md5(string_agg(md5(row_to_json(v)::text),'' ORDER BY v.id)) FROM (" + spec['projection'] + ') v').fetchone()

                        before = fingerprint()
                        if before[0]:
                            c.execute(spec['insert'])
                            c.execute('WITH changed AS (' + spec['update'] + ') UPDATE storage_batch_ids b SET row_tid=changed.ctid FROM changed WHERE b.id=changed.id')
                        after = fingerprint()
                        if before != after:
                            raise RuntimeError(f'ROUNDTRIP_MISMATCH:{job}:{cursor}')
                        c.execute('INSERT INTO storage_normalization_batches(job,block_start,block_end,row_count,before_hash,after_hash) VALUES(%s,%s,%s,%s,%s,%s)', (job, cursor, end, before[0], before[1], after[1]))
                        c.execute("UPDATE storage_normalization_jobs SET cursor_block=%s,completed_rows=completed_rows+%s,verified_rows=verified_rows+%s,status='RUNNING',updated_at=now() WHERE job=%s", (end, before[0], before[0], job))
                    print(json.dumps({'job': job, 'blocks_done': end, 'blocks_total': stop, 'verified_rows': total + before[0]}), flush=True)
        finally:
            lease.execute("SELECT pg_advisory_unlock(hashtext('official-storage-normalization'))")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--blocks', type=int, default=2048)
    args = parser.parse_args()
    if not 1 <= args.blocks <= 16384:
        raise ValueError('blocks must be between 1 and 16384')
    normalize(blocks=args.blocks)
