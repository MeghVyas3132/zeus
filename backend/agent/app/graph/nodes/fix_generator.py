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

from ...config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE
from ...llm import get_llm, has_llm_keys
from ...db import insert_fix, insert_trace
from ...events import emit_fix_applied, emit_thought
from ..state import AgentState, FixRecord, TestFailure

logger = logging.getLogger("rift.node.fix_generator")


# ── Rule-based fixers ───────────────────────────────────────

def _fix_import(failure: TestFailure, file_content: str) -> str | None:
    """Attempt to fix ImportError / ModuleNotFoundError."""
    # Common: `from X import Y` where X is misspelled
    m = re.search(r"No module named '(\w+)'", failure.error_message)
    if not m:
        m = re.search(r"cannot import name '(\w+)'", failure.error_message)
    if not m:
        return None

    # Simple heuristic: if it looks like a relative import issue, try adding .
    bad_module = m.group(1)
    # Check if there is a file matching the module in the repo
    # For now, return None to let LLM handle complex cases
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
        logger.warning("No Groq API keys — cannot generate LLM fix")
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
        # Guard against None/empty file_path from LLM fallback
        fp = failure.file_path or "unknown"
        if fp == "unknown" or not fp.strip():
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

        file_path = Path(repo_dir) / fp
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
            fixed_code = fixer(failure, original_code)

        # 2. LLM fallback
        if fixed_code is None:
            llm_result = await _llm_generate_fix(failure, original_code, language)
            if llm_result:
                fixed_code, _ = llm_result
                model_used = OPENAI_MODEL

        if fixed_code is None:
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
