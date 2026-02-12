#!/usr/bin/env python3
"""
Streamlit dashboard for Kitabite lesson authoring.
Gives dropdown-driven forms for the most common workflows so users can avoid typing paths/flags.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
from functools import lru_cache
from typing import List, Optional, Tuple

import streamlit as st

from author_lessons import (
    GENERATED,
    author_batch as author_batch_cmd,
    author_one as author_one_cmd,
    bundle_curriculum as bundle_curriculum_cmd,
    get_source_language,
    get_target_language,
    resolve_curriculum_id,
)
from generate_curriculum import plan as plan_curriculum_cmd
from memory import normalize_slug


ROOT = pathlib.Path(__file__).resolve().parents[1]
CURRICULUM_DIRS = [
    ROOT / "curricula",
    ROOT / "samples",
    ROOT / "final",
]


def list_curriculum_files() -> List[pathlib.Path]:
    seen = {}
    for base in CURRICULUM_DIRS:
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            seen[str(path)] = path
    for path in sorted(ROOT.glob("*.json")):
        if "curriculum" in path.stem.lower():
            seen[str(path)] = path
    return list(seen.values())


@lru_cache(maxsize=32)
def load_curriculum(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_modules(plan: dict) -> List[dict]:
    modules: List[dict] = []
    for level in plan.get("levels", []):
        modules.extend(level.get("modules", []))
    return modules


def flatten_lessons(plan: dict) -> List[Tuple[str, dict]]:
    lessons: List[Tuple[str, dict]] = []
    for level in plan.get("levels", []):
        for module in level.get("modules", []):
            for lesson in module.get("lessons", []):
                lessons.append((module.get("title", "Module"), lesson))
    return lessons


def lesson_totals(plan: dict) -> int:
    return len(flatten_lessons(plan))


def completed_lessons(plan: dict, curriculum_id: str) -> int:
    if not curriculum_id:
        return 0
    base = GENERATED / curriculum_id
    if not base.exists():
        return 0
    done = 0
    for level in plan.get("levels", []):
        for module in level.get("modules", []):
            mod_slug = module.get("slug") or normalize_slug(module.get("title", "module"))
            for lesson in module.get("lessons", []):
                lesson_slug = normalize_slug(lesson.get("slug") or lesson.get("title", "lesson"))
                lesson_path = base / mod_slug / f"{lesson_slug}.json"
                if lesson_path.exists():
                    done += 1
    return done


def run_with_logs(label: str, fn, **kwargs) -> str:
    buf = io.StringIO()
    try:
        with st.spinner(label), contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            fn(**kwargs)
    except SystemExit as exc:
        st.error(f"Command aborted: {exc}")
    except Exception as exc:  # pragma: no cover - streamlit handles display
        st.exception(exc)
    return buf.getvalue().strip()


def curriculum_selectbox(label: str, key: str) -> Optional[pathlib.Path]:
    files = list_curriculum_files()
    options: List[Optional[pathlib.Path]] = [None] + files
    def _fmt(option: Optional[pathlib.Path]) -> str:
        if option is None:
            return "— Select a curriculum file —"
        rel = option.relative_to(ROOT)
        return str(rel)
    return st.selectbox(label, options, format_func=_fmt, key=key)


def module_selectbox(plan: dict, key: str, include_all: bool = False) -> Tuple[str, Optional[str]]:
    modules = flatten_modules(plan)
    options: List[Tuple[str, Optional[str]]] = []
    if include_all:
        options.append(("All modules", None))
    for module in modules:
        label = module.get("title", "Untitled module")
        slug = module.get("slug") or label
        options.append((label, slug))
    disabled = False
    if not options:
        options = [("No modules found", None)]
        disabled = True
    selection = st.selectbox(
        "Module",
        options,
        format_func=lambda opt: opt[0],
        key=key,
        disabled=disabled,
    )
    return selection[0], selection[1]


def lesson_selectbox(plan: dict, key: str, placeholder: str = "Beginning") -> Tuple[str, Optional[str]]:
    lessons = flatten_lessons(plan)
    options: List[Tuple[str, Optional[str]]] = [(placeholder, None)]
    for module_title, lesson in lessons:
        lesson_title = lesson.get("title", "Untitled lesson")
        slug = lesson.get("slug") or lesson_title
        options.append((f"{module_title} → {lesson_title} ({slug})", slug))
    disabled = False
    if len(options) == 1:
        options = [(f"No lessons found ({placeholder})", None)]
        disabled = True
    selection = st.selectbox(
        "Lesson",
        options,
        format_func=lambda opt: opt[0],
        key=key,
        disabled=disabled,
    )
    return selection[0], selection[1]


def default_langs(curriculum: Optional[dict]) -> Tuple[str, str]:
    if curriculum:
        lang_instruction = curriculum.get("languageOfInstruction") or get_source_language()
        target = curriculum.get("targetLanguage") or get_target_language()
        return lang_instruction, target
    return get_source_language(), get_target_language()


def main() -> None:
    st.set_page_config("Kitabite Dashboard", layout="wide")
    st.title("Kitabite Lesson Builder")
    st.caption("Click-to-run interface for authoring lessons, running batches, and bundling curricula.")
    st.session_state.setdefault("batch_running", False)
    st.session_state.setdefault("lesson_running", False)
    st.session_state.setdefault("bundle_running", False)

    tabs = st.tabs([
        "Author One Lesson",
        "Author Entire Curriculum",
        "Bundle Curriculum",
        "Draft Curriculum Plan",
    ])

    # --- Author one lesson ---
    with tabs[0]:
        st.header("Author a single lesson")
        lesson_status = st.empty()
        if st.session_state["lesson_running"]:
            lesson_status.warning("Status: generating lesson…")
        else:
            lesson_status.info("Status: idle")
        plan_path = curriculum_selectbox("Reference curriculum", key="a1_curriculum")
        plan = load_curriculum(plan_path) if plan_path else None
        mode = st.radio("Lesson source", ["Choose from curriculum", "Enter manually"], horizontal=True)

        if mode == "Choose from curriculum" and not plan:
            st.info("Select a curriculum file to unlock dropdown options, or switch to manual mode.")
        module_title = ""
        lesson_title = ""
        lesson_slug = ""
        brief = ""
        if plan and mode == "Choose from curriculum":
            module_label, _ = module_selectbox(plan, key="a1_module")
            module_lessons = [entry for entry in flatten_lessons(plan) if entry[0] == module_label]
            lesson_choices = [("Select lesson", None)] + [
                (entry[1].get("title", "Untitled lesson"), entry[1]) for entry in module_lessons
            ]
            selection = st.selectbox(
                "Lesson",
                lesson_choices,
                format_func=lambda opt: opt[0],
                key="a1_lesson",
            )
            lesson_dict = selection[1]
            if lesson_dict:
                module_title = module_label
                lesson_title = lesson_dict.get("title", "")
                lesson_slug = lesson_dict.get("slug") or lesson_title
                brief = lesson_dict.get("brief", "")
        if mode == "Enter manually" or not lesson_title:
            module_title = st.text_input("Module title", value=module_title)
            lesson_title = st.text_input("Lesson title", value=lesson_title)
            lesson_slug = st.text_input("Lesson slug", value=lesson_slug)
            brief = st.text_area("Optional brief for the model", value=brief)

        lang_instruction, lang_target = default_langs(plan)
        col1, col2, col3 = st.columns(3)
        with col1:
            source_lang = st.text_input("Language of instruction", value=lang_instruction)
        with col2:
            target_lang = st.text_input("Language being taught", value=lang_target)
        with col3:
            default_curriculum_id = (plan or {}).get("slug") or resolve_curriculum_id(None, source_lang, target_lang)
            curriculum_id = st.text_input("Curriculum folder ID", value=default_curriculum_id)

        if st.button("Author lesson", type="primary", use_container_width=True):
            if not module_title or not lesson_title or not lesson_slug:
                st.error("Module title, lesson title, and slug are required.")
            else:
                st.session_state["lesson_running"] = True
                lesson_status.warning("Status: generating lesson…")
                log = run_with_logs(
                    "Authoring lesson...",
                    author_one_cmd,
                    module=module_title,
                    lesson=lesson_title,
                    slug=lesson_slug,
                    brief=brief or None,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    curriculum_id=curriculum_id,
                )
                st.session_state["lesson_running"] = False
                lesson_status.info("Status: idle")
                if log:
                    st.code(log, language="text")
                st.success("Lesson generated. Check the console/log for exact file path.")

    # --- Author batch ---
    with tabs[1]:
        st.header("Author an entire curriculum")
        batch_status = st.empty()
        if st.session_state["batch_running"]:
            batch_status.warning("Status: generating lessons…")
        else:
            batch_status.info("Status: idle")
        plan_path = curriculum_selectbox("Curriculum plan JSON", key="batch_curriculum")
        if plan_path:
            plan = load_curriculum(plan_path)
            _, filter_value = module_selectbox(plan, key="batch_module", include_all=True)
            _, start_at = lesson_selectbox(plan, key="batch_lesson", placeholder="Start at beginning")
            lang_instruction, lang_target = default_langs(plan)
            col1, col2, col3 = st.columns(3)
            with col1:
                source_lang = st.text_input("Language of instruction", value=lang_instruction, key="batch_source")
            with col2:
                target_lang = st.text_input("Language being taught", value=lang_target, key="batch_target")
            with col3:
                default_curriculum_id = plan.get("slug") or resolve_curriculum_id(None, source_lang, target_lang)
                curriculum_id = st.text_input("Curriculum folder ID", value=default_curriculum_id, key="batch_curriculum_id")
            total_lessons = lesson_totals(plan)
            finished = completed_lessons(plan, curriculum_id)
            progress = finished / total_lessons if total_lessons else 0.0
            prog_col1, prog_col2 = st.columns([1, 3])
            with prog_col1:
                st.metric("Lessons completed", f"{finished}/{total_lessons}")
            with prog_col2:
                st.progress(progress)
            bundle_default = ROOT / "final" / f"{curriculum_id}.json"
            bundle_path = st.text_input(
                "Optional bundle output (final JSON path)",
                value=str(bundle_default),
                key="batch_bundle",
            )
            if st.button("Generate all lessons", type="primary", use_container_width=True):
                st.session_state["batch_running"] = True
                batch_status.warning("Status: generating lessons…")
                log = run_with_logs(
                    "Authoring curriculum...",
                    author_batch_cmd,
                    curriculum=plan_path,
                    filter_module=filter_value,
                    start_at=start_at,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    curriculum_id=curriculum_id,
                    bundle_output=pathlib.Path(bundle_path) if bundle_path else None,
                )
                st.session_state["batch_running"] = False
                batch_status.info("Status: idle")
                if log:
                    st.code(log, language="text")
                st.success("Batch run finished. Inspect the log for per-lesson paths.")
        else:
            st.info("Select a curriculum file to configure the batch run.")

    # --- Bundle ---
    with tabs[2]:
        st.header("Bundle generated lessons")
        bundle_status = st.empty()
        if st.session_state["bundle_running"]:
            bundle_status.warning("Status: bundling lessons…")
        else:
            bundle_status.info("Status: idle")
        plan_path = curriculum_selectbox("Curriculum plan JSON", key="bundle_curriculum")
        if plan_path:
            plan = load_curriculum(plan_path)
            lang_instruction, lang_target = default_langs(plan)
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                source_lang = st.text_input("Language of instruction", value=lang_instruction, key="bundle_source")
            with col_b:
                target_lang = st.text_input("Language being taught", value=lang_target, key="bundle_target")
            with col_c:
                default_curriculum_id = plan.get("slug") or resolve_curriculum_id(None, source_lang, target_lang)
                curriculum_id = st.text_input("Curriculum folder ID", value=default_curriculum_id, key="bundle_curriculum_id")
            default_output = ROOT / "final" / f"{curriculum_id}.json"
            output_path = st.text_input("Bundled JSON output path", value=str(default_output), key="bundle_output")

            if st.button("Bundle lessons", type="primary", use_container_width=True):
                st.session_state["bundle_running"] = True
                bundle_status.warning("Status: bundling lessons…")
                log = run_with_logs(
                    "Bundling lessons...",
                    bundle_curriculum_cmd,
                    curriculum=plan_path,
                    output=pathlib.Path(output_path),
                    source_lang=source_lang,
                    target_lang=target_lang,
                    curriculum_id=curriculum_id,
                )
                st.session_state["bundle_running"] = False
                bundle_status.info("Status: idle")
                if log:
                    st.code(log, language="text")
                st.success(f"Bundled file saved to {output_path}")
        else:
            st.info("Select a curriculum file to bundle.")

    # --- Plan generation ---
    with tabs[3]:
        st.header("Draft a curriculum plan")
        col1, col2 = st.columns(2)
        with col1:
            source_lang = st.text_input("Language of instruction", value=get_source_language(), key="plan_source")
            level_count = st.number_input("Number of proficiency levels", min_value=1, max_value=8, value=4, step=1)
            lessons_per_module = st.number_input("Lessons per module", min_value=1, max_value=10, value=4, step=1)
        with col2:
            target_lang = st.text_input("Language being taught", value=get_target_language(), key="plan_target")
            modules_per_level = st.number_input("Modules per level", min_value=1, max_value=8, value=4, step=1)
            focus = st.text_input("Overall focus (optional)", key="plan_focus")
            audience = st.selectbox(
                "Target audience",
                options=["university", "high-school"],
                format_func=lambda val: "High school (plain language)" if val == "high-school" else "University/adult",
                key="plan_audience",
            )
        output_path = st.text_input(
            "Where should we save the curriculum JSON?",
            value=str(ROOT / "curricula" / "new-curriculum.json"),
            key="plan_output",
        )
        add_notes = st.checkbox("Add level-specific guidance?")
        level_notes: List[str] = []
        if add_notes:
            for idx in range(int(level_count)):
                note = st.text_input(f"Level {idx + 1} guidance", key=f"level_note_{idx}")
                if note:
                    level_notes.append(note)

        if st.button("Generate curriculum plan", type="primary", use_container_width=True):
            log = run_with_logs(
                "Drafting curriculum plan...",
                plan_curriculum_cmd,
                output=pathlib.Path(output_path),
                source_lang=source_lang,
                target_lang=target_lang,
                level_count=int(level_count),
                modules_per_level=int(modules_per_level),
                lessons_per_module=int(lessons_per_module),
                level_note=level_notes,
                focus=focus or None,
                audience=audience,
            )
            if log:
                st.code(log, language="text")
            st.success(f"Saved curriculum plan to {output_path}")


if __name__ == "__main__":
    main()
