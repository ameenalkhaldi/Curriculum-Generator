#!/usr/bin/env python3
"""
Simple interactive UI for the Kitabite lesson authoring CLI.
Allows you to choose commands from a menu instead of typing long shell commands.
"""

import pathlib
from typing import Optional

import typer

from author_lessons import (
    init_style as init_style_cmd,
    author_one as author_one_cmd,
    author_batch as author_batch_cmd,
    ask as ask_cmd,
    bundle_curriculum as bundle_curriculum_cmd,
    get_source_language,
    get_target_language,
    resolve_curriculum_id,
)
from generate_curriculum import plan as plan_curriculum
from reindex_memory import run as reindex_memory

app = typer.Typer(help="Interactive menu for Kitabite lesson generation")


def _prompt_path(message: str, must_exist: bool = True, default: Optional[str] = None) -> pathlib.Path:
    while True:
        value = typer.prompt(message, default=default or "").strip()
        if not value:
            typer.echo("Please enter a path.", err=True)
            continue
        path = pathlib.Path(value).expanduser()
        if must_exist and not path.exists():
            typer.echo(f"I couldn't find that file: {path}", err=True)
            continue
        return path


def _prompt_optional(message: str, default_hint: Optional[str] = None) -> Optional[str]:
    hint = f" (press Enter to keep '{default_hint}')" if default_hint else ""
    value = typer.prompt(f"{message}{hint}", default="").strip()
    return value or None


def _current_defaults() -> tuple[str, str, str]:
    src = get_source_language()
    tgt = get_target_language()
    curr_id = resolve_curriculum_id(None, src, tgt)
    return src, tgt, curr_id


def handle_init_style() -> None:
    typer.echo("\n[Step] Point us to your reference lesson or style guide.")
    typer.echo("This file teaches the model your preferred tone, structure, and terminology.")
    path = _prompt_path("Where is the style/lesson markdown file?", must_exist=True)
    init_style_cmd(from_file=path)


def handle_author_one() -> None:
    typer.echo("\n[Author a single lesson]")
    typer.echo("We'll ask for the basics about the lesson and any special notes.")
    module = typer.prompt("Module name (e.g., 'Basic Concepts')").strip()
    lesson = typer.prompt("Lesson title shown to learners").strip()
    slug = typer.prompt("URL-friendly slug (e.g., 'nouns-cases-301')").strip()
    brief = _prompt_optional("Extra coaching for the model (optional)")
    src_def, tgt_def, curr_def = _current_defaults()
    typer.echo(f"Current language direction: explain in {src_def}, teach {tgt_def}.")
    source_lang = _prompt_optional("Explanation language (what the prose should be in)", src_def)
    target_lang = _prompt_optional("Language you're teaching (used inside examples)", tgt_def)
    curriculum_id = _prompt_optional("Folder label for this curriculum run", curr_def)

    author_one_cmd(
        module=module,
        lesson=lesson,
        slug=slug,
        brief=brief,
        source_lang=source_lang,
        target_lang=target_lang,
        curriculum_id=curriculum_id,
    )


def handle_generate_curriculum() -> None:
    typer.echo("\n[Draft a curriculum plan]")
    typer.echo("We’ll ask a few high-level questions and draft a JSON curriculum you can feed into author-batch.")
    default_output = "curricula/new-curriculum.json"
    output_path = _prompt_path(
        f"Where should the curriculum JSON be saved? (default: {default_output})",
        must_exist=False,
        default=default_output,
    )
    src_def, tgt_def, _ = _current_defaults()
    source_lang = _prompt_optional("Learners' native language (explanations)", src_def) or src_def
    target_lang = _prompt_optional("Language they are learning", tgt_def) or tgt_def

    def _prompt_int(msg: str, default: int) -> int:
        while True:
            raw = typer.prompt(f"{msg} (default {default})", default=str(default)).strip()
            try:
                val = int(raw)
                if val <= 0:
                    raise ValueError
                return val
            except ValueError:
                typer.echo("Please enter a positive integer.", err=True)

    level_count = _prompt_int("How many proficiency levels?", 4)
    modules_per_level = _prompt_int("Approx. modules per level?", 4)
    lessons_per_module = _prompt_int("Approx. lessons per module?", 4)

    level_notes: list[str] = []
    if typer.confirm("Add level-specific guidance?", default=False):
        for idx in range(level_count):
            note = typer.prompt(
                f"Guidance for Level {idx + 1} (leave blank for none)",
                default="",
            ).strip()
            if note:
                level_notes.append(note)

    focus = _prompt_optional("Overall focus (e.g., travel, academic, business)")
    audience = typer.prompt("Target audience ('university' or 'high-school')", default="university").strip().lower()
    if audience not in ("university", "high-school"):
        typer.echo("Unrecognized audience; defaulting to 'university'.", err=True)
        audience = "university"

    plan_curriculum(
        output=output_path,
        source_lang=source_lang,
        target_lang=target_lang,
        level_count=level_count,
        modules_per_level=modules_per_level,
        lessons_per_module=lessons_per_module,
        level_note=level_notes,
        focus=focus,
        audience=audience,
    )


