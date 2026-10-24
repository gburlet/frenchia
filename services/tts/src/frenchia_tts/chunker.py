"""Pure text helpers: normalise French text and split it into sentence-sized chunks."""

from __future__ import annotations

import re
import unicodedata

MAX_CHUNK = 300
MIN_CHUNK = 20

# Words whose trailing period does not end a sentence ("p. ex." -> "p", "ex").
ABBREVIATIONS = frozenset(
    (
        "m mm mme mmes mlle mlles me mes dr drs pr st ste sts stes p pp ex cf env vol no nos n "
        "fig av boul bd ch chap éd ed tel tél min max etc cie ltée apr "
        "janv févr avr juil sept oct nov déc"
    ).split()
)
_END = re.compile(r"[.!?…]+(?:\s?[»\"”')\]])*(?=\s|$)")
_WORD_BEFORE = re.compile(r"(\w+)$")
_SPACES: dict[str, str | int | None] = {" ": " ", " ": " ", " ": " ", "’": "'", "‘": "'"}


def normalize(text: str) -> str:
    """NFC, plain spaces and apostrophes, collapsed whitespace; line breaks are kept."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(str.maketrans(_SPACES))
    lines = (re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.split("\n"))
    return "\n".join(ln for ln in lines if ln)


def _is_abbreviation(text: str, m: re.Match[str]) -> bool:
    if m.group() != ".":
        return False
    w = _WORD_BEFORE.search(text[: m.start()])
    if not w:
        return False
    word = w.group(1)
    if word.lower() == "etc":  # "etc." may legitimately end a sentence
        return not text[m.end() :].lstrip()[:1].isupper()
    return word.lower() in ABBREVIATIONS or (len(word) == 1 and word.isupper())


def split_sentences(text: str) -> list[str]:
    """Split on . ! ? … and line breaks, skipping abbreviations; decimals never match."""
    out: list[str] = []
    for line in normalize(text).split("\n"):
        start = 0
        for m in _END.finditer(line):
            if not _is_abbreviation(line, m):
                out.append(line[start : m.end()].strip())
                start = m.end()
        if line[start:].strip():
            out.append(line[start:].strip())
    return out


def hard_wrap(sentence: str, limit: int = MAX_CHUNK) -> list[str]:
    """Wrap an over-long sentence at the last comma (else space) before ``limit``."""
    parts: list[str] = []
    while len(sentence) > limit:
        window = sentence[:limit]
        cut = max(window.rfind(", "), window.rfind("; "))
        cut = cut + 1 if cut > limit // 3 else window.rfind(" ")
        if cut <= 0:
            cut = limit
        parts.append(sentence[:cut].strip())
        sentence = sentence[cut:].strip()
    if sentence:
        parts.append(sentence)
    return parts


def chunk_text(text: str, limit: int = MAX_CHUNK, min_len: int = MIN_CHUNK) -> list[str]:
    """Sentences, hard-wrapped, with tiny fragments merged into their neighbour."""
    pieces = [p for s in split_sentences(text) for p in hard_wrap(s, limit)]
    merged: list[str] = []
    for p in pieces:
        if merged and (len(merged[-1]) < min_len) and len(merged[-1]) + 1 + len(p) <= limit:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    if len(merged) > 1 and len(merged[-1]) < min_len and len(merged[-2]) + len(merged[-1]) < limit:
        merged[-2:] = [f"{merged[-2]} {merged[-1]}"]
    return merged
