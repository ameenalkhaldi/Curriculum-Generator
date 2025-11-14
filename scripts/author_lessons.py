#!/usr/bin/env python3
"""
Kitabite Lesson Authoring CLI

Features
- Author one lesson or a batch from a curriculum.json
- Persists a style guide + lesson embeddings to keep format and voice consistent
- RAG: ask about previously authored lessons
- Outputs JSON ready for your frontend schema (blocks + quiz + tagged questions)

Usage (examples):
  export OPENAI_API_KEY=sk-...
  python scripts/author_lessons.py init-style --from-file samples/seed_lesson.md
  python scripts/author_lessons.py author-one --module "Nouns" --lesson "الاسم المرفوع والمنصوب والمجرور" --slug "nouns-cases-301"
  python scripts/author_lessons.py author-batch --curriculum ./curriculum.json
  python scripts/author_lessons.py ask --q "What did we say about جملة القسم and the role of لام القسم?"

Outputs:
  - ./generated/<module_slug>/<lesson_slug>.json
  - ./memory/style.md
  - ./memory/index.json (metadata + embeddings)
"""

import os
import json
import uuid
import time
import pathlib
from typing import List, Dict, Any, Optional

import typer

from templates import SYSTEM_STYLE_TEMPLATE, LESSON_PROMPT_TEMPLATE, RAG_ANSWER_PROMPT
from memory import MemoryStore, normalize_slug

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    # OpenAI SDK v1
    from openai import OpenAI
except ImportError:
    raise SystemExit("Please: pip install openai typer python-dotenv")

app = typer.Typer(help="Kitabite lesson authoring CLI")

ROOT = pathlib.Path(__file__).resolve().parents[1]
if load_dotenv:
    load_dotenv(ROOT / ".env")
GENERATED = ROOT / "generated"
MEMORY_DIR = ROOT / "memory"
STYLE_PATH = MEMORY_DIR / "style.md"
INDEX_PATH = MEMORY_DIR / "index.json"
DEFAULT_SOURCE_LANG = "English"
DEFAULT_TARGET_LANG = "Arabic"


def resolve_curriculum_id(explicit: Optional[str], source_lang: str, target_lang: str) -> str:
    env_value = os.environ.get("CURRICULUM_ID")
    if explicit:
        return normalize_slug(explicit)
    if env_value:
        return normalize_slug(env_value)
    # fall back to source-to-target pattern
    return normalize_slug(f"{source_lang}-to-{target_lang}")


def get_source_language(override: Optional[str] = None) -> str:
    return override or os.environ.get("CURRICULUM_SOURCE_LANG", DEFAULT_SOURCE_LANG)


def get_target_language(override: Optional[str] = None) -> str:
    return override or os.environ.get("CURRICULUM_TARGET_LANG", DEFAULT_TARGET_LANG)


def openai_client() -> "OpenAI":
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=key)


def model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # fast, good structure
def embed_model() -> str:
    return os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")


# ---------- Helpers ----------

