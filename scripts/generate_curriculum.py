#!/usr/bin/env python3
"""
Curriculum plan generator.
Creates a curriculum JSON (levels -> modules -> lessons) so you can run author-batch without hand-writing the structure.
"""

import json
import pathlib
from typing import List, Optional

import typer

from author_lessons import openai_client, model_name
from memory import normalize_slug

app = typer.Typer(help="Generate curriculum plans for new language pairs")


PLAN_PROMPT = """Design a curriculum plan for language learners.

Language of instruction (explanations): {source_language}
Language being taught: {target_language}
Audience: {audience_label}

Output JSON with this exact schema:
{{
  "slug": "short-hyphenated-lang-pair-id",
  "title": "{source_language} → {target_language}",
  "languageOfInstruction": "{source_language}",
  "targetLanguage": "{target_language}",
  "levels": [
    {{
      "id": "slug-or-short-id",
      "title": "Human-readable level name",
      "description": "1-2 sentences about this level (optional)",
      "modules": [
        {{
          "id": "module-id",
          "title": "Module title",
          "description": "Optional blurb",
          "lessons": [
            {{
              "title": "Lesson title",
              "slug": "lesson-slug",
              "brief": "Optional instructions or emphasis for that lesson"
            }}
          ]
        }}
      ]
    }}
  ]
}}

Rules:
- Provide exactly {level_count} levels.
- Each level should contain roughly {modules_per_level} modules (±1 is fine if it keeps the story coherent).
- Each module should contain {lessons_per_module} lessons (±1 ok).
- Include lesson briefs when guidance will help the authoring step (e.g., highlight pronunciation pitfalls, comparative grammar, culture notes).
- Slugs must be lowercase, hyphen-separated, and unique across the file.
- Set the slug to a concise lowercase identifier for this language pair (e.g., en-ar, ar-en, en-es).
- The title should read "{source_language} → {target_language}" unless a better, equally short variant is obvious.
- languageOfInstruction MUST exactly match "{source_language}".
- targetLanguage MUST exactly match "{target_language}".
- Lean on communicative competence: mix grammar, usage, mini-dialogues, and culture checkpoints.
- Match the proficiency arc from basic foundations to advanced fluency.
{audience_rules}{level_notes_section}
{extra_focus}

Return ONLY the JSON object. No commentary.
"""


def build_prompt(
    source_language: str,
    target_language: str,
    level_count: int,
    modules_per_level: int,
    lessons_per_module: int,
    level_notes: List[str],
    focus: Optional[str],
    audience: str,
) -> str:
    notes = ""
    if level_notes:
        bullet = "\n".join([f"- Level {idx+1}: {text}" for idx, text in enumerate(level_notes)])
        notes = f"Level-specific guidance:\n{bullet}\n"

    normalized_audience = audience.lower().strip()
    audience_label = "University/college or adult learners"
    audience_rules = ""
    if normalized_audience == "high-school":
        audience_label = "High school students (secondary education)"
        audience_rules = (
            "Audience adjustments:\n"
            "- Keep the scope and tone appropriate for high school learners; prioritize teen-relevant contexts over university seminars.\n"
            "- Avoid linguistics jargon; explain grammar, sounds, and usage in plain language.\n"
        )
    extra = f"Overall emphasis: {focus}" if focus else ""
    return PLAN_PROMPT.format(
        source_language=source_language,
        target_language=target_language,
        level_count=level_count,
        modules_per_level=modules_per_level,
        lessons_per_module=lessons_per_module,
        level_notes_section=notes,
        extra_focus=extra,
        audience_label=audience_label,
        audience_rules=audience_rules,
    )


@app.command()
def plan(
    output: pathlib.Path = typer.Option(..., help="Where to save the generated curriculum JSON"),
    source_lang: str = typer.Option(..., help="Learners' native language (explanations)"),
    target_lang: str = typer.Option(..., help="Language being learned"),
    level_count: int = typer.Option(4, min=1, max=8, help="How many proficiency levels to include"),
    modules_per_level: int = typer.Option(4, min=1, max=8, help="Approximate modules per level"),
    lessons_per_module: int = typer.Option(4, min=1, max=10, help="Approximate lessons per module"),
    level_note: List[str] = typer.Option([], help="Optional text for each level (provide multiple --level-note entries)"),
    focus: Optional[str] = typer.Option(None, help="Overall curricular focus (e.g., business travel, academic writing)"),
    audience: str = typer.Option(
        "university",
        "--audience",
        help="Target audience ('university' or 'high-school'). High-school keeps jargon light and tone teen-friendly.",
        case_sensitive=False,
        show_default=True,
    ),
) -> None:
    """
    Generate a curriculum skeleton ready for author-batch.
    """
    client = openai_client()
    prompt = build_prompt(
        source_language=source_lang,
        target_language=target_lang,
        level_count=level_count,
        modules_per_level=modules_per_level,
        lessons_per_module=lessons_per_module,
        level_notes=level_note,
        focus=focus,
        audience=audience,
    )
    system = "You design structured curricula with clear sequencing."
    resp = client.chat.completions.create(
        model=model_name(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        typer.echo(content)
        raise SystemExit(f"Model returned invalid JSON: {exc}")

    levels = data.get("levels")
    if not isinstance(levels, list):
        raise SystemExit("Model response is missing a 'levels' array.")

    fallback_slug = normalize_slug(f"{source_lang}-to-{target_lang}")
    lang_of_instruction = data.get("languageOfInstruction") or source_lang
    tgt_language = data.get("targetLanguage") or target_lang
    slug = data.get("slug") or fallback_slug or "curriculum"
    title = data.get("title") or f"{lang_of_instruction} → {tgt_language}"

    curriculum = {
        "slug": slug,
        "title": title,
        "languageOfInstruction": lang_of_instruction,
        "targetLanguage": tgt_language,
        "levels": levels,
    }
    if "id" in data:
        curriculum["id"] = data["id"]
    if "meta" in data:
        curriculum["meta"] = data["meta"]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(curriculum, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"✓ Curriculum saved to {output}")


if __name__ == "__main__":
    app()
