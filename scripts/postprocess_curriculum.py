#!/usr/bin/env python3
"""
Utility for editing every string inside bundled curriculum/lesson JSON files.

Instructions live in a small JSON file (see scripts/rules/remove_english_glosses.json).
Each instruction describes how to transform matching paths, so you can batch‑remove or
add content without regenerating the curriculum.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import typer

app = typer.Typer(help="Apply text cleanup instructions across curriculum JSON files.")


def iter_json_files(target: pathlib.Path) -> Iterable[pathlib.Path]:
    if target.is_file():
        if target.suffix.lower() == ".json":
            yield target
        return
    for path in target.rglob("*.json"):
        if path.is_file():
            yield path


def dotted_path(parent: str, key: str) -> str:
    if parent in ("", "."):
        return key
    if key.startswith("["):
        return f"{parent}{key}"
    return f"{parent}.{key}"


@dataclass
class CleanupInstruction:
    kind: str
    description: str
    paths: List[str] = field(default_factory=list)
    exclude_paths: List[str] = field(default_factory=list)
    literal: Optional[str] = None
    replacement: Optional[str] = None
    pattern: Optional[re.Pattern[str]] = None
    append_text: Optional[str] = None
    prepend_text: Optional[str] = None
    case_sensitive: bool = True
    count: int = 0

    @classmethod
    def from_dict(cls, spec: Dict[str, Any]) -> "CleanupInstruction":
        kind = spec.get("type")
        if not kind:
            raise ValueError("Instruction missing 'type'.")
        description = spec.get("description", kind)
        inst = cls(
            kind=kind,
            description=description,
            paths=list(spec.get("paths", [])),
            exclude_paths=list(spec.get("exclude_paths", [])),
            case_sensitive=spec.get("case_sensitive", True),
        )
        if kind == "replace":
            inst.literal = spec.get("find")
            inst.replacement = spec.get("replacement", "")
            if inst.literal is None:
                raise ValueError("Replace instruction requires 'find'.")
        elif kind == "regex_sub":
            pattern = spec.get("pattern")
            if not pattern:
                raise ValueError("regex_sub instruction requires 'pattern'.")
            flags_value = 0
            for flag in spec.get("flags", []):
                flag_upper = flag.upper()
                if flag_upper == "IGNORECASE":
                    flags_value |= re.IGNORECASE
                elif flag_upper == "MULTILINE":
                    flags_value |= re.MULTILINE
                elif flag_upper == "DOTALL":
                    flags_value |= re.DOTALL
                else:
                    raise ValueError(f"Unsupported regex flag '{flag}'.")
            inst.pattern = re.compile(pattern, flags=flags_value)
            inst.replacement = spec.get("replacement", "")
        elif kind == "append":
            inst.append_text = spec.get("text", "")
        elif kind == "prepend":
            inst.prepend_text = spec.get("text", "")
        else:
            raise ValueError(f"Unsupported instruction type '{kind}'.")
        return inst

    def applies_to_path(self, path: str) -> bool:
        if self.paths and not any(token in path for token in self.paths):
            return False
        if self.exclude_paths and any(token in path for token in self.exclude_paths):
            return False
        return True

    def apply(self, text: str, path: str) -> Tuple[str, int]:
        if not self.applies_to_path(path):
            return text, 0
        if self.kind == "replace":
            old = self.literal or ""
            new = self.replacement or ""
            if not old:
                return text, 0
            if self.case_sensitive:
                occurrences = text.count(old)
                if not occurrences:
                    return text, 0
                return text.replace(old, new), occurrences
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            new_text, occurrences = pattern.subn(new, text)
            return new_text, occurrences
        if self.kind == "regex_sub":
            pattern = self.pattern
            if not pattern:
                return text, 0
            new_text, occurrences = pattern.subn(self.replacement or "", text)
            return new_text, occurrences
        if self.kind == "append":
            addition = self.append_text or ""
            if not addition:
                return text, 0
            if text.endswith(addition):
                return text, 0
            return f"{text}{addition}", 1
        if self.kind == "prepend":
            addition = self.prepend_text or ""
            if not addition:
                return text, 0
            if text.startswith(addition):
                return text, 0
            return f"{addition}{text}", 1
        return text, 0


def load_instructions(path: pathlib.Path) -> List[CleanupInstruction]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(content, dict):
        instructions_data = content.get("instructions") or content.get("rules") or []
    else:
        instructions_data = content
    instructions = [CleanupInstruction.from_dict(item) for item in instructions_data]
    if not instructions:
        raise ValueError("No instructions defined.")
    return instructions


def walk(value: Any, path: str, instructions: List[CleanupInstruction]) -> Tuple[Any, bool]:
    changed = False
    if isinstance(value, dict):
        for key, child in list(value.items()):
            new_path = dotted_path(path, key)
            new_child, child_changed = walk(child, new_path, instructions)
            if child_changed:
                value[key] = new_child
                changed = True
        return value, changed
    if isinstance(value, list):
        for idx, child in enumerate(value):
            new_path = dotted_path(path, f"[{idx}]")
            new_child, child_changed = walk(child, new_path, instructions)
            if child_changed:
                value[idx] = new_child
                changed = True
        return value, changed
    if isinstance(value, str):
        new_value = value
        local_changed = False
        for inst in instructions:
            new_value, count = inst.apply(new_value, path)
            if count:
                inst.count += count
                local_changed = True
        return new_value, local_changed
    return value, False


def process_file(
    file_path: pathlib.Path,
    base_dir: pathlib.Path,
    instructions: List[CleanupInstruction],
    dry_run: bool,
    output_dir: Optional[pathlib.Path],
    target_is_dir: bool,
) -> bool:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    _, changed = walk(data, "$", instructions)
    if not changed:
        return False
    if output_dir:
        if target_is_dir:
            relative_name: pathlib.Path | str = file_path.relative_to(base_dir)
        else:
            relative_name = file_path.name
        destination = output_dir / relative_name
    else:
        destination = file_path
    if dry_run:
        typer.echo(f"[DRY-RUN] Would update {file_path}")
        return True
    if output_dir:
        destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"Updated {destination}")
    return True


@app.command()
def run(
    target: pathlib.Path = typer.Argument(..., exists=True, readable=True, help="Curriculum JSON file or directory."),
    instructions_path: pathlib.Path = typer.Option(..., "--instructions", "-i", exists=True, readable=True, help="JSON file describing replacements."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview files that would change without writing."),
    output_dir: Optional[pathlib.Path] = typer.Option(None, "--output-dir", help="Write modified files to this directory instead of in-place."),
) -> None:
    """
    Apply a list of cleanup instructions to every JSON string in the target.
    Use dry-run to preview and combine with --output-dir to keep originals untouched.
    """
    instructions = load_instructions(instructions_path)
    files = list(iter_json_files(target))
    if not files:
        raise SystemExit(f"No JSON files found under {target}")
    base_dir = target if target.is_dir() else target.parent
    target_is_dir = target.is_dir()
    changed_files = 0
    for file_path in files:
        try:
            if process_file(
                file_path,
                base_dir=base_dir,
                instructions=instructions,
                dry_run=dry_run,
                output_dir=output_dir,
                target_is_dir=target_is_dir,
            ):
                changed_files += 1
        except Exception as exc:
            typer.echo(f"[WARN] Failed to process {file_path}: {exc}", err=True)
    typer.echo(f"Done. {'Would update' if dry_run else 'Updated'} {changed_files} file(s).")
    typer.echo("Instruction hit counts:")
    for inst in instructions:
        typer.echo(f"- {inst.description}: {inst.count}")


if __name__ == "__main__":
    app()
