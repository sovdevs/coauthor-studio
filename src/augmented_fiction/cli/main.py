from datetime import datetime, timezone
from pathlib import Path

import typer
from dotenv import load_dotenv

load_dotenv()

from augmented_fiction.commands.builtins import build_registry
from augmented_fiction.commands.registry import WriteContext
from augmented_fiction.project.chapters import (
    ChapterSentence,
    append_sentence_to_chapter,
    load_chapter,
)
from augmented_fiction.project.history import (
    SentenceRecord,
    append_record,
    load_finalized,
    next_sentence_id,
)
from augmented_fiction.project.meta import load_meta
from augmented_fiction.project.store import list_projects, load_project
from augmented_fiction.project.wizard import run_wizard

app = typer.Typer(
    help="af — AI-augmented writing assistant",
    no_args_is_help=True,
)

MANUSCRIPT_RULE = "═" * 56
SECTION_RULE    = "─" * 56


def _print_manuscript(segments: list[str]) -> None:
    """Print the manuscript area with formatted segments."""
    typer.echo(f"\n  {MANUSCRIPT_RULE}")
    if not segments:
        typer.echo("  (no segments yet)\n")
    else:
        for i, text in enumerate(segments, 1):
            lines = text.split("\n")
            typer.echo(f"  {i}.  {typer.style(lines[0], fg='cyan')}")
            for line in lines[1:]:
                typer.echo(f"       " + typer.style(line, fg="cyan"))
            typer.echo()
    typer.echo(f"  {MANUSCRIPT_RULE}")


def _read_input(submit_token: str) -> tuple[str, str] | None:
    """
    Read multiline segment input from stdin.

    Returns:
        ("command", text) — single-line colon command on an empty buffer
        ("segment", text) — prose segment submitted with the token
        None              — EOF or KeyboardInterrupt (quit)
    """
    lines: list[str] = []

    while True:
        try:
            prompt = "  ▶ " if not lines else "    "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            return None

        stripped = line.strip()

        # Submit token on its own — end of segment
        if stripped == submit_token:
            break

        # Colon command: only dispatched when the buffer is completely empty
        if not lines and stripped.startswith(":"):
            return ("command", stripped)

        lines.append(line)

    # Drop trailing blank lines (keep internal ones)
    while lines and not lines[-1].strip():
        lines.pop()

    return ("segment", "\n".join(lines))


@app.command()
def init():
    """Initialize a new project via setup wizard."""
    run_wizard()


@app.command(name="list")
def list_cmd():
    """List all projects."""
    projects = list_projects()
    if not projects:
        typer.echo("No projects found.")
        return
    for p in projects:
        try:
            _, config = load_project(p.name)
            active = config.modules.active_modules()
            modules_str = ", ".join(active) if active else "none"
            typer.echo(
                f"  {config.project.project_id:<24}  [{config.mode.type.value}]"
                f"  {config.project.title}"
                f"  modules: {modules_str}"
            )
        except Exception:
            typer.echo(f"  {p.name:<24}  (error loading config)")


@app.command()
def draft(
    project_id: str = typer.Argument(..., help="Project ID to export"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export all finalized segments to a draft text file."""
    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        typer.echo(f"Project '{project_id}' not found.", err=True)
        raise typer.Exit(1)

    history_path = project_path / config.document.history_file
    finalized = load_finalized(history_path, count=999999)
    if not finalized:
        typer.echo("No finalized segments to export.")
        raise typer.Exit(0)

    out_path = output or f"{project_id}_draft.txt"
    with open(out_path, "w", encoding="utf-8") as fh:
        for rec in finalized:
            fh.write(rec.final_text + "\n\n")   # blank line between segments

    typer.echo(f"Exported {len(finalized)} segments → {out_path}")


@app.command()
def write(
    project_id: str = typer.Argument(..., help="Project ID to write in"),
):
    """Enter a typewriter writing session for a project."""
    try:
        project_path, config = load_project(project_id)
    except FileNotFoundError:
        typer.echo(f"Project '{project_id}' not found.", err=True)
        raise typer.Exit(1)

    history_path  = project_path / config.document.history_file
    n             = config.interface.last_finalized_segment_count
    submit_token  = config.interface.submit_token

    meta     = load_meta(project_path) if config.chapters.enabled else None
    ctx      = WriteContext(project_path=project_path, config=config, meta=meta)
    registry = build_registry(ctx)

    def _load_chapter_safe():
        if config.chapters.enabled and meta:
            try:
                return load_chapter(project_path, config, meta.current_chapter)
            except FileNotFoundError:
                return None
        return None

    def _recent_segments() -> list[str]:
        chapter = _load_chapter_safe()
        if config.chapters.enabled and chapter:
            return [s.text for s in chapter.sentences[-n:]]
        return [r.final_text for r in load_finalized(history_path, n)]

    while True:
        # ── Header ─────────────────────────────────────────────────────────
        chapter = _load_chapter_safe()
        typer.echo(f"\n  {config.project.title}  [{config.mode.type.value}]")
        if chapter:
            typer.echo(f"  {chapter.title}")

        # ── Manuscript area ─────────────────────────────────────────────────
        _print_manuscript(_recent_segments())

        # ── Typing hint ─────────────────────────────────────────────────────
        typer.echo(
            f"\n  Enter = new line  ·  "
            f"{typer.style(submit_token, bold=True)} = submit  ·  "
            f":command on empty line\n"
        )

        # ── Read input ──────────────────────────────────────────────────────
        result = _read_input(submit_token)

        if result is None:
            break

        kind, text = result

        # ── Dispatch command ────────────────────────────────────────────────
        if kind == "command":
            cmd_result = registry.dispatch(text, ctx)
            if cmd_result is not None:
                if cmd_result.kind == "quit":
                    break
                typer.echo(f"\n  {SECTION_RULE}")
                typer.echo(cmd_result.output)
                typer.echo(f"  {SECTION_RULE}")
                if config.chapters.enabled and meta:
                    _load_chapter_safe()  # side-effect: meta may have changed
            continue

        # ── Save segment ────────────────────────────────────────────────────
        if not text.strip():
            continue

        line_count = text.count("\n") + 1
        record = SentenceRecord(
            sentence_id=next_sentence_id(history_path),
            timestamp=datetime.now(timezone.utc),
            raw_input=text,
            final_text=text,
            status="finalized",
            mode=config.mode.type.value,
            module_results=[],
            user_choice="original",
            line_count=line_count,
        )
        append_record(history_path, record)

        if config.chapters.enabled and meta:
            cs = ChapterSentence(
                sentence_id=record.sentence_id,
                text=record.final_text,
                finalized_at=record.timestamp,
                line_count=line_count,
            )
            try:
                append_sentence_to_chapter(
                    project_path, config, meta.current_chapter, cs
                )
            except FileNotFoundError:
                typer.echo(
                    f"  Warning: chapter {meta.current_chapter} not found — "
                    "segment saved to global history only."
                )

        typer.echo("  Saved.")
