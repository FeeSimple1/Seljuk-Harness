"""Lossless, packaged rules/card reference access. No character truncation."""
from functools import lru_cache
from pathlib import Path
import json
import re


@lru_cache(maxsize=1)
def sources() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] /
                       "data/static/llm_references.json").read_text(encoding="utf-8"))


def card_text(card_id: str) -> str:
    text = sources()["cards"]["text"]
    starts = list(re.finditer(r"^([RS]\d+)\. .+$", text, re.MULTILINE))
    for i, match in enumerate(starts):
        if match.group(1) == card_id:
            end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
            return text[match.start():end].rstrip("\n -\r")
    raise KeyError(card_id)
