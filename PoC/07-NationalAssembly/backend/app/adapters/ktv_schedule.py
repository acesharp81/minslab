from __future__ import annotations

import hashlib
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .national_assembly.base import AdapterError, SourcePayload
from .national_assembly.schedule import ScheduleSourceRecord


KTV_BROADCAST_SCHEDULE_URL = "https://www.ktv.go.kr/broadChart/tv"


class KtvScheduleAdapter:
    source_key = "ktv_broadcast_schedule"
    parser_version = "ktv-broadcast-schedule/1.0.0"

    def parse(
        self, payload: SourcePayload, *, scheduled_date: date,
    ) -> list[ScheduleSourceRecord]:
        if payload.source_key != self.source_key:
            raise AdapterError(f"unexpected source key: {payload.source_key}")
        try:
            soup = BeautifulSoup(payload.content, "html.parser")
        except Exception as exc:
            raise AdapterError("invalid KTV broadcast schedule HTML") from exc

        records: list[ScheduleSourceRecord] = []
        for row in soup.select("tr"):
            time_node = row.select_one("th.date")
            title_node = row.select_one("td.tit .channel-cont span.text")
            if time_node is None or title_node is None:
                continue
            title = " ".join(title_node.get_text(" ", strip=True).split())
            if "국무회의" not in title:
                continue
            is_live_broadcast = any(
                str(image.get("alt") or "").strip() == "생방송"
                for image in row.select("img")
            )
            # KTV may also list later reruns.  Only the official live-broadcast
            # slot is evidence of the meeting schedule itself.
            if not is_live_broadcast:
                continue
            time_text = " ".join(time_node.get_text(" ", strip=True).split())
            if not time_text:
                continue
            program_node = row.select_one("td.tit .channel-cont strong")
            program_name = (
                " ".join(program_node.get_text(" ", strip=True).split())
                if program_node is not None else None
            )
            link_node = row.select_one("td.action a[href]")
            detail_url = (
                urljoin(payload.source_url, str(link_node.get("href")))
                if link_node is not None else payload.source_url
            )
            identity = "|".join((
                scheduled_date.isoformat(), time_text, title,
            ))
            records.append(ScheduleSourceRecord(
                source_record_key=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                schedule_kind="국무회의",
                content=title,
                date_text=scheduled_date.isoformat(),
                time_text=time_text,
                meeting_type="국무회의",
                committee_name="국무회의",
                session_text=None,
                meeting_order_text=None,
                host_name=program_name or "KTV 국민방송",
                place="KTV 국민방송",
                institution="EXECUTIVE",
                broadcast_scheduled=True,
                broadcast_source_url=detail_url,
            ))
        return records
