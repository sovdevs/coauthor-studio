"""
Built-in command handlers for the writing session.

Each handler follows the signature: (arg: str, ctx: WriteContext) -> CommandResult.
Commands are registered conditionally based on config — only enabled features
add commands, so the registry stays clean for every project type.

To add commands for a new module: write a handler function, then register
it in build_registry() conditional on whatever config flag makes sense.
"""
from __future__ import annotations

from datetime import datetime, timezone

from augmented_fiction.commands.registry import CommandRegistry, CommandResult, WriteContext
from augmented_fiction.project.chapters import (
    Chapter,
    ChapterSentence,
    append_sentence_to_chapter,
    delete_sentence_from_chapter,
    list_chapters,
    load_chapter,
    save_chapter,
)
from augmented_fiction.project.history import delete_record
from augmented_fiction.project.meta import save_meta


# ── Chapter commands ──────────────────────────────────────────────────────────

def _chapters_list(arg: str, ctx: WriteContext) -> CommandResult:
    chapters = list_chapters(ctx.project_path, ctx.config)
    if not chapters:
        return CommandResult("  No chapters found.", kind="info")
    lines: list[str] = []
    for ch in chapters:
        marker = "▶" if ch.chapter_id == ctx.meta.current_chapter else " "
        lines.append(f"  {marker} {ch.chapter_number}.  {ch.title}  [{ch.status}]  ({len(ch.sentences)} sentences)")
    return CommandResult("\n".join(lines))


def _chapter_switch(arg: str, ctx: WriteContext) -> CommandResult:
    if not arg:
        return CommandResult("  Usage: :c <number or chapter_id>", kind="error")
    chapters = list_chapters(ctx.project_path, ctx.config)
    if arg.isdigit():
        target = next((c for c in chapters if c.chapter_number == int(arg)), None)
    else:
        target = next((c for c in chapters if c.chapter_id == arg), None)
    if target is None:
        return CommandResult(f"  Chapter not found: {arg}", kind="error")
    ctx.meta.current_chapter = target.chapter_id
    ctx.meta.current_chapter_number = target.chapter_number
    save_meta(ctx.project_path, ctx.meta)
    return CommandResult(f"  Switched to: {target.title}  ({target.chapter_id})")


def _chapter_new(arg: str, ctx: WriteContext) -> CommandResult:
    chapters = list_chapters(ctx.project_path, ctx.config)
    next_n = max((c.chapter_number for c in chapters), default=0) + 1
    title = arg.strip() or f"Chapter {next_n}"
    chapter_id = f"chapter_{next_n:03d}"
    new_ch = Chapter(
        chapter_id=chapter_id,
        chapter_number=next_n,
        title=title,
        status="draft",
        summary="",
        sentences=[],
    )
    save_chapter(ctx.project_path, ctx.config, new_ch)
    ctx.meta.current_chapter = chapter_id
    ctx.meta.current_chapter_number = next_n
    save_meta(ctx.project_path, ctx.meta)
    return CommandResult(f"  Created and switched to: {title}  ({chapter_id})")


# ── Lexical commands ──────────────────────────────────────────────────────────

def _dict_lookup(arg: str, ctx: WriteContext) -> CommandResult:
    if not arg:
        return CommandResult("  Usage: :d <word>  e.g.  :d obdurate", kind="error")
    lang = ctx.config.mode.language
    try:
        from augmented_fiction.modules.dictionary import lookup
        result = lookup(arg, lang, ctx.config.lexical_backends.dictionary)
        lines = [f"  Dictionary · {result.word}  [{result.language}]"]
        if result.part_of_speech:
            lines.append(f"  Part of speech: {result.part_of_speech}")
        lines.append(f"  Meaning: {result.definition}")
        if result.notes:
            lines.append(f"  {result.notes}")
        return CommandResult("\n".join(lines))
    except Exception as exc:
        return CommandResult(f"  Dictionary lookup failed: {exc}", kind="error")


