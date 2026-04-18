"""
Reusable command dispatch engine.

Any input starting with ':' is treated as a command.
Registers handlers by name; dispatches by prefix match.
Used by both CLI and web — caller decides how to render CommandResult.output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class CommandResult:
    output: str
    kind: str = "info"  # "info" | "error" | "quit"


@dataclass
class WriteContext:
    """Shared state passed to every command handler."""
    project_path: Path
    config: Any   # ProjectConfig — typed loosely to avoid circular imports
    meta: Any     # ProjectMeta | None


@dataclass
class _CommandDef:
    names: list[str]
    handler: Callable[[str, WriteContext], CommandResult]
    help_text: str


class CommandRegistry:
    """
    Register command handlers and dispatch ':cmd arg' strings.

    Usage::

        registry = CommandRegistry()
        registry.register([":d", ":dict"], my_handler, ":d <word>  dictionary lookup")
        result = registry.dispatch(":d obdurate", ctx)
        if result:
            print(result.output)

    Any string not starting with ':' returns None — it's a sentence.
    """

    def __init__(self) -> None:
        self._defs: list[_CommandDef] = []
        self._index: dict[str, _CommandDef] = {}

    def register(
        self,
        names: list[str],
        handler: Callable[[str, WriteContext], CommandResult],
        help_text: str = "",
    ) -> None:
        """Register a command under one or more names (with or without leading ':')."""
        defn = _CommandDef(
            names=[n.lstrip(":") for n in names],
            handler=handler,
            help_text=help_text,
        )
        self._defs.append(defn)
        for n in defn.names:
            self._index[n.lower()] = defn

    def dispatch(self, raw: str, ctx: WriteContext) -> CommandResult | None:
        """
        If raw starts with ':', parse and dispatch.
        Returns None if raw is not a command.
        """
        raw = raw.strip()
        if not raw.startswith(":"):
            return None
        # Multi-line input is never a command — it's a segment that starts with ':'
        if "\n" in raw:
            return None
        parts = raw[1:].split(None, 1)
        cmd_name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        defn = self._index.get(cmd_name)
        if defn is None:
            return CommandResult(
                output=f"Unknown command :{cmd_name}  (type :help for a list)",
                kind="error",
            )
        return defn.handler(arg, ctx)

    def help_lines(self) -> list[str]:
        seen: set[int] = set()
        lines: list[str] = []
        for defn in self._defs:
            key = id(defn)
            if key not in seen:
                seen.add(key)
                names_str = "  ".join(f":{n}" for n in defn.names)
                lines.append(f"  {names_str:<30} {defn.help_text}")
        return lines
