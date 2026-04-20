from __future__ import annotations

import re


_QUESTION_ID_RE = re.compile(
    r"(?:question\s*)?(?P<number>\d{1,2})\s*(?:\(?\s*(?P<alpha>[a-h])\s*\)?)?\s*(?:\(?\s*(?P<roman>viii|vii|vi|iv|ix|iii|ii|i|v|x)\s*\)?)?",
    re.IGNORECASE,
)


def normalize_question_id(value: str | int | None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    match = _QUESTION_ID_RE.search(text)
    if not match:
        return text.replace(" ", "")
    number = str(int(match.group("number")))
    alpha = match.group("alpha")
    roman = match.group("roman")
    parts = [number]
    if alpha:
        parts.append(f"({alpha.lower()})")
    if roman:
        parts.append(f"({roman.lower()})")
    return "".join(parts)


def parent_question_id(value: str | int | None) -> str:
    normalized = normalize_question_id(value)
    match = re.match(r"\d{1,2}", normalized)
    return match.group(0) if match else normalized
