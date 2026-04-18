import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class ChapterSentence(BaseModel):
    sentence_id: str
    text: str
    finalized_at: datetime
    line_count: int = 1  # number of lines in the segment (1 for legacy records)


class Chapter(BaseModel):
    chapter_id: str
    chapter_number: int
    title: str
    status: str = "draft"
    summary: str = ""
    notes: str = ""
    last_updated: Optional[datetime] = None
    sentences: list[ChapterSentence] = []


def _chapters_dir(project_path: Path, config) -> Path:
    return project_path / config.chapters.chapters_dir


def list_chapters(project_path: Path, config) -> list[Chapter]:
    d = _chapters_dir(project_path, config)
    if not d.exists():
        return []
    chapters: list[Chapter] = []
    for f in sorted(d.glob("chapter_*.json")):
        try:
            chapters.append(Chapter.model_validate(json.loads(f.read_text())))
        except Exception:
            continue
    return sorted(chapters, key=lambda c: c.chapter_number)


def load_chapter(project_path: Path, config, chapter_id: str) -> Chapter:
    path = _chapters_dir(project_path, config) / f"{chapter_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Chapter file not found: {path}")
    return Chapter.model_validate(json.loads(path.read_text()))


def save_chapter(project_path: Path, config, chapter: Chapter) -> None:
    d = _chapters_dir(project_path, config)
    d.mkdir(parents=True, exist_ok=True)
    chapter.last_updated = datetime.now(timezone.utc)
    path = d / f"{chapter.chapter_id}.json"
    path.write_text(chapter.model_dump_json(indent=2))


def append_sentence_to_chapter(
    project_path: Path, config, chapter_id: str, sentence: ChapterSentence
) -> None:
    chapter = load_chapter(project_path, config, chapter_id)
    chapter.sentences.append(sentence)
    save_chapter(project_path, config, chapter)


def delete_sentence_from_chapter(
    project_path: Path, config, chapter_id: str, sentence_id: str
) -> bool:
    """Remove the sentence with *sentence_id* from the chapter.

    Returns True if found and removed, False if not found.
    """
    chapter = load_chapter(project_path, config, chapter_id)
    before = len(chapter.sentences)
    chapter.sentences = [s for s in chapter.sentences if s.sentence_id != sentence_id]
    if len(chapter.sentences) < before:
        save_chapter(project_path, config, chapter)
        return True
    return False
