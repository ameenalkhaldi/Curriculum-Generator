#!/usr/bin/env python3
"""
Rebuild memory/index.json from already generated lessons.
Useful when you delete the index or import a batch of JSON files manually.
"""

import json
import pathlib
import time
import uuid

import typer

from author_lessons import embed_texts, openai_client, GENERATED
from memory import MemoryStore, normalize_slug

app = typer.Typer(help="Recreate the memory index from lesson JSON files.")

def iter_lessons(root: pathlib.Path):
    if not root.exists():
        raise SystemExit(f"{root} does not exist.")
    for path in root.rglob("*.json"):
        if path.is_file():
            yield path

@app.command()
def run(
    source: pathlib.Path = typer.Option(GENERATED, help="Root folder that contains lesson JSONs (default: ./generated)"),
    output: pathlib.Path = typer.Option(pathlib.Path("memory/index.json"), help="Where to store the rebuilt index"),
    clear: bool = typer.Option(True, help="Start from an empty index instead of appending"),
) -> None:
    """
    Rebuild the vector index by embedding every lesson JSON under `source`.
    """
    client = openai_client()
    mem = MemoryStore(output)
    if clear:
        mem.index["items"] = []

    lesson_files = list(iter_lessons(source))
    if not lesson_files:
        typer.echo(f"No lesson JSON files found under {source}")
        return

    typer.echo(f"Embedding {len(lesson_files)} lessons...")
    for lesson_path in lesson_files:
        try:
            data = json.loads(lesson_path.read_text(encoding="utf-8"))
        except Exception as exc:
            typer.echo(f"[WARN] Could not read {lesson_path}: {exc}", err=True)
            continue

        module = data.get("module") or lesson_path.parent.name
        slug = normalize_slug(data.get("slug") or data.get("id") or lesson_path.stem)
        title = data.get("title", lesson_path.stem)

        full_text = f"{title}\n" + "\n".join(
            json.dumps(block, ensure_ascii=False) for block in data.get("blocks", [])
        )
        try:
            vector = embed_texts(client, [full_text])[0]
        except Exception as exc:
            typer.echo(f"[WARN] Could not embed {lesson_path}: {exc}", err=True)
            continue

        mem.add_item(
            item_id=str(uuid.uuid4()),
            title=title,
            slug=slug,
            module=module,
            path=str(lesson_path.resolve()),
            vector=vector,
            meta={"created_at": int(time.time())},
        )

    mem.save()
    typer.echo(f"✓ Rebuilt index with {len(mem.index.get('items', []))} items.")


if __name__ == "__main__":
    app()
