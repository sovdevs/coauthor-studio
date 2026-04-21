import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from augmented_fiction.commands.builtins import build_registry
from augmented_fiction.commands.registry import WriteContext
from augmented_fiction.modules.voice.characterbuilder.schema import (
    AuthorialMaterial,
    Behavior,
    CharacterProfile,
    Demographics,
    InnerEngine,
    Provenance,
    ReferenceQuote,
    Signature,
    Story,
    StyleTrace,
    Surface,
    Voice,
    _slugify,
    make_character_id,
    profile_to_markdown,
    source_slug,
)
from augmented_fiction.modules.voice.characterbuilder.storage import (
    delete_character,
    duplicate_character,
    existing_ids,
    list_characters,
    load_character,
    save_character,
)
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

    characters = list_characters()

    return templates.TemplateResponse(
        request=request,
        name="write.html",
        context={
            "config": config,
            "finalized": finalized,
            "active_modules": active,
            "chapters": chapters,
            "current_chapter": current_chapter,
            "characters": characters,
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


# ── Character Studio ──────────────────────────────────────────────────────────

def _parse_lines(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _parse_bool_field(value: str) -> Optional[bool]:
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


async def _form_to_profile(form, existing: Optional[CharacterProfile] = None) -> CharacterProfile:
    """Build a CharacterProfile from POSTed form data."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    display_name = form.get("display_name", "").strip()
    source_author = form.get("source_author", "").strip() or None
    source_work   = form.get("source_work", "").strip() or None
    source_mode   = form.get("source_mode", "manual").strip()

    slug = source_slug(source_mode, source_author)
    ids  = existing_ids()
    if existing:
        ids.discard(existing.character_id)
    char_id = existing.character_id if existing else make_character_id(slug, display_name, ids)

    # Reference quotes — one per line (text only for web V1)
    rq_texts = _parse_lines(form.get("reference_quotes_text", ""))
    rq_list  = [ReferenceQuote(text=t, added_by_user=True) for t in rq_texts]
    if existing:
        # Preserve structured metadata from existing profile; only add new entries
        existing_texts = {q.text for q in existing.signature.reference_quotes}
        kept = [q for q in existing.signature.reference_quotes if q.text in {t for t in rq_texts}]
        new_ones = [ReferenceQuote(text=t, added_by_user=True) for t in rq_texts if t not in existing_texts]
        rq_list = kept + new_ones

    # Authorial material — one per line (text only for web V1)
    am_texts = _parse_lines(form.get("authorial_material_text", ""))
    am_list  = [AuthorialMaterial(text=t, paraphrase_preferred=True) for t in am_texts]

    dialogue_moves = list(form.getlist("dialogue_moves"))

    return CharacterProfile(
        character_id=char_id,
        display_name=display_name,
        source_author=source_author,
        source_work=source_work,
        source_mode=source_mode,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        demographics=Demographics(
            age=form.get("age", "").strip(),
            gender=form.get("gender", "").strip(),
            regionalism=form.get("regionalism", "").strip(),
            physical_condition=form.get("physical_condition", "").strip() or None,
            class_register=form.get("class_register", "").strip(),
        ),
        surface=Surface(
            first_impression=form.get("first_impression", "").strip(),
        ),
        inner_engine=InnerEngine(
            core_desire=form.get("core_desire", "").strip(),
            core_fear=form.get("core_fear", "").strip(),
            avoidance=form.get("avoidance", "").strip(),
            what_they_hide=form.get("what_they_hide", "").strip(),
            key_contradiction=form.get("key_contradiction", "").strip(),
            contradiction_behavior=form.get("contradiction_behavior", "").strip(),
            shame=form.get("shame", "").strip() or None,
            false_belief=form.get("false_belief", "").strip() or None,
            taboo=form.get("taboo", "").strip() or None,
        ),
        voice=Voice(
            description=form.get("voice_description", "").strip(),
            sentence_length=form.get("sentence_length", "medium"),
            question_frequency=form.get("question_frequency", "low"),
            abstraction_level=form.get("abstraction_level", "medium"),
            uses_fragments=_parse_bool_field(form.get("uses_fragments", "")),
            repetition=form.get("repetition", "low"),
            metaphor=form.get("metaphor", "low"),
            conversation_control=form.get("conversation_control", "mixed"),
            verbosity=form.get("verbosity", "variable"),
        ),
        behavior=Behavior(
            conflict_response=form.get("conflict_response", "").strip(),
            avoidance_pattern=form.get("avoidance_pattern", "").strip(),
            dialogue_stance=form.get("dialogue_stance", "mixed"),
            dialogue_moves=dialogue_moves,
            status_with_needed=form.get("status_with_needed", "").strip() or None,
            status_with_unneeded=form.get("status_with_unneeded", "").strip() or None,
            intimacy_style=form.get("intimacy_style", "").strip() or None,
            pressure_response=form.get("pressure_response", "").strip() or None,
        ),
        signature=Signature(
            what_they_notice=form.get("what_they_notice", "").strip(),
            behaviors=_parse_lines(form.get("behaviors", "")),
            sensory_bias=form.get("sensory_bias", "").strip() or None,
            relational_tendencies=form.get("relational_tendencies", "").strip() or None,
            anti_patterns=_parse_lines(form.get("anti_patterns", "")),
            example_lines=_parse_lines(form.get("example_lines", "")),
            speech_patterns=_parse_lines(form.get("speech_patterns", "")),
            lexical_markers=_parse_lines(form.get("lexical_markers", "")),
            reference_quotes=rq_list,
            authorial_material=am_list,
        ),
        story=Story(
            role=form.get("story_role", "").strip() or None,
            scene_function=form.get("scene_function", "").strip() or None,
        ),
        style_trace=StyleTrace(),
        provenance=existing.provenance if existing else Provenance(
            registry_path=f"modules/voice/characterbuilder/characters/{char_id}.json"
        ),
    )


@app.get("/characters", response_class=HTMLResponse)
async def characters_index(request: Request):
    chars = list_characters()
    return templates.TemplateResponse(
        request=request,
        name="characters.html",
        context={"characters": chars, "selected": None},
    )


@app.get("/characters/new", response_class=HTMLResponse)
async def characters_new_form(request: Request):
    chars = list_characters()
    return templates.TemplateResponse(
        request=request,
        name="characters.html",
        context={"characters": chars, "selected": None, "is_new": True},
    )


@app.post("/characters/new")
async def characters_create(request: Request):
    form = await request.form()
    profile = await _form_to_profile(form)
    if not profile.display_name:
        return JSONResponse({"error": "Name is required"}, status_code=400)
    save_character(profile)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/characters/{profile.character_id}", status_code=303)


@app.get("/characters/{character_id}", response_class=HTMLResponse)
async def characters_detail(request: Request, character_id: str):
    try:
        selected = load_character(character_id)
    except FileNotFoundError:
        return HTMLResponse("Character not found", status_code=404)
    chars = list_characters()
    return templates.TemplateResponse(
        request=request,
        name="characters.html",
        context={"characters": chars, "selected": selected, "is_new": False},
    )


@app.post("/characters/{character_id}")
async def characters_update(request: Request, character_id: str):
    try:
        existing = load_character(character_id)
    except FileNotFoundError:
        return JSONResponse({"error": "Not found"}, status_code=404)
    form = await request.form()
    updated = await _form_to_profile(form, existing=existing)
    save_character(updated)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/characters/{character_id}", status_code=303)


@app.post("/characters/{character_id}/delete")
async def characters_delete(character_id: str):
    delete_character(character_id)
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/characters", status_code=303)


@app.post("/characters/{character_id}/duplicate")
async def characters_duplicate(character_id: str):
    try:
        new_profile = duplicate_character(character_id)
    except FileNotFoundError:
        return JSONResponse({"error": "Character not found"}, status_code=404)
    save_character(new_profile)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/characters/{new_profile.character_id}", status_code=303)


# ── Dialog Studio ─────────────────────────────────────────────────────────────

@app.get("/dialog/new", response_class=HTMLResponse)
async def dialog_new_form(request: Request):
    chars = list_characters()
    projects = []
    for p in list_projects():
        try:
            _, config = load_project(p.name)
            projects.append({"id": config.project.project_id, "title": config.project.title})
        except Exception:
            pass
    return templates.TemplateResponse(
        request=request,
        name="dialog_new.html",
        context={"characters": chars, "projects": projects},
    )


@app.post("/dialog/generate")
async def dialog_generate(request: Request):
    form = await request.form()
    char_ids  = [form.get("char_a", "").strip(), form.get("char_b", "").strip()]
    char_ids  = [c for c in char_ids if c]
    setting   = form.get("setting", "").strip()
    mode      = form.get("mode", "dialog")
    project_id = form.get("project_id", "").strip()
    quote_mode = form.get("quote_mode", "auto")
    allow_direct = form.get("allow_direct_quotes") == "1"
    include_auth = form.get("include_authorial_material") == "1"

    if len(char_ids) < 2:
        return JSONResponse({"error": "Two characters required"}, status_code=400)
    if not setting:
        return JSONResponse({"error": "Setting is required"}, status_code=400)
    if not project_id:
        return JSONResponse({"error": "Project is required for saving drafts"}, status_code=400)

    try:
        profiles = [load_character(cid) for cid in char_ids]
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        return JSONResponse({"error": f"Project not found: {project_id}"}, status_code=404)

    try:
        from augmented_fiction.modules.voice.characterbuilder.dialog import generate
        out_path = generate(
            profiles=profiles,
            setting=setting,
            mode=mode,
            project_path=project_path,
            llm_config=config.llm,
            quote_mode=quote_mode,
            allow_direct_quotes=allow_direct,
            include_authorial_material=include_auth,
        )
        draft_text = Path(out_path).read_text(encoding="utf-8")
        return JSONResponse({
            "ok": True,
            "path": out_path,
            "content": draft_text,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ── Dialog revision loop ──────────────────────────────────────────────────────

@app.post("/dialog/submit-revision")
async def dialog_submit_revision(request: Request):
    """
    Receive original + revised dialog content, run delta generation,
    return structured delta + proposed profile updates for writer review.
    """
    form = await request.form()
    original_content = form.get("original_content", "").strip()
    revised_content  = form.get("revised_content", "").strip()
    char_ids = [c.strip() for c in form.getlist("char_ids") if c.strip()]
    mode     = form.get("mode", "dialog")
    setting  = form.get("setting", "").strip()
    project_id = form.get("project_id", "").strip()

    if not original_content or not revised_content:
        return JSONResponse({"error": "Both original and revised content required"}, status_code=400)
    if not char_ids:
        return JSONResponse({"error": "Character IDs required"}, status_code=400)

    try:
        profiles = [load_character(cid) for cid in char_ids]
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        return JSONResponse({"error": f"Project not found: {project_id}"}, status_code=404)

    api_key = os.environ.get(config.llm.api_key_env, "")
    if not api_key:
        return JSONResponse({"error": f"LLM API key not set ({config.llm.api_key_env})"}, status_code=500)

    try:
        from augmented_fiction.modules.voice.characterbuilder.delta import (
            generate_delta, write_revision_log,
        )
        delta = generate_delta(
            profiles=profiles,
            original_content=original_content,
            revised_content=revised_content,
            mode=mode,
            setting=setting,
            llm_config=config.llm,
            api_key=api_key,
        )
        write_revision_log(
            project_path=project_path,
            log_id=delta.log_id,
            mode=mode,
            setting=setting,
            character_ids=char_ids,
            original_content=original_content,
            revised_content=revised_content,
            delta_result=delta,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    # Serialise delta for the client
    result = {
        "log_id": delta.log_id,
        "affected_characters": [
            {
                "character_id": cd.character_id,
                "display_name": cd.display_name,
                "change_labels": [
                    {"label": cl.label, "confidence": cl.confidence}
                    for cl in cd.change_labels
                ],
                "proposed_updates": [
                    {
                        "field": u.field,
                        "display_name": u.display_name,
                        "update_type": u.update_type,
                        "current_value": u.current_value,
                        "proposed_value": u.proposed_value,
                        "reason": u.reason,
                        "confidence": u.confidence,
                    }
                    for u in cd.proposed_updates
                ],
            }
            for cd in delta.affected_characters
        ],
    }
    return JSONResponse(result)


@app.post("/dialog/accept-updates")
async def dialog_accept_updates(request: Request):
    """
    Apply accepted profile updates to character(s) and update the revision log.
    """
    form = await request.form()
    # Updates are sent as JSON string
    updates_json = form.get("updates_json", "[]")
    log_id       = form.get("log_id", "")
    project_id   = form.get("project_id", "").strip()
    mode         = form.get("mode", "dialog")
    setting      = form.get("setting", "").strip()
    char_ids     = [c.strip() for c in form.getlist("char_ids") if c.strip()]
    original_content = form.get("original_content", "").strip()
    revised_content  = form.get("revised_content", "").strip()

    try:
        all_updates = json.loads(updates_json)  # list of {character_id, updates:[...]}
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": "Invalid updates JSON"}, status_code=400)

    applied: list[dict] = []
    for char_block in all_updates:
        cid  = char_block.get("character_id", "")
        upds = char_block.get("updates", [])
        if not cid or not upds:
            continue
        try:
            profile = load_character(cid)
        except FileNotFoundError:
            return JSONResponse({"error": f"Character not found: {cid}"}, status_code=404)

        from augmented_fiction.modules.voice.characterbuilder.delta import apply_updates
        updated = apply_updates(profile, upds)
        save_character(updated)
        applied.extend(upds)

    # Update revision log with accepted status
    if log_id and project_id:
        try:
            project_path, _ = load_project(project_id)
            from augmented_fiction.modules.voice.characterbuilder.delta import (
                write_revision_log, DeltaResult, CharacterDelta
            )
            # Reconstruct minimal delta for log update
            dummy_delta = DeltaResult(log_id=log_id, mode=mode, affected_characters=[])
            write_revision_log(
                project_path=project_path,
                log_id=log_id,
                mode=mode,
                setting=setting,
                character_ids=char_ids,
                original_content=original_content,
                revised_content=revised_content,
                delta_result=dummy_delta,
                accepted=True,
                applied_updates=applied,
            )
        except Exception:
            pass  # log failure is non-fatal

    return JSONResponse({"ok": True, "applied_count": len(applied)})


def serve():
    uvicorn.run("augmented_fiction.web.app:app", host="0.0.0.0", port=8010, reload=True)
