# Kitabite Lesson Authoring CLI

Python CLI utilities for authoring Arabic-first lessons, batching an entire curriculum, and querying previously authored content. The workflow keeps a persistent style guide plus lesson embeddings so every new lesson inherits the same tone, structure, and terminology.

## Requirements
- Python 3.10+
- OpenAI API access (chat + embeddings)
- `pip install openai typer python-dotenv`
- Optional: `pip install streamlit` if you want the browser dashboard.

Optional (Windows PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Environment variables
Place secrets in `.env` (loaded via `python-dotenv`) or set them in PowerShell before running commands:

| Variable | Required | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | ✅ | Use an API key with access to the chosen model + embeddings. Example: `$env:OPENAI_API_KEY="sk-..."` (session only) or `setx OPENAI_API_KEY "sk-..."` (persists). |
| `OPENAI_MODEL` | optional | Defaults to `gpt-4o-mini`. Set to any chat-completions model you prefer (CLI prints the active model at runtime). |
| `OPENAI_EMBED_MODEL` | optional | Defaults to `text-embedding-3-small`. |
| `CURRICULUM_SOURCE_LANG` | optional | Default `English`. Set to the language of instruction (the voice used for prose and quiz wording). |
| `CURRICULUM_TARGET_LANG` | optional | Default `Arabic`. Set to the language being taught (used for examples, vocab, and transliteration cues). |
| `CURRICULUM_ID` | optional | Override the namespace used under `generated/` and for bundled files (defaults to `<source>-to-<target>`). |

## Quick start
```powershell
$env:OPENAI_API_KEY="sk-..."
python scripts/author_lessons.py --help
```

Prefer a guided UI? Launch the interactive menu:
```powershell
python scripts/ui.py run
```
The menu walks you through:
- Initializing the style memory
- Drafting a curriculum plan
- Authoring one lesson
- Authoring a full curriculum batch (with bundle option)
- Asking questions about memory
- Bundling existing lessons into a single JSON file
- Rebuilding the memory index if you delete or import lessons

Want something even simpler? Launch the dropdown-driven web dashboard (requires `pip install streamlit` once):
```powershell
streamlit run scripts/ui_dashboard.py
```
The dashboard runs in your browser, shows per-curriculum progress (lessons completed / total), and displays a live status indicator while commands are running—all via dropdowns and buttons instead of manual flags.

The CLI automatically creates two working directories at the repo root:
- `generated/<curriculum_id>/<module_slug>/<lesson_slug>.json` – finalized lesson payloads (blocks + quiz), namespaced per curriculum (e.g., `generated/english-to-arabic/basic-concepts/definition-of-nahw-101.json`).
- `memory/` – `style.md` keeps your seed style guide, `index.json` stores vector metadata for retrieval.

### How lessons are rendered
- Text blocks flow through `components/blocks/TextBlock.tsx`, which uses `react-markdown` + `remark-gfm`. That means headings, tables, lists, and inline code all render exactly as Markdown.
- Make use of Markdown tables for side-by-side comparisons or declension charts; the renderer wraps them responsively.
- Other block types (MC, free-text, audio, image) live under `components/blocks/`, so follow the schema in `types/types.ts` if you add new block shapes.

## What is the seed lesson?
`init-style` needs a reference document (`samples/seed_lesson.md` in the examples) so the model always sees your preferred tone, formatting, and pedagogical quirks. You can create it from:
- A lesson you already wrote in Markdown or exported from another CMS.
- A lightweight “style guide” describing voice, block ordering (Objectives → Explanation → Examples → Key Takeaways), and any recurring terminology or transliteration rules.
- Existing JSON lessons by copying their explanatory blocks into plain text. Easiest workflow: open your JSON, extract the `blocks` prose (ignore IDs/metadata), and paste it under the headings below so the style doc captures the human-readable flow.

Minimal template to get started:
```markdown
# Lesson Title (used for tone cues)

## Lesson Objectives
- Students can explain ...
- Students can identify ...

## Explanatory style
- Preferred sentence length, language mix (Arabic/English gloss).
- Notes on diacritics, transliteration, or key phrases.

## Sample Block Ordering
1. Lesson Objectives (text)
2. Concept introduction (text)
3. Worked example (text or mc)
4. Key Takeaways (text)
5. Quiz mix (10–14 questions, mostly MC, 2–4 free-text)
```
Save this as `samples/seed_lesson.md` (or any `.md` file) and run `init-style` against it. You can refine it over time; rerun `init-style` whenever you update the seed. If you prefer to stay in JSON, convert one representative lesson to Markdown automatically with a quick script:
```powershell
python - <<'PY'
import json, pathlib
src = pathlib.Path("samples/lessons/nouns-cases-301.json")
data = json.loads(src.read_text(encoding="utf-8"))
lines = ["# " + data.get("title", "Seed Lesson"), ""]
for block in data.get("blocks", []):
    if block.get("type") == "text":
        lines.append(block["data"].get("content", ""))
        lines.append("")
pathlib.Path("samples/seed_lesson.md").write_text("\n".join(lines), encoding="utf-8")
print("Saved samples/seed_lesson.md")
PY
```
Edit the generated Markdown to add objectives, quiz guidance, and tone notes, then run `init-style`.

## Reusing the generator for different language pairs
Many teams build multiple curricula (e.g., English→Arabic, English→French, Arabic→English). The CLI stays the same—you just set the language direction via environment variables or per-command flags:

1. **Environment-based (best for long runs)**
   ```powershell
   setx CURRICULUM_SOURCE_LANG "English"
   setx CURRICULUM_TARGET_LANG "Arabic"
   ```
   Reopen PowerShell so the variables load, then author lessons normally.

2. **Command overrides (one-off jobs)**
   Add `--source-lang "Arabic"` (language of instruction) and `--target-lang "English"` (language being taught) to `author-one` or `author-batch`.

3. **Reflect it in your style + curriculum**
   - Mention the direction in `samples/seed_lesson.md` (e.g., “Explain grammar in English while teaching Arabic examples”).
   - Include hints in `curriculum.json` briefs when special translation behavior is needed (“Provide French glosses wherever students might confuse gender agreement.”).

**Reminder:** `source-lang` = language of instruction (all prose, headings, quiz stems). `target-lang` = language being taught (appears inside examples/terms with fast translations).

4. **Namespace each curriculum**
   - Let the CLI derive the folder name (`<source>-to-<target>`) or set `CURRICULUM_ID` / `--curriculum-id` yourself (e.g., `msa-beginners`, `en-to-fr`).
   - Every run then writes to `generated/<curriculum_id>/...`, so multiple curricula never collide and each can be bundled separately.

Each lesson prompt now includes the language-of-instruction / language-being-taught info, so the OpenAI model always knows which learners it is addressing for that run. Switching to a new curriculum is as simple as adjusting the env vars (or flags) plus pointing to the new `curriculum.json`.

## Preparing your curriculum plan
`author-batch` expects a JSON file, so keep any Markdown outline as your planning document and export it to JSON before running the CLI.

### 1. Draft the outline in Markdown (optional but nice for humans)
```markdown
# Level 1 – Foundations
## Module: الصرف 101 (slug: sarf-101)
- Lesson: جذور الفعل الثلاثي (slug: triliteral-roots, brief: Emphasize وزن فَعَلَ)
- Lesson: الأوزان المزيدة (slug: augmented-forms)

## Module: الإعراب (slug: irab)
- Lesson: حالات الاسم (slug: noun-cases-101, brief: رفع/نصب/جر overview)
```

### 2. Convert the outline to JSON
- Create `curriculum.json` at the repo root (or inside a `curricula/` folder).
- Add top-level metadata so bundling knows how to describe the curriculum (set `"slug"` to the ID you use for `--curriculum-id`, `"title"` to something like `"English → Arabic"`, and the exact `"languageOfInstruction"` / `"targetLanguage"` strings).
- Map each Markdown concept to the fields the CLI expects:

| Markdown concept | JSON key |
| --- | --- |
| Level heading | `"title"` inside `"levels"` |
| Module heading | `"title"` inside `"modules"` |
| Lesson bullet | objects inside `"lessons"` with `"title"`, optional `"slug"`/`"brief"` |

Example JSON generated from the Markdown above:
```json
{
  "slug": "en-ar",
  "title": "English → Arabic",
  "languageOfInstruction": "English",
  "targetLanguage": "Arabic",
  "levels": [
    {
      "title": "Level 1 – Foundations",
      "modules": [
        {
          "title": "الصرف 101",
          "slug": "sarf-101",
          "lessons": [
            {"title": "جذور الفعل الثلاثي", "slug": "triliteral-roots", "brief": "Emphasize وزن فَعَلَ"},
            {"title": "الأوزان المزيدة", "slug": "augmented-forms"}
          ]
        },
        {
          "title": "الإعراب",
          "slug": "irab",
          "lessons": [
            {"title": "حالات الاسم", "slug": "noun-cases-101", "brief": "رفع/نصب/جر overview"}
          ]
        }
      ]
    }
  ]
}
```

### 3. Validate before running
```powershell
python -m json.tool curriculum.json
```
`json.tool` will throw an error if brackets, commas, or quotes are off.

### 4. Keep both versions if helpful
Retain the Markdown file for editing/review and regenerate the JSON whenever you make structural changes. Only the JSON file is consumed by `author-batch`.

## Commands

### Initialize the style guide
```powershell
python scripts/author_lessons.py init-style --from-file samples/seed_lesson.md
```
Copies your seed lesson/style document into `memory/style.md` and bootstraps an empty memory index. Run this once before generating lessons so every prompt gets the same style context.

### Generate a curriculum plan (optional helper)
No curriculum JSON yet? Ask the generator to draft one:
```powershell
python scripts/generate_curriculum.py plan `
  --output curricula/en-fr.json `
  --source-lang "English" `
  --target-lang "French" `
  --level-count 4 `
  --modules-per-level 4 `
  --lessons-per-module 4 `
  --focus "Travel + conversational confidence"
```
- Add multiple `--level-note "..."` flags if you want to steer each level (“Level 1 = pronunciation foundations”, etc.).
- The script returns a JSON file formatted exactly like `samples/curriculum.json` (slug/title/language metadata + levels/modules/lessons), ready for `author-batch`.

### Author a single lesson
```powershell
python scripts/author_lessons.py author-one `
  --module "Nouns" `
  --lesson "الاسم المرفوع والمنصوب والمجرور" `
  --slug "nouns-cases-301" `
  --brief "Highlight iʿrāb cues for dual nouns" `
  --source-lang "English" `
  --target-lang "Arabic" `
  --curriculum-id "english-to-arabic"
```
Inputs:
- `--module` – UI-facing module title.
- `--lesson` – lesson title.
- `--slug` – unique slug used for file names and tags (auto-normalized).
- `--brief` – optional per-lesson instructions or emphasis.
- `--source-lang` – overrides `CURRICULUM_SOURCE_LANG` (the language of instruction used for explanations/quiz text).
- `--target-lang` – overrides `CURRICULUM_TARGET_LANG` (the language being taught, used for examples and vocabulary).
- `--curriculum-id` – forces output into `generated/<curriculum-id>/...` (defaults to `<source>-to-<target>`).

Outputs:
- JSON written to `generated/<curriculum_id>/<module>/<lesson>.json`.
- Lesson embedding stored in `memory/index.json` to keep future runs on-brand.

### Author a batch from a curriculum
```powershell
python scripts/author_lessons.py author-batch `
  --curriculum curriculum.json `
  --filter-module "Module A" `
  --start-at "nouns-cases-301" `
  --source-lang "English" `
  --target-lang "Arabic" `
  --curriculum-id "english-to-arabic" `
  --bundle-output final/curriculum.english-to-arabic.json
```
`curriculum.json` must include curriculum metadata plus levels → modules → lessons:
```json
{
  "slug": "english-to-arabic",
  "title": "English → Arabic",
  "languageOfInstruction": "English",
  "targetLanguage": "Arabic",
  "levels": [
    {
      "title": "Level 1",
      "modules": [
        {
          "title": "Module A",
          "lessons": [
            {"title": "Intro", "slug": "intro-101", "brief": "Optional notes"}
          ]
        }
      ]
    }
  ]
}
```
Flags:
- `--filter-module` – run only the matching module title or slug.
- `--start-at` – skip lessons until this slug is reached (useful for resumable jobs).
- `--source-lang` / `--target-lang` – override the language of instruction vs. language being taught for this batch.
- `--curriculum-id` – set the namespace folder for generated lessons (defaults to `<source>-to-<target>`).
- `--bundle-output` – after generation, stitch every lesson into one JSON file matching the curriculum skeleton.

Each generated lesson is saved + indexed just like `author-one`. The command throttles requests slightly to respect rate limits.

### Author the entire curriculum (no filters)
If your `samples/curriculum.json` already contains every level/module/lesson you want to produce, run:
```powershell
$env:OPENAI_API_KEY="sk-..."          # only if not already set
python scripts/author_lessons.py init-style --from-file samples/seed_lesson.md
python scripts/author_lessons.py author-batch `
  --curriculum samples/curriculum.json `
  --source-lang "English" `
  --target-lang "Arabic" `
  --curriculum-id "english-to-arabic" `
  --bundle-output final/curriculum.english-to-arabic.json
```
Tips for long runs:
- Keep PowerShell open; closing it aborts the job.
- Expect dozens of requests—watch for OpenAI rate limits. If you need a pause, stop with `Ctrl+C` and resume later using `--start-at <lesson-slug>`.
- All JSON output lands under `generated/<curriculum_id>/<module>/<lesson>.json`; memory entries update incrementally after each lesson.
- With `--bundle-output`, a merged file (e.g., `final/curriculum.english-to-arabic.json`) is written automatically once the batch finishes.

### Ask questions about authored lessons
```powershell
python scripts/author_lessons.py ask --q "What did we say about جملة القسم؟"
```
Retrieves the most relevant lessons from `memory/index.json` and answers using their content, respecting the saved style guide. Great for double-checking prior definitions or keeping terminology consistent.

### Bundle lessons after the fact
If you skipped `--bundle-output` (or want to regenerate the merged file later), run:
```powershell
python scripts/author_lessons.py bundle-curriculum `
  --curriculum samples/curriculum.json `
  --output final/curriculum.english-to-arabic.json `
  --source-lang "English" `
  --target-lang "Arabic" `
  --curriculum-id "english-to-arabic"
```
The command reads every lesson JSON from `generated/<curriculum-id>/...`, inserts them back into the curriculum skeleton, auto-generates missing `id` fields for levels/modules (slugged from their titles), and writes a single deliverable file.

### Fix older lessons that used nested text blocks
If you generated lessons before the “plain string text blocks” rule, run the migration script to flatten those blocks:
```powershell
python scripts/migrate_lessons.py run --root generated
```
- Add `--dry-run` first to see which files would change without modifying anything.
- After the script runs, regenerated lessons will render correctly in UIs expecting `block.data` to be a simple string.

### Rebuild the memory index
Deleted `memory/index.json` or imported lessons manually? Recreate the embeddings with one command:
```powershell
python scripts/reindex_memory.py run `
  --source generated `
  --output memory/index.json `
  --clear True
```
- `--source` can point to any curriculum folder (run it multiple times for different IDs if needed).
- Drop `--clear` to append new lessons without losing the existing index.

## Using existing lessons and reference material
If you already authored lessons elsewhere, you can fold them into this workflow in two complementary ways.

### 1. Use a favorite lesson as the style seed
1. Convert the lesson to Markdown or copy its explanatory prose into a `.md` file.
2. Run `python scripts/author_lessons.py init-style --from-file <that-file>.md`.
3. All subsequent generations will mirror the tone, headings, and terminology captured there.

### 2. Index ready-made lesson JSONs so RAG can see them
1. Place your example lesson files under `samples/lessons/` or directly inside `generated/<curriculum_id>/<module>/<slug>.json`.
2. Launch Python from PowerShell and run the snippet below to embed and register every JSON file. This uses the same helper functions as the CLI, so the vectors look identical.

```powershell
python
```

Inside the Python prompt:

```python
import json, pathlib, time, uuid
from author_lessons import embed_texts, openai_client, GENERATED
from memory import MemoryStore, normalize_slug

client = openai_client()
mem = MemoryStore(pathlib.Path("memory/index.json"))

source_dir = pathlib.Path("samples/lessons")
for path in source_dir.rglob("*.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    module = data.get("module", "imported")
    slug = normalize_slug(data.get("slug") or data.get("id") or path.stem)
    full_text = f"{data.get('title','')}\n" + "\n".join(
        [json.dumps(b, ensure_ascii=False) for b in data.get("blocks", [])]
    )
    emb = embed_texts(client, [full_text])[0]
    out_path = GENERATED / normalize_slug(module) / f"{slug}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    mem.add_item(
        item_id=str(uuid.uuid4()),
        title=data.get("title", path.stem),
        slug=slug,
        module=module,
        path=str(out_path),
        vector=emb,
        meta={"created_at": int(time.time())}
    )

mem.save()
```

3. Exit Python with `exit()` when the loop finishes. Your imported lessons now live in both `generated/` and `memory/index.json`, so `author-one`, `author-batch`, and `ask` can reference them immediately.

If you skip the indexing step, the CLI will still run, but its retrieval context will only include lessons generated after you started using this tool.

## How retrieval (RAG) works here
- **Generated lessons (`generated/…`)** store the full JSON output per lesson—everything your frontend will consume.
- **Memory (`memory/index.json`)** is a lightweight vector index (no external DB). Each entry records metadata (`title`, `slug`, `path`) plus an embedding of that lesson’s text so we can search semantically.
- When you run `author-one`, `author-batch`, or `ask`, the script:
  1. Reads the requested query (lesson title or user question).
  2. Uses `MemoryStore.search()` to pull the most relevant past lessons from `memory/index.json`. If there are embeddings, it reranks based on cosine similarity; if not, it falls back to recency + keyword matches.
  3. Loads the referenced files from `generated/…` to build concise summaries (block types, quiz samples) and feeds them back into the prompt so the model keeps tone/structure consistent.
- You can safely delete or edit items in `generated/` without touching the index, but the two should usually stay in sync: `generated/` is the source of truth, and `memory/index.json` is just “fast look-up” glue.

## Tips & troubleshooting
- Rerun `init-style` whenever you want to swap in a new canonical tone; existing lessons remain untouched.
- If a model response is not valid JSON, the CLI prints the raw output so you can retry after nudging the brief or lesson inputs.
- Keep an eye on `memory/index.json` size; it grows with every lesson. You can prune older entries manually if necessary (be sure to back up first).
- For reproducibility, pin exact model versions via `OPENAI_MODEL`/`OPENAI_EMBED_MODEL`.

Happy authoring!
