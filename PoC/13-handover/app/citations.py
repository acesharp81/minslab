"""Resolve PDF visual line wraps back to exact, contiguous original spans.

No punctuation, numbers, words or block identifiers are corrected. The returned
text always comes from the original block, never from normalized model output.
"""
import re


def _layout_text(text):
    chars, starts, ends = [], [], []
    for match in re.finditer(r'\s+|\S', text):
        token = match.group()
        if token.isspace():
            # PDF can split a Korean word across physical lines. Only a bare
            # line ending between Hangul syllables is removable; ordinary
            # spaces (and separated numbers) remain meaningful separators.
            before = text[match.start()-1:match.start()] if match.start() else ''
            after = text[match.end():match.end()+1]
            if token in {'\n','\r\n'} and re.fullmatch('[가-힣]', before) and re.fullmatch('[가-힣]', after):
                continue
            token = ' '
        chars.append(token); starts.append(match.start()); ends.append(match.end())
    return ''.join(chars), starts, ends


def exact_pdf_span(original, proposed):
    if proposed in original:
        return proposed
    if '\n' not in original:
        raise ValueError('원문에 존재하지 않는 인용입니다.')
    text, starts, ends = _layout_text(original)
    target, _, _ = _layout_text(proposed)
    first = text.find(target) if target else -1
    if first < 0 or text.find(target, first+1) >= 0:
        raise ValueError('원문에 존재하지 않거나 위치가 불명확한 인용입니다.')
    return original[starts[first]:ends[first+len(target)-1]]
