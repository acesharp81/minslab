"""Housing block identity, including physically distinct split blocks."""
import re

# A hyphen before the number is typography; one after it identifies a sub-block.
_CODE = r'([A-Z]{1,3})\s*[-－]?\s*(\d+)(?:\s*[-－]\s*(\d+))?'
_FULL = re.compile(_CODE + r'\s*(?:BL|블록)?', re.I)
_TITLE = re.compile(r'(?<![A-Z])' + _CODE +
                    r'\s*(?:BL|블록|(?![A-Z0-9－-]))', re.I)


def _canonical(match):
    prefix, number, split = match.groups()
    return prefix.upper() + str(int(number)) + ('-' + str(int(split)) if split else '')


def normalize_block(value):
    match = _FULL.fullmatch(str(value or '').strip())
    return _canonical(match) if match else None


def title_blocks(value):
    return {_canonical(match) for match in _TITLE.finditer(str(value or ''))}