def handle_author_batch() -> None:
    typer.echo("\n[Author a full curriculum]")
    typer.echo("You'll point to a curriculum JSON file and we will generate every lesson inside it.")
    curriculum_path = _prompt_path("Where is the curriculum JSON?", must_exist=True, default="samples/curriculum.json")
    filter_module = _prompt_optional("Only run a specific module? (leave blank for all modules)")
    start_at = _prompt_optional("Resume from lesson slug (leave blank to start at the top)")
    src_def, tgt_def, curr_def = _current_defaults()
    typer.echo(f"Current language direction: explain in {src_def}, teach {tgt_def}.")
    source_lang = _prompt_optional("Explanation language", src_def)
    target_lang = _prompt_optional("Language being taught", tgt_def)
    curriculum_id = _prompt_optional("Folder label for generated lessons", curr_def)
    bundle_answer = _prompt_optional("Save everything into one JSON at the end? (path like final/curriculum.id.json)")
    bundle_path = pathlib.Path(bundle_answer).expanduser() if bundle_answer else None

    author_batch_cmd(
        curriculum=curriculum_path,
        filter_module=filter_module,
        start_at=start_at,
        source_lang=source_lang,
        target_lang=target_lang,
        curriculum_id=curriculum_id,
        bundle_output=bundle_path,
    )


def handle_ask() -> None:
    typer.echo("\n[Search previous lessons]")
    typer.echo("Ask a question and the assistant will answer using only the lessons you've already generated.")
    question = typer.prompt("What do you want to know?").strip()
    ask_cmd(q=question)


def handle_bundle() -> None:
    typer.echo("\n[Bundle lessons into one deliverable]")
    typer.echo("This stitches every per-lesson JSON back into the curriculum structure.")
    curriculum_path = _prompt_path("Which curriculum plan should we follow?", must_exist=True, default="samples/curriculum.json")
    src_def, tgt_def, curr_def = _current_defaults()
    typer.echo(f"Current language direction: explain in {src_def}, teach {tgt_def}.")
    source_lang = _prompt_optional("Explanation language", src_def)
    target_lang = _prompt_optional("Language being taught", tgt_def)
    curriculum_id = _prompt_optional("Which curriculum folder holds the lessons?", curr_def)
    output_path = _prompt_path("Where should the combined JSON be saved?", must_exist=False)

    bundle_curriculum_cmd(
        curriculum=curriculum_path,
        output=output_path,
        source_lang=source_lang,
        target_lang=target_lang,
        curriculum_id=curriculum_id,
    )


def handle_reindex_memory() -> None:
    typer.echo("\n[Rebuild memory index]")
    typer.echo("Use this if you deleted memory/index.json or imported lessons manually.")
    source_default = str(GENERATED)
    source = _prompt_path(f"Where should we scan for lessons? (default: {source_default})", must_exist=True, default=source_default)
    output = _prompt_path("Where should the index be saved? (default: memory/index.json)", must_exist=False, default="memory/index.json")
    clear = typer.confirm("Clear existing entries before rebuilding?", default=True)
    reindex_memory(source=source, output=output, clear=clear)


MENU_ITEMS = {
    "1": ("Save a reference style lesson", handle_init_style),
    "2": ("Draft a curriculum plan", handle_generate_curriculum),
    "3": ("Write one lesson", handle_author_one),
    "4": ("Generate an entire curriculum", handle_author_batch),
    "5": ("Ask what the system already taught", handle_ask),
    "6": ("Combine lessons into a single JSON", handle_bundle),
    "7": ("Rebuild the memory index", handle_reindex_memory),
    "q": ("Quit", None),
}


@app.command()
def run() -> None:
    """Launch the interactive UI."""
    typer.echo("Kitabite Authoring UI\n======================")
    while True:
        typer.echo("\nSelect an action:")
        for key, (label, _) in MENU_ITEMS.items():
            typer.echo(f"  {key}) {label}")
        choice = typer.prompt("Enter choice").strip().lower()
        if choice in ("q", "quit", "exit"):
            typer.echo("Goodbye!")
            break
        action = MENU_ITEMS.get(choice)
        if not action:
            typer.echo("Invalid choice.", err=True)
            continue
        _, handler = action
        try:
            handler()
        except SystemExit as exc:
            typer.echo(f"[ERROR] {exc}", err=True)
        except KeyboardInterrupt:
            typer.echo("\n[Cancelled]", err=True)


if __name__ == "__main__":
    app()
