import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class SentenceRecord(BaseModel):
    sentence_id: str
    timestamp: datetime
    raw_input: str
    final_text: str
    status: str          # "finalized" | "candidate" | "rejected"
    mode: str
    module_results: list = []
    user_choice: str     # "original" | "suggestion_N"
    line_count: int = 1  # number of lines in the segment (1 for legacy records)


def load_finalized(history_path: Path, count: int) -> list[SentenceRecord]:
    """Return the last *count* finalized sentences from history."""
    if not history_path.exists():
        return []
    records: list[SentenceRecord] = []
    for line in history_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = SentenceRecord.model_validate(json.loads(line))
            if rec.status == "finalized":
                records.append(rec)
        except Exception:
            continue
    return records[-count:]


def append_record(history_path: Path, record: SentenceRecord) -> None:
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(record.model_dump_json() + "\n")


def delete_record(history_path: Path, sentence_id: str) -> bool:
    """Remove the record with *sentence_id* from the JSONL file.

    Returns True if a record was found and removed, False otherwise.
    The file is rewritten in-place; all other records are preserved.
    """
    if not history_path.exists():
        return False
    lines = history_path.read_text().splitlines()
    kept: list[str] = []
    removed = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get("sentence_id") == sentence_id:
                removed = True
                continue
        except Exception:
            pass
        kept.append(line)
    if removed:
        history_path.write_text("\n".join(kept) + ("\n" if kept else ""))
    return removed


def next_sentence_id(history_path: Path) -> str:
    if not history_path.exists():
        return "sent_000001"
    total = sum(1 for line in history_path.read_text().splitlines() if line.strip())
    return f"sent_{total + 1:06d}"
