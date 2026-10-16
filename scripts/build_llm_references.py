"""Rebuild packaged LLM lookup text from existing repository authorities.

No summarization or rule reconciliation: text and SHA-256 provenance are kept.
Run after changing any of the listed sources; tests detect a stale bundle.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "cards": "reference/Seljuk Arts of War Reference.txt",
    "lords": "reference/Seljuk Lords Reference.txt",
    "battle": "reference/Seljuk Battle and Storm Reference.txt",
    "sequence": "reference/Seljuk Sequence of Play Reference.txt",
    "units": "reference/Seljuk_Units_and_Strongholds.txt",
    "map": "reference/Seljuk Map Reference.txt",
    "scenarios": "reference/Seljuk Themata and Scenario Reference.txt",
    "errata": "reference/Seljuk Errata and Clarifications.txt",
    "rules": "source/rules.txt",
    "decisions": "RULES_DECISIONS.md",
    "guide": "LLM_PLAY_GUIDE.md",
}


def build():
    data = {}
    for key, rel in SOURCES.items():
        raw = (ROOT / rel).read_bytes()
        data[key] = {"path": rel, "sha256": hashlib.sha256(raw).hexdigest(),
                     "text": raw.decode("utf-8")}
    dest = ROOT / "src/seljuk/data/static/llm_references.json"
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    build()
