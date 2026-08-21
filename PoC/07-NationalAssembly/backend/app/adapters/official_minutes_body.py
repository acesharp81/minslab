from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .national_assembly.base import AdapterError, SourcePayload


@dataclass(frozen=True, slots=True)
class OfficialUtterance:
    sequence_number: int
    source_speaker_id: str
    source_span_id: str
    agenda_item_ref: str | None
    speaker_name: str | None
    speaker_role: str | None
    text: str
    text_hash: str


@dataclass(frozen=True, slots=True)
class OfficialMinutesBody:
    conference_id: str
    publication_stage: str
    status_text: str | None
    title: str | None
    utterances: tuple[OfficialUtterance, ...]


class OfficialMinutesBodyAdapter:
    source_key = "committee_minutes_body"
    parser_version = "official-minutes-html.v1"

    def parse(self, payload: SourcePayload) -> OfficialMinutesBody:
        if "html" not in payload.content_type.lower() and not payload.content.lstrip().startswith(b"<"):
            raise AdapterError("official minutes body is not HTML")
        decoded = payload.content.decode("utf-8", "replace")
        soup = BeautifulSoup(payload.content, "html.parser")
        minutes = soup.select_one("#minutes")
        if minutes is None:
            raise AdapterError("official minutes body has no #minutes element")
        conference_match = re.search(r'const\s+confer_num\s*=\s*["\']([^"\']+)', decoded)
        if not conference_match:
            raise AdapterError("official minutes body has no conference id")
        temporary = minutes.select_one(".bg_tmp") is not None or "임시회의록" in minutes.get_text(" ", strip=True)
        status_text = None
        status_match = re.search(r'const\s+status\s*=\s*"((?:[^"\\]|\\.)*)"', decoded)
        if status_match:
            status_text = status_match.group(1).replace("\\r", " ").replace("\\n", " ").strip()
        title_node = minutes.select_one(".minutes_header h1")
        utterances: list[OfficialUtterance] = []
        for speaker in minutes.select(".minutes_body .speaker[id]"):
            source_speaker_id = str(speaker.get("id") or "").strip()
            if not source_speaker_id:
                continue
            classes = speaker.get("class") or []
            agenda_ref = next((value for value in classes if re.fullmatch(r"item\d+", value)), None)
            speaker_name = self._clean(speaker.get("data-name"))
            speaker_role = self._clean(speaker.get("data-pos"))
            for span in speaker.select(".talk .spk_sub[id]"):
                source_span_id = str(span.get("id") or "").strip()
                text = self._clean(span.get_text(" ", strip=True))
                if not source_span_id or not text:
                    continue
                utterances.append(OfficialUtterance(
                    sequence_number=len(utterances) + 1,
                    source_speaker_id=source_speaker_id,
                    source_span_id=source_span_id,
                    agenda_item_ref=agenda_ref,
                    speaker_name=speaker_name,
                    speaker_role=speaker_role,
                    text=text,
                    text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                ))
        if not utterances:
            raise AdapterError("official minutes body has no utterance spans")
        return OfficialMinutesBody(
            conference_id=conference_match.group(1),
            publication_stage="TEMPORARY" if temporary else "FINAL",
            status_text=status_text,
            title=self._clean(title_node.get_text(" ", strip=True) if title_node else None),
            utterances=tuple(utterances),
        )

    @staticmethod
    def _clean(value: object) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
        return text or None


def normalized_match_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())
