from __future__ import annotations

from typing import Any

from ..services.specific_policy_issues import build_specific_policy_issues


class PolicyIssueRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def specific_issue_flow(self) -> dict[str, Any]:
        rows = self.connection.execute(
            """
            WITH latest_briefs AS (
                SELECT DISTINCT ON (brief.broadcast_id)
                       brief.id, brief.broadcast_id, brief.brief
                FROM meeting_briefs brief
                ORDER BY brief.broadcast_id, brief.source_last_event_cursor DESC,
                         brief.generated_at DESC, brief.id DESC
            )
            SELECT latest.broadcast_id, broadcast.title, broadcast.committee_name,
                   broadcast.institution,
                   COALESCE(broadcast.ended_at, broadcast.last_seen_at, broadcast.detected_at),
                   COALESCE(integration.integrated_brief, latest.brief),
                   CASE WHEN integration.id IS NULL THEN 'PROVISIONAL' ELSE 'OFFICIAL_INTEGRATED' END
            FROM latest_briefs latest
            JOIN live_broadcasts broadcast ON broadcast.id = latest.broadcast_id
            LEFT JOIN LATERAL (
                SELECT candidate.id, candidate.integrated_brief
                FROM meeting_official_integrations candidate
                WHERE candidate.meeting_brief_id = latest.id
                  AND candidate.status = 'READY'
                ORDER BY candidate.generated_at DESC, candidate.id DESC
                LIMIT 1
            ) integration ON true
            WHERE broadcast.lifecycle_status = 'ENDED'
            ORDER BY COALESCE(broadcast.ended_at, broadcast.last_seen_at) DESC
            """
        ).fetchall()
        records = [
            {
                "broadcast_id": broadcast_id,
                "meeting_title": title,
                "committee_name": committee_name,
                "institution": institution,
                "meeting_date": meeting_date,
                "brief": brief,
                "authority_status": authority_status,
            }
            for (
                broadcast_id, title, committee_name, institution,
                meeting_date, brief, authority_status,
            ) in rows
        ]
        bill_rows = self.connection.execute(
            """
            SELECT link.utterance_id::text, bill.bill_id, agenda.agenda_name,
                   version.bill_number, version.bill_name,
                   version.process_stage_code, version.committee_result,
                   version.plenary_result,
                   COALESCE(version.official_url, bill.official_url),
                   version.proposer_kind, version.proposer_name,
                   version.proposal_date, version.committee_name,
                   version.committee_process_date,
                   version.plenary_resolution_date, version.pass_classification,
                   version.created_at, link.match_method
            FROM official_utterance_agenda_links link
            JOIN agenda_items agenda ON agenda.id = link.agenda_item_id
            JOIN bills bill ON bill.id = agenda.bill_id
            LEFT JOIN LATERAL (
                SELECT bill_number, bill_name, process_stage_code,
                       committee_result, plenary_result, official_url,
                       proposer_kind, proposer_name, proposal_date, committee_name,
                       committee_process_date, plenary_resolution_date,
                       pass_classification, created_at
                FROM bill_versions
                WHERE bill_id = bill.id
                ORDER BY created_at DESC, id DESC LIMIT 1
            ) version ON true
            WHERE link.reconciliation_status = 'MATCHED'
              AND link.match_method IN (
                    'EXACT_ITEM_REF_AGENDA_PREFIX',
                    'EXPLICIT_SPOKEN_ITEM_AGENDA_PREFIX'
                  )
            """
        ).fetchall()
        bill_links: dict[str, list[dict[str, Any]]] = {}
        for row in bill_rows:
            evidence_id = row[0]
            bill_links.setdefault(evidence_id, []).append({
                "bill_id": row[1], "agenda_name": row[2],
                "bill_number": row[3], "bill_name": row[4],
                "process_stage_code": row[5], "committee_result": row[6],
                "plenary_result": row[7], "official_url": row[8],
                "proposer_kind": row[9], "proposer_name": row[10],
                "proposal_date": row[11], "committee_name": row[12],
                "committee_process_date": row[13],
                "plenary_resolution_date": row[14],
                "pass_classification": row[15], "status_as_of": row[16],
                "match_method": row[17],
            })
        return build_specific_policy_issues(records, bill_links)
