"""
fix_generator node — generate fixes for each failure.

Strategy (per SOURCE_OF_TRUTH §7):
  1. Rule-based fixer for well-known patterns first.
  2. LLM fallback when rules don't match.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ...config import OPENAI_MODEL
from ...llm import get_llm, has_llm_keys
from ...db import insert_fix, insert_trace
from ...events import emit_fix_applied, emit_thought
from ..state import AgentState, FixRecord, TestFailure

logger = logging.getLogger("rift.node.fix_generator")


# ── Rule-based fixers ───────────────────────────────────────

def _extract_missing_module(error_message: str) -> str | None:
    """Extract a missing module/package name from common import errors."""
    patterns = [
        r"No module named ['\"]([^'\"]+)['\"]",
        r"cannot find module ['\"]([^'\"]+)['\"]",
        r"Cannot find module ['\"]([^'\"]+)['\"]",
    ]
    for pat in patterns:
        m = re.search(pat, error_message, re.I)
        if m:
            return m.group(1).strip().split(".")[0]
    return None


def _local_module_exists(module_name: str, repo_dir: Path, file_path: Path) -> bool:
    """Best-effort check whether missing module likely exists in-repo."""
    candidates = [
        file_path.parent / f"{module_name}.py",
        file_path.parent / module_name / "__init__.py",
        repo_dir / f"{module_name}.py",
        repo_dir / module_name / "__init__.py",
    ]
    return any(p.exists() for p in candidates)


def _fix_import(
    failure: TestFailure,
    file_content: str,
    file_path: Path,
    repo_dir: Path,
) -> str | None:
    """
    Attempt to fix ImportError / ModuleNotFoundError.

    Heuristics:
      1) Rewrite absolute local imports to relative imports in Python files.
      2) Add missing package to requirements.txt / package.json when
         the failure clearly points to a missing dependency.
    """
    missing_module = _extract_missing_module(failure.error_message)
    if not missing_module:
        return None

    suffix = file_path.name.lower()

    # requirements.txt dependency fallback
    if suffix == "requirements.txt":
        req_lines = file_content.splitlines()
        normalized = {ln.strip().split("==")[0].lower() for ln in req_lines if ln.strip()}
        if missing_module.lower() in normalized:
            return None
        fixed = file_content
        if fixed and not fixed.endswith("\n"):
            fixed += "\n"
        fixed += f"{missing_module}\n"
        return fixed

    # package.json dependency fallback
    if suffix == "package.json":
        import json

        try:
            pkg = json.loads(file_content)
        except json.JSONDecodeError:
            return None

        deps = pkg.setdefault("devDependencies", {})
        if not isinstance(deps, dict):
            return None
        if missing_module in deps:
            return None

        deps[missing_module] = "latest"
        return json.dumps(pkg, indent=2, ensure_ascii=True) + "\n"

    # Source-level Python import rewrite (absolute -> relative)
    if file_path.suffix != ".py":
        return None
    if not _local_module_exists(missing_module, repo_dir, file_path):
        return None

    lines = file_content.splitlines(keepends=True)
    target_idx = max(0, min(len(lines) - 1, failure.line_number - 1))

    pat_from = re.compile(
        rf"^(\s*)from\s+{re.escape(missing_module)}(\.[\w\.]+)?\s+import\s+(.+)$"
    )
    pat_import = re.compile(
        rf"^(\s*)import\s+{re.escape(missing_module)}(\.[\w\.]+)?(\s+as\s+\w+)?\s*$"
    )

    candidate_indexes = [target_idx] + [i for i in range(len(lines)) if i != target_idx]
    for idx in candidate_indexes:
        line = lines[idx]
        if line.lstrip().startswith(("from .", "from ..")):
            continue

        m_from = pat_from.match(line)
        if m_from:
            indent, submodule, imported = m_from.groups()
            submodule = submodule or ""
            lines[idx] = f"{indent}from .{missing_module}{submodule} import {imported}\n"
            return "".join(lines)

        m_import = pat_import.match(line)
        if m_import:
            indent, submodule, alias = m_import.groups()
            submodule = submodule or ""
            alias = alias or ""
            lines[idx] = f"{indent}from . import {missing_module}{submodule}{alias}\n"
            return "".join(lines)

    return None


def _fix_indentation(failure: TestFailure, file_content: str) -> str | None:
    """Fix indentation issues."""
    lines = file_content.splitlines(keepends=True)
    target_line = failure.line_number - 1
    if target_line < 0 or target_line >= len(lines):
        return None

    line = lines[target_line]
    # Mixed tabs and spaces
    if "\t" in line and " " in line[:len(line) - len(line.lstrip())]:
        lines[target_line] = line.expandtabs(4)
        return "".join(lines)

    # Unexpected indent — try removing one level
    if "unexpected indent" in failure.error_message.lower():
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]
        if len(indent) >= 4:
            lines[target_line] = indent[4:] + stripped
            return "".join(lines)

    # Expected indented block — add 4 spaces
    if "expected an indented block" in failure.error_message.lower():
        indent = line[:len(line) - len(line.lstrip())]
        lines[target_line] = indent + "    " + line.lstrip()
        return "".join(lines)

    return None


def _fix_syntax(failure: TestFailure, file_content: str) -> str | None:
    """Fix common syntax errors."""
    lines = file_content.splitlines(keepends=True)
    target_line = failure.line_number - 1
    if target_line < 0 or target_line >= len(lines):
        return None

    line = lines[target_line]

    # Missing colon at end of def/class/if/for/while/with
    if re.search(r"expected ':'", failure.error_message, re.I):
        stripped = line.rstrip()
        if not stripped.endswith(":") and re.match(
            r"\s*(def|class|if|elif|else|for|while|with|try|except|finally)\b",
            line,
        ):
            lines[target_line] = stripped + ":\n"
            return "".join(lines)

    # Unmatched parenthesis — basic
    if "unexpected EOF" in failure.error_message or "SyntaxError" in failure.error_message:
        open_count = file_content.count("(") - file_content.count(")")
        if open_count > 0:
            lines.append(")" * open_count + "\n")
            return "".join(lines)

    return None


def _fix_linting(failure: TestFailure, file_content: str) -> str | None:
    """Fix common linting issues."""
    lines = file_content.splitlines(keepends=True)
    target_line = failure.line_number - 1
    if target_line < 0 or target_line >= len(lines):
        return None

    line = lines[target_line]

    # Trailing whitespace
    if "trailing whitespace" in failure.error_message.lower():
        lines[target_line] = line.rstrip() + "\n"
        return "".join(lines)

    # Line too long — not auto-fixable safely, skip
    return None


def _guess_import_manifest(repo_dir: Path) -> Path | None:
    """Pick the best manifest file for dependency-level import fixes."""
    for rel in ("requirements.txt", "package.json"):
        path = repo_dir / rel
        if path.exists():
            return path
    return None


_RULE_FIXERS: dict[str, Any] = {
    "IMPORT": _fix_import,
    "INDENTATION": _fix_indentation,
    "SYNTAX": _fix_syntax,
    "LINTING": _fix_linting,
}


async def _llm_generate_fix(
    failure: TestFailure,
    file_content: str,
    language: str,
) -> tuple[str, str] | None:
    """Use LLM to generate a fix. Returns (fixed_code, explanation) or None."""
    if not has_llm_keys():
        logger.warning("No LLM keys configured — cannot generate LLM fix")
        return None

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm()

    # Show context around the failing line
    lines = file_content.splitlines()
    start = max(0, failure.line_number - 10)
    end = min(len(lines), failure.line_number + 10)
    context_lines = lines[start:end]
    context = "\n".join(
        f"{'>>>' if i + start + 1 == failure.line_number else '   '} {i + start + 1}: {l}"
        for i, l in enumerate(context_lines)
    )

    prompt = f"""Fix the following {language} code error.

