from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from augmented_fiction.commands.builtins import build_registry
from augmented_fiction.commands.registry import WriteContext
from augmented_fiction.project.chapters import (
    Chapter,
    ChapterSentence,
    append_sentence_to_chapter,
    list_chapters,
    load_chapter,
    save_chapter,
)
from augmented_fiction.project.history import (
    SentenceRecord,
    append_record,
    load_finalized,
    next_sentence_id,
)
from augmented_fiction.project.meta import load_meta, save_meta
from augmented_fiction.project.store import list_projects, load_project

_HERE = Path(__file__).parent

app = FastAPI(title="Augmented Fiction")
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=_HERE / "templates")


def _build_ctx(project_path, config) -> WriteContext:
    meta = load_meta(project_path) if config.chapters.enabled else None
    return WriteContext(project_path=project_path, config=config, meta=meta)


def _current_finalized(project_path, config, meta, n: int) -> list[str]:
    """Return last n sentence texts, chapter-scoped if chapters are enabled."""
    if config.chapters.enabled and meta:
        try:
            chapter = load_chapter(project_path, config, meta.current_chapter)
            return [s.text for s in chapter.sentences[-n:]]
        except FileNotFoundError:
            return []
    history_path = project_path / config.document.history_file
    return [r.final_text for r in load_finalized(history_path, n)]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    projects = []
    for p in list_projects():
        try:
            _, config = load_project(p.name)
            projects.append({
                "id": config.project.project_id,
                "title": config.project.title,
                "mode": config.mode.type.value,
                "author": config.project.author,
            })
        except Exception:
            pass
    return templates.TemplateResponse(
        request=request, name="index.html", context={"projects": projects}
    )


@app.get("/project/{project_id}", response_class=HTMLResponse)
async def write_session(request: Request, project_id: str):
    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        return HTMLResponse("Project not found", status_code=404)

    meta = load_meta(project_path) if config.chapters.enabled else None
    n = config.interface.last_finalized_segment_count
    finalized = _current_finalized(project_path, config, meta, n)
    active = config.modules.active_modules()

    chapters = list_chapters(project_path, config) if config.chapters.enabled else []
    current_chapter = None
    if config.chapters.enabled and meta:
        try:
            current_chapter = load_chapter(project_path, config, meta.current_chapter)
        except FileNotFoundError:
            pass

    return templates.TemplateResponse(
        request=request,
        name="write.html",
        context={
            "config": config,
            "finalized": finalized,
            "active_modules": active,
            "chapters": chapters,
            "current_chapter": current_chapter,
        },
    )


@app.post("/project/{project_id}/submit")
async def submit(project_id: str, sentence: str = Form(...)):
    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        return JSONResponse({"error": "Project not found"}, status_code=404)

    text = sentence.strip()
    if not text:
        return JSONResponse({"error": "Empty input"}, status_code=400)

    meta = load_meta(project_path) if config.chapters.enabled else None
    ctx = WriteContext(project_path=project_path, config=config, meta=meta)
    registry = build_registry(ctx)

    # Dispatch colon commands
    result = registry.dispatch(text, ctx)
    if result is not None:
        n = config.interface.last_finalized_segment_count
        # Meta may have changed (chapter switch); reload
        meta = load_meta(project_path) if config.chapters.enabled else None
        finalized = _current_finalized(project_path, config, meta, n)
        return JSONResponse({
            "kind": "command",
            "output": result.output,
            "error": result.kind == "error",
            "finalized": finalized,
            "current_chapter": meta.current_chapter if meta else None,
        })

    # Save sentence
    history_path = project_path / config.document.history_file
    record = SentenceRecord(
        sentence_id=next_sentence_id(history_path),
        timestamp=datetime.now(timezone.utc),
        raw_input=text,
        final_text=text,
        status="finalized",
        mode=config.mode.type.value,
        module_results=[],
        user_choice="original",
    )
    append_record(history_path, record)

    if config.chapters.enabled and meta:
        cs = ChapterSentence(
            sentence_id=record.sentence_id,
            text=record.final_text,
            finalized_at=record.timestamp,
        )
        try:
            append_sentence_to_chapter(
                project_path, config, meta.current_chapter, cs
            )
        except FileNotFoundError:
            pass

    n = config.interface.last_finalized_segment_count
    finalized = _current_finalized(project_path, config, meta, n)

    return JSONResponse({
        "kind": "sentence",
        "sentence_id": record.sentence_id,
        "finalized": finalized,
        "current_chapter": meta.current_chapter if meta else None,
    })


@app.get("/project/{project_id}/chapters")
async def get_chapters(project_id: str):
    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        return JSONResponse({"error": "Project not found"}, status_code=404)

    if not config.chapters.enabled:
        return JSONResponse({"chapters": [], "enabled": False})

    chapters = list_chapters(project_path, config)
    meta = load_meta(project_path)
    return JSONResponse({
        "enabled": True,
        "current_chapter": meta.current_chapter,
        "chapters": [
            {
                "chapter_id": c.chapter_id,
                "chapter_number": c.chapter_number,
                "title": c.title,
                "status": c.status,
                "sentence_count": len(c.sentences),
            }
            for c in chapters
        ],
    })


@app.post("/project/{project_id}/chapter/new")
async def new_chapter(project_id: str, title: str = Form("")):
    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        return JSONResponse({"error": "Project not found"}, status_code=404)

    if not config.chapters.enabled:
        return JSONResponse({"error": "Chapters not enabled"}, status_code=400)

    chapters = list_chapters(project_path, config)
    next_n = max((c.chapter_number for c in chapters), default=0) + 1
    chapter_id = f"chapter_{next_n:03d}"
    new_ch = Chapter(
        chapter_id=chapter_id,
        chapter_number=next_n,
        title=title.strip() or f"Chapter {next_n}",
        status="draft",
        summary="",
        sentences=[],
    )
    save_chapter(project_path, config, new_ch)

    meta = load_meta(project_path)
    meta.current_chapter = chapter_id
    meta.current_chapter_number = next_n
    save_meta(project_path, meta)

    return JSONResponse({
        "chapter_id": chapter_id,
        "title": new_ch.title,
        "chapter_number": next_n,
    })


def serve():
    uvicorn.run("augmented_fiction.web.app:app", host="0.0.0.0", port=8010, reload=True)