def _thes_lookup(arg: str, ctx: WriteContext) -> CommandResult:
    if not arg:
        return CommandResult("  Usage: :t <word>  e.g.  :t bleak", kind="error")
    lang = ctx.config.mode.language
    try:
        import shutil
        from augmented_fiction.modules.thesaurus import lookup
        result = lookup(arg, lang, ctx.config.lexical_backends.thesaurus)
        archaic_note = "  † archaic · literary" if result.query_is_archaic else ""
        lines = [f"  Thesaurus · {result.word}{archaic_note}"]

        # Target ~2/3 of terminal width for each synonym line
        term_width = max(40, shutil.get_terminal_size(fallback=(100, 40)).columns * 2 // 3)

        def _fill_line(prefix: str, alternatives: list[str]) -> str:
            """Join terms with ' · ' up to term_width; always include at least one."""
            parts: list[str] = []
            budget = term_width - len(prefix)
            for term in alternatives:
                segment = (" · " if parts else "") + term
                if parts and len("".join(parts)) + len(segment) > budget:
                    break
                parts.append(segment)
            return prefix + "".join(parts)

        main_groups = [g for g in result.groups if not g.is_archaic]
        archaic_groups = [g for g in result.groups if g.is_archaic]

        if main_groups:
            for group in main_groups:
                lines.append(_fill_line(f"  {group.label}:  ", group.alternatives))
        else:
            # Moby fallback — plain list
            for group in result.groups:
                lines.append(_fill_line(f"  {group.label}:  ", group.alternatives))

        if archaic_groups:
            for group in archaic_groups:
                lines.append(_fill_line("  † archaic:  ", group.alternatives))

        if not result.groups:
            lines.append("  (no synonyms found)")
        if result.notes:
            lines.append(f"  {result.notes}")
        return CommandResult("\n".join(lines))
    except Exception as exc:
        return CommandResult(f"  Thesaurus lookup failed: {exc}", kind="error")


# ── Delete command ───────────────────────────────────────────────────────────

def _del_sentence(arg: str, ctx: WriteContext) -> CommandResult:
    if not arg or not arg.strip().isdigit():
        return CommandResult("  Usage: :del <n>  — delete displayed sentence number n", kind="error")

    n_display = int(arg.strip())
    history_path = ctx.project_path / ctx.config.document.history_file
    window = ctx.config.interface.last_finalized_segment_count

    if ctx.config.chapters.enabled and ctx.meta:
        try:
            chapter = load_chapter(ctx.project_path, ctx.config, ctx.meta.current_chapter)
        except FileNotFoundError:
            return CommandResult("  Current chapter not found.", kind="error")

        displayed = chapter.sentences[-window:]
        if n_display < 1 or n_display > len(displayed):
            return CommandResult(
                f"  Number out of range — choose 1..{len(displayed)}", kind="error"
            )
        target = displayed[n_display - 1]
        delete_sentence_from_chapter(
            ctx.project_path, ctx.config, ctx.meta.current_chapter, target.sentence_id
        )
        delete_record(history_path, target.sentence_id)
        preview = target.text[:60] + ("…" if len(target.text) > 60 else "")
        return CommandResult(f'  Deleted sentence {n_display}: "{preview}"')

    # No chapters — delete from global JSONL display
    from augmented_fiction.project.history import load_finalized
    finalized = load_finalized(history_path, window)
    if n_display < 1 or n_display > len(finalized):
        return CommandResult(
            f"  Number out of range — choose 1..{len(finalized)}", kind="error"
        )
    target_rec = finalized[n_display - 1]
    delete_record(history_path, target_rec.sentence_id)
    preview = target_rec.final_text[:60] + ("…" if len(target_rec.final_text) > 60 else "")
    return CommandResult(f'  Deleted sentence {n_display}: "{preview}"')


# ── Utility commands ──────────────────────────────────────────────────────────

def _modules_info(arg: str, ctx: WriteContext) -> CommandResult:
    active = ctx.config.modules.active_modules()
    if not active:
        return CommandResult("  No modules active.")
    return CommandResult(f"  Active modules: {', '.join(active)}")


def _mode_info(arg: str, ctx: WriteContext) -> CommandResult:
    return CommandResult(
        f"  Mode: {ctx.config.mode.type.value}  Language: {ctx.config.mode.language}"
    )


def _quit(arg: str, ctx: WriteContext) -> CommandResult:
    return CommandResult("", kind="quit")


# ── Registry factory ──────────────────────────────────────────────────────────

def build_registry(ctx: WriteContext) -> CommandRegistry:
    """
    Build a CommandRegistry for the given project context.

    Only registers commands that are relevant to the current config.
    Safe to call for any project type — non-fiction projects won't get
    chapter commands; projects without LLM enabled won't get dict/thesaurus.
    """
    registry = CommandRegistry()

    if ctx.config.chapters.enabled:
        registry.register(["chapters"], _chapters_list, "list all chapters")
        registry.register(
            ["c"], _chapter_switch, ":c <n or id>   switch chapter"
        )
        registry.register(
            ["new"], _chapter_new, ":new [title]   create a new chapter"
        )

    if ctx.config.modules.dictionary.enabled:
        registry.register(
            ["d", "dict", "dictionary"],
            _dict_lookup,
            ":d <word>      dictionary lookup",
        )

    if ctx.config.modules.thesaurus.enabled:
        registry.register(
            ["t", "thes", "thesaurus"],
            _thes_lookup,
            ":t <word>      thesaurus lookup",
        )

    registry.register(
        ["del", "delete"],
        _del_sentence,
        ":del <n>      delete displayed sentence number n",
    )

    registry.register(["modules"], _modules_info, "list active modules")
    registry.register(["mode"], _mode_info, "show mode and language")
    registry.register(["q", "quit", "exit"], _quit, "quit writing session")

    # :help defined last so it can reference the now-complete registry
    def _help(arg: str, ctx: WriteContext) -> CommandResult:
        lines = ["  Commands:"] + registry.help_lines()
        return CommandResult("\n".join(lines))

    registry.register(["help"], _help, "show this help")

    return registry