**Error**: {failure.error_message}
**Bug type**: {failure.bug_type}
**File**: {failure.file_path}
**Line**: {failure.line_number}

**Code context** (>>> marks the failing line):
```
{context}
```

**Full file** (first 3000 chars):
```{language}
{file_content[:3000]}
```

Return ONLY the complete fixed file content. No markdown fences, no explanation."""

    resp = await llm.ainvoke([
        SystemMessage(
            content=(
                "You are an expert code fixer. Return ONLY the corrected full file content. "
                "Make minimal changes. Preserve formatting and style."
            )
        ),
        HumanMessage(content=prompt),
    ])

    fixed = str(resp.content).strip()
    # Strip markdown fences if present
    if fixed.startswith("```"):
        lines_out = fixed.splitlines()
        if lines_out[0].startswith("```"):
            lines_out = lines_out[1:]
        if lines_out and lines_out[-1].strip() == "```":
            lines_out = lines_out[:-1]
        fixed = "\n".join(lines_out)

    if fixed and fixed != file_content:
        return fixed, f"LLM fix for {failure.bug_type}: {failure.error_message[:100]}"

    return None


async def fix_generator(state: AgentState) -> AgentState:
    """
    Generate a fix for each failure.
    """
    run_id = state["run_id"]
    failures = state.get("failures", [])
    repo_dir = state.get("repo_dir", "")
    language = state.get("language", "python")
    iteration = state.get("iteration", 1)
    existing_fixes = list(state.get("fixes", []))
    step = iteration * 10 + 5

    if not failures:
        await emit_thought(run_id, "fix_generator", "No failures to fix ✓", step)
        return {"current_node": "fix_generator"}

    await emit_thought(
        run_id, "fix_generator",
        f"Generating fixes for {len(failures)} failure(s)…",
        step,
    )

    new_fixes: list[FixRecord] = []

    for i, failure in enumerate(failures):
        repo_root = Path(repo_dir)
        # Guard against None/empty file_path from LLM fallback
        fp = failure.file_path or "unknown"
        if fp == "unknown" or not fp.strip():
            # For IMPORT failures we can still target dependency manifests.
            if failure.bug_type == "IMPORT":
                guessed = _guess_import_manifest(repo_root)
                if guessed is not None:
                    fp = guessed.relative_to(repo_root).as_posix()
                    await emit_thought(
                        run_id,
                        "fix_generator",
                        f"Failure had unknown file path; targeting {fp} for dependency fix",
                        step + i + 1,
                    )
                else:
                    logger.warning("Skipping failure with unknown file path: %s", failure.error_message[:100])
                    new_fixes.append(
                        FixRecord(
                            file_path=fp,
                            bug_type=failure.bug_type,
                            line_number=failure.line_number,
                            description=failure.error_message,
                            fix_description="Unknown file path — skipped",
                            original_code="",
                            fixed_code="",
                            status="skipped",
                            confidence=0.0,
                        )
                    )
                    continue
            else:
                logger.warning("Skipping failure with unknown file path: %s", failure.error_message[:100])
                new_fixes.append(
                    FixRecord(
                        file_path=fp,
                        bug_type=failure.bug_type,
                        line_number=failure.line_number,
                        description=failure.error_message,
                        fix_description="Unknown file path — skipped",
                        original_code="",
                        fixed_code="",
                        status="skipped",
                        confidence=0.0,
                    )
                )
                continue

        file_path = repo_root / fp
        if not file_path.exists():
            logger.warning("File not found: %s", file_path)
            new_fixes.append(
                FixRecord(
                    file_path=fp,
                    bug_type=failure.bug_type,
                    line_number=failure.line_number,
                    description=failure.error_message,
                    fix_description="File not found — skipped",
                    original_code="",
                    fixed_code="",
                    status="skipped",
                    confidence=0.0,
                )
            )
            continue

        original_code = file_path.read_text(encoding="utf-8", errors="replace")

        # 1. Try rule-based fix
        fixed_code = None
        model_used = "rule-based"
        fixer = _RULE_FIXERS.get(failure.bug_type)
        if fixer:
            if failure.bug_type == "IMPORT":
                fixed_code = fixer(failure, original_code, file_path, repo_root)
            else:
                fixed_code = fixer(failure, original_code)

        # 2. LLM fallback
        if fixed_code is None:
            llm_result = await _llm_generate_fix(failure, original_code, language)
            if llm_result:
                fixed_code, _ = llm_result
                model_used = OPENAI_MODEL or "llm"

        # 3. Import-specific manifest fallback (if source-level fix failed)
        if fixed_code is None and failure.bug_type == "IMPORT":
            manifest = _guess_import_manifest(repo_root)
            if manifest is not None and manifest != file_path:
                manifest_original = manifest.read_text(encoding="utf-8", errors="replace")
                manifest_fixed = _fix_import(failure, manifest_original, manifest, repo_root)
                if manifest_fixed and manifest_fixed != manifest_original:
                    file_path = manifest
                    fp = manifest.relative_to(repo_root).as_posix()
                    original_code = manifest_original
                    fixed_code = manifest_fixed
                    model_used = "rule-based"

        if fixed_code is None:
            await emit_thought(
                run_id, "fix_generator",
                f"No patch generated for {fp}:{failure.line_number} ({failure.bug_type})",
                step + i + 1,
            )
            new_fixes.append(
                FixRecord(
                    file_path=fp,
                    bug_type=failure.bug_type,
                    line_number=failure.line_number,
                    description=failure.error_message,
                    fix_description="Could not generate fix",
                    original_code=original_code[:500],
                    fixed_code="",
                    status="failed",
                    confidence=0.0,
                    model_used=model_used,
                )
            )
            await emit_fix_applied(
                run_id, fp, failure.bug_type,
                failure.line_number, "failed", 0.0,
            )
            continue

        # Apply the fix
        file_path.write_text(fixed_code, encoding="utf-8")
        confidence = 0.95 if model_used == "rule-based" else 0.75

        fix_record = FixRecord(
            file_path=fp,
            bug_type=failure.bug_type,
            line_number=failure.line_number,
            description=failure.error_message,
            fix_description=f"{model_used} fix for {failure.bug_type}",
            original_code=original_code[:500],
            fixed_code=fixed_code[:500],
            status="applied",
            confidence=confidence,
            model_used=model_used,
        )
        new_fixes.append(fix_record)

        # Persist to DB
        fix_id = await insert_fix(
            run_id,
            file_path=fp,
            bug_type=failure.bug_type,
            line_number=failure.line_number,
            description=failure.error_message,
            fix_description=fix_record.fix_description,
            original_code=original_code[:2000],
            fixed_code=fixed_code[:2000],
            status="applied",
            confidence_score=confidence,
            model_used=model_used,
        )

        await emit_fix_applied(
            run_id, fp, failure.bug_type,
            failure.line_number, "applied", confidence,
        )

        await emit_thought(
            run_id, "fix_generator",
            f"Fixed {fp}:{failure.line_number} ({failure.bug_type}) via {model_used}",
            step + i + 1,
        )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="fix_generator",
        action_type="fix_generation",
        action_label=f"Generated {len(new_fixes)} fix(es) for iteration {iteration}",
        payload={
            "fixes_applied": sum(1 for f in new_fixes if f.status == "applied"),
            "fixes_failed": sum(1 for f in new_fixes if f.status == "failed"),
            "fixes_skipped": sum(1 for f in new_fixes if f.status == "skipped"),
        },
    )

    return {
        "fixes": existing_fixes + new_fixes,
        "current_node": "fix_generator",
    }