def save_json(output_path: pathlib.Path, data: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def call_chat(client: OpenAI, sys: str, user: str, seed: Optional[str] = None) -> str:
    messages = [{"role": "system", "content": sys}]
    if seed:
        messages.append({"role": "user", "content": seed})
    messages.append({"role": "user", "content": user})

    resp = client.chat.completions.create(
        model=model_name(),
        messages=messages,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def embed_texts(client: OpenAI, texts: List[str]) -> List[List[float]]:
    resp = client.embeddings.create(model=embed_model(), input=texts)
    return [d.embedding for d in resp.data]


def bundle_curriculum_output(curriculum_path: pathlib.Path, curriculum_id: str, output_path: pathlib.Path) -> None:
    with open(curriculum_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    base_dir = GENERATED / curriculum_id
    if not base_dir.exists():
        raise SystemExit(f"No generated lessons found for curriculum_id={curriculum_id} under {base_dir}")

    bundled = {"levels": []}
    missing = []

    seen_level_ids = set()
    seen_module_ids = set()

    for level in plan.get("levels", []):
        level_id = level.get("id") or normalize_slug(level.get("title", f"level-{len(seen_level_ids)+1}")) or f"level-{len(seen_level_ids)+1}"
        if level_id in seen_level_ids:
            level_id = f"{level_id}-{len(seen_level_ids)+1}"
        seen_level_ids.add(level_id)

        level_copy = {k: v for k, v in level.items() if k != "modules"}
        level_copy["id"] = level_id
        modules_out = []
        for module in level.get("modules", []):
            module_id = module.get("id") or module.get("slug") or normalize_slug(module.get("title", f"module-{len(seen_module_ids)+1}")) or f"module-{len(seen_module_ids)+1}"
            if module_id in seen_module_ids:
                module_id = f"{module_id}-{len(seen_module_ids)+1}"
            seen_module_ids.add(module_id)

            module_copy = {k: v for k, v in module.items() if k != "lessons"}
            module_copy["id"] = module_id
            mod_slug = module.get("slug") or normalize_slug(module.get("title", "module"))
            lessons_out = []
            for lesson in module.get("lessons", []):
                lesson_slug = normalize_slug(lesson.get("slug") or lesson.get("title", "lesson"))
                lesson_path = base_dir / mod_slug / f"{lesson_slug}.json"
                if lesson_path.exists():
                    lessons_out.append(json.loads(lesson_path.read_text(encoding="utf-8")))
                else:
                    missing.append(str(lesson_path))
            module_copy["lessons"] = lessons_out
            modules_out.append(module_copy)
        level_copy["modules"] = modules_out
        bundled["levels"].append(level_copy)

    if missing:
        raise SystemExit(f"Cannot bundle curriculum. Missing lesson files: {', '.join(missing)}")

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundled, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- Commands ----------

@app.command()
def init_style(from_file: pathlib.Path = typer.Option(..., exists=True, readable=True, help="A seed lesson or style doc (md)")):
    """
    Initialize style memory from a seed file (your favorite authored lesson or style guide).
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    STYLE_PATH.write_text(from_file.read_text(encoding="utf-8"), encoding="utf-8")
    if not INDEX_PATH.exists():
        INDEX_PATH.write_text(json.dumps({"items": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"✓ Style memory initialized from {from_file}")


@app.command()
def author_one(
    module: str = typer.Option(..., help="Module title (e.g., Nouns)"),
    lesson: str = typer.Option(..., help="Lesson title in your UI"),
    slug: str = typer.Option(..., help="Unique lesson slug (e.g., nouns-cases-301)"),
    brief: Optional[str] = typer.Option(None, help="Optional extra instructions for this lesson"),
    source_lang: Optional[str] = typer.Option(None, help="Learner's base language (defaults to CURRICULUM_SOURCE_LANG env)"),
    target_lang: Optional[str] = typer.Option(None, help="Language being taught (defaults to CURRICULUM_TARGET_LANG env)"),
    curriculum_id: Optional[str] = typer.Option(None, help="Folder/bundle identifier (defaults to <source>-to-<target>)"),
):
    """
    Author a single lesson JSON (blocks + quiz with tags) with consistent style.
    """
    client = openai_client()
    mem = MemoryStore(INDEX_PATH)
    style = STYLE_PATH.read_text(encoding="utf-8") if STYLE_PATH.exists() else ""

    # Retrieve top 5 nearest previous lessons as style/context exemplars
    neighbors = mem.search(queries=[lesson], k=5)
    neighbor_summaries = []
    for n in neighbors:
        # load partial lesson header to show the model the same structure
        try:
            with open(n["path"], "r", encoding="utf-8") as f:
                j = json.load(f)
            neighbor_summaries.append({
                "id": j.get("id"),
                "title": j.get("title"),
                "sample_block_types": [b.get("type") for b in j.get("blocks", [])[:5]],
                "sample_quiz_kinds": [q.get("type") for q in j.get("quiz", {}).get("questions", [])[:5]],
            })
        except Exception:
            continue

    src_language = get_source_language(source_lang)
    tgt_language = get_target_language(target_lang)

    user_prompt = LESSON_PROMPT_TEMPLATE.format(
        module_title=module,
        lesson_title=lesson,
        lesson_slug=slug,
        source_language=src_language,
        target_language=tgt_language,
        extra_instructions=brief or "",
        neighbor_json=json.dumps(neighbor_summaries, ensure_ascii=False),
    )

    system_prompt = SYSTEM_STYLE_TEMPLATE.format(
        style_guide=style,
        source_language=src_language,
        target_language=tgt_language,
    )

    raw = call_chat(client, sys=system_prompt, user=user_prompt)
    try:
        data = json.loads(raw)
    except Exception as e:
        typer.echo(raw)
        raise SystemExit(f"Model did not return valid JSON: {e}")

    # Validate minimal shape
    for k in ("id", "title", "blocks", "quiz"):
        if k not in data:
            raise SystemExit(f"Missing required key in lesson JSON: {k}")
    if "questions" not in data["quiz"]:
        raise SystemExit("Missing quiz.questions array")

    # Persist
    module_slug = normalize_slug(module)
    lesson_slug = normalize_slug(slug or lesson)
    curr_id = resolve_curriculum_id(curriculum_id, src_language, tgt_language)
    out_path = GENERATED / curr_id / module_slug / f"{lesson_slug}.json"
    save_json(out_path, data)

    # Index to memory (embedding on concatenated content)
    full_text_for_embed = f"{data.get('title','')}\n" + "\n".join(
        [json.dumps(b, ensure_ascii=False) for b in data.get("blocks", [])]
    )
    emb = embed_texts(client, [full_text_for_embed])[0]
    mem.add_item(
        item_id=str(uuid.uuid4()),
        title=data.get("title", ""),
        slug=lesson_slug,
        module=module,
        path=str(out_path),
        vector=emb,
        meta={"created_at": int(time.time())}
    )
    mem.save()

    typer.echo(f"✓ Authored: {out_path}")


@app.command()
def author_batch(
    curriculum: pathlib.Path = typer.Option(..., exists=True, readable=True, help="Curriculum JSON with modules/lessons"),
    filter_module: Optional[str] = typer.Option(None, help="Only this module title/slug"),
    start_at: Optional[str] = typer.Option(None, help="Start from this lesson slug"),
    source_lang: Optional[str] = typer.Option(None, help="Learner's base language (defaults to CURRICULUM_SOURCE_LANG env)"),
    target_lang: Optional[str] = typer.Option(None, help="Language being taught (defaults to CURRICULUM_TARGET_LANG env)"),
    curriculum_id: Optional[str] = typer.Option(None, help="Folder/bundle identifier (defaults to <source>-to-<target>)"),
    bundle_output: Optional[pathlib.Path] = typer.Option(None, help="Optional path to write a merged curriculum JSON after generation"),
):
    """
    Author all lessons from a curriculum file.
    Expected schema (minimal):
    {
      "levels":[
        {"title":"Level 1","modules":[
          {"title":"Module A","lessons":[{"title":"...", "slug":"..."}, ...]}
        ]}...
      ]
    }
    """
    client = openai_client()
    mem = MemoryStore(INDEX_PATH)
    style = STYLE_PATH.read_text(encoding="utf-8") if STYLE_PATH.exists() else ""

    with open(curriculum, "r", encoding="utf-8") as f:
        plan = json.load(f)

    started = start_at is None
    authored = 0

    src_language = get_source_language(source_lang)
    tgt_language = get_target_language(target_lang)
    curr_id = resolve_curriculum_id(curriculum_id, src_language, tgt_language)

    for level in plan.get("levels", []):
        for module in level.get("modules", []):
            mod_title = module.get("title", "")
            mod_slug = normalize_slug(mod_title)
            if filter_module and filter_module not in (mod_title, mod_slug):
                continue

            for les in module.get("lessons", []):
                title = les.get("title", "")
                slug = les.get("slug") or normalize_slug(title)
                if not started:
                    if slug == start_at:
                        started = True
                    else:
                        continue

                # RAG neighbors per lesson
                neighbors = mem.search(queries=[title], k=5)
                neighbor_summaries = []
                for n in neighbors:
                    try:
                        with open(n["path"], "r", encoding="utf-8") as f:
                            j = json.load(f)
                        neighbor_summaries.append({
                            "id": j.get("id"),
                            "title": j.get("title"),
                            "sample_block_types": [b.get("type") for b in j.get("blocks", [])[:5]],
                            "sample_quiz_kinds": [q.get("type") for q in j.get("quiz", {}).get("questions", [])[:5]],
                        })
                    except Exception:
                        continue

                user_prompt = LESSON_PROMPT_TEMPLATE.format(
                    module_title=mod_title,
                    lesson_title=title,
                    lesson_slug=slug,
                    source_language=src_language,
                    target_language=tgt_language,
                    extra_instructions=les.get("brief") or "",
                    neighbor_json=json.dumps(neighbor_summaries, ensure_ascii=False),
                )
                system_prompt = SYSTEM_STYLE_TEMPLATE.format(
                    style_guide=style,
                    source_language=src_language,
                    target_language=tgt_language,
                )

                raw = client.chat.completions.create(
                    model=model_name(),
                    messages=[{"role": "system", "content": system_prompt},
                              {"role": "user", "content": user_prompt}],
                    response_format={"type": "json_object"},
                ).choices[0].message.content

                try:
                    data = json.loads(raw)
                except Exception as e:
                    typer.echo(f"[WARN] Invalid JSON for {slug}: {e}")
                    typer.echo(raw)
                    continue

                # Persist
                out_path = GENERATED / curr_id / mod_slug / f"{normalize_slug(slug)}.json"
                save_json(out_path, data)

                # Index
                full_text = f"{data.get('title','')}\n" + "\n".join(
                    [json.dumps(b, ensure_ascii=False) for b in data.get("blocks", [])]
                )
                emb = embed_texts(client, [full_text])[0]
                mem.add_item(
                    item_id=str(uuid.uuid4()),
                    title=data.get("title", ""),
                    slug=normalize_slug(slug),
                    module=mod_title,
                    path=str(out_path),
                    vector=emb,
                    meta={"created_at": int(time.time())}
                )
                authored += 1
                # be nice to rate limits
                time.sleep(0.4)

    mem.save()
    typer.echo(f"✓ Batch complete. Authored: {authored} lessons.")

    if bundle_output:
        bundle_curriculum_output(curriculum, curr_id, bundle_output)
        typer.echo(f"✓ Bundled curriculum saved to {bundle_output}")


@app.command()
def bundle_curriculum(
    curriculum: pathlib.Path = typer.Option(..., exists=True, readable=True, help="Curriculum JSON (same file used for authoring)"),
    output: pathlib.Path = typer.Option(..., help="Path to write merged curriculum JSON"),
    source_lang: Optional[str] = typer.Option(None, help="Learner's base language (defaults to CURRICULUM_SOURCE_LANG env)"),
    target_lang: Optional[str] = typer.Option(None, help="Language being taught (defaults to CURRICULUM_TARGET_LANG env)"),
    curriculum_id: Optional[str] = typer.Option(None, help="Folder/bundle identifier (defaults to <source>-to-<target>)"),
):
    """
    Merge all per-lesson JSON files into a single curriculum JSON.
    """
    src_language = get_source_language(source_lang)
    tgt_language = get_target_language(target_lang)
    curr_id = resolve_curriculum_id(curriculum_id, src_language, tgt_language)
    bundle_curriculum_output(curriculum, curr_id, output)
    typer.echo(f"✓ Bundled lessons from {curr_id} into {output}")


@app.command()
def ask(q: str = typer.Option(..., help="Question about previously authored lessons")):
    """
    Ask about things the system has written before (RAG over memory).
    """
    client = openai_client()
    mem = MemoryStore(INDEX_PATH)
    style = STYLE_PATH.read_text(encoding="utf-8") if STYLE_PATH.exists() else ""

    neighbors = mem.search(queries=[q], k=6)
    context_docs = []
    for n in neighbors:
        try:
            with open(n["path"], "r", encoding="utf-8") as f:
                j = json.load(f)
            context_docs.append({
                "title": j.get("title"),
                "id": j.get("id"),
                "blocks": j.get("blocks", [])[:6],
                "quiz_sample": j.get("quiz", {}).get("questions", [])[:6]
            })
        except Exception:
            continue

    user_prompt = RAG_ANSWER_PROMPT.format(
        query=q,
        retrieved=json.dumps(context_docs, ensure_ascii=False, indent=2)
    )
    system_prompt = f"You are Kitabite's curriculum librarian. Keep answers concise but accurate. Maintain the same voice and definitions. Style guide:\n\n{style}".strip()

    resp = client.chat.completions.create(
        model=model_name(),
        messages=[{"role":"system", "content": system_prompt},
                  {"role":"user", "content": user_prompt}],
    )
    print(resp.choices[0].message.content)


if __name__ == "__main__":
    app()
