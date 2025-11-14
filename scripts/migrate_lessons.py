#!/usr/bin/env python3
"""
Migration helper to normalize previously generated lessons.
Use this after tightening template requirements (e.g., flatten text block data).
"""

import json
import pathlib
from typing import Any, Dict

import typer

app = typer.Typer(help="Fix earlier lessons so they match the latest JSON schema.")


TEXT_HEADER_KEYS = ("heading", "title", "subtitle")
TEXT_BODY_KEYS = ("content", "text", "body", "value", "description")


def flatten_text_data(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return "\n".join(str(item).strip() for item in data if str(item).strip())
    if isinstance(data, dict):
        parts = []
        for key in TEXT_HEADER_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        body_chunks = []
        for key in TEXT_BODY_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                body_chunks.append(value.strip())
        if body_chunks:
            parts.append("\n\n".join(body_chunks))
        others = [
            (k, v)
            for k, v in data.items()
            if k not in (*TEXT_HEADER_KEYS, *TEXT_BODY_KEYS)
        ]
        if others:
            extra = "\n".join(f"{k}: {v}" for k, v in others if v is not None)
            if extra:
                parts.append(extra)
        return "\n\n".join(parts).strip()
    return str(data)


def normalize_lesson(path: pathlib.Path, dry_run: bool) -> bool:
    changed = False
    data = json.loads(path.read_text(encoding="utf-8"))
    for block in data.get("blocks", []):
        if block.get("type") == "text":
            text_data = block.get("data")
            flattened = flatten_text_data(text_data)
            if flattened and flattened != text_data:
                block["data"] = flattened
                changed = True
    if changed and not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


@app.command()
def run(
    root: pathlib.Path = typer.Option(pathlib.Path("generated"), help="Parent directory to scan (default: ./generated)"),
    dry_run: bool = typer.Option(False, help="Only report files that would change"),
) -> None:
    """
    Flatten text block data so every block uses a simple string (no nested objects).
    """
    if not root.exists():
        raise SystemExit(f"{root} does not exist.")
    target_files = list(root.rglob("*.json"))
    if not target_files:
        typer.echo("No lesson JSON files found.")
        return
    changed_files = 0
    for lesson_file in target_files:
        try:
            if normalize_lesson(lesson_file, dry_run=dry_run):
                changed_files += 1
                typer.echo(f"{'[DRY-RUN] ' if dry_run else ''}Updated {lesson_file}")
        except Exception as exc:
            typer.echo(f"[WARN] Could not process {lesson_file}: {exc}", err=True)
    typer.echo(f"Done. {'Would update' if dry_run else 'Updated'} {changed_files} files.")


if __name__ == "__main__":
    app()
