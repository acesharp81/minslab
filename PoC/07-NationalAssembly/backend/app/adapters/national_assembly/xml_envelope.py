from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

from .base import AdapterError


@dataclass(frozen=True, slots=True)
class XmlEnvelope:
    result_code: str | None
    result_message: str | None
    total_count: int | None
    rows: tuple[dict[str, str | None], ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_dict(element: ElementTree.Element) -> dict[str, str | None]:
    return {_local_name(child.tag): child.text for child in list(element)}


def parse_xml_envelope(content: bytes, *, row_tag: str = "row") -> XmlEnvelope:
    """Parse only the common envelope; source-specific mapping follows contract verification."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise AdapterError(f"malformed XML: {error}") from error

    values: dict[str, str | None] = {}
    rows: list[dict[str, str | None]] = []
    for element in root.iter():
        name = _local_name(element.tag)
        if name == row_tag:
            rows.append(_element_dict(element))
        elif not list(element) and name not in values:
            values[name] = element.text

    raw_count = values.get("totalCount") or values.get("list_total_count")
    try:
        total_count = int(raw_count) if raw_count is not None else None
    except ValueError as error:
        raise AdapterError(f"invalid total count: {raw_count!r}") from error

    return XmlEnvelope(
        result_code=values.get("resultCode") or values.get("CODE"),
        result_message=values.get("resultMsg") or values.get("MESSAGE"),
        total_count=total_count,
        rows=tuple(rows),
    )
