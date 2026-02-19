"""
ast_analyzer node — parse test output and classify failures into the
six canonical bug types required by the hackathon scoring rubric.

Strategy (per SOURCE_OF_TRUTH §7):
  1. Rule-based parser/classifier first.
  2. LLM fallback only when rule path cannot resolve.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ...config import OPENAI_API_KEY, OPENAI_MODEL
from ...db import insert_trace
from ...events import emit_thought
from ...llm import get_llm, has_llm_keys
from ..state import AgentState, BugType, TestFailure

logger = logging.getLogger("rift.node.ast_analyzer")

# ── Rule-based classifiers ──────────────────────────────────

_PYTEST_FAILURE_RE = re.compile(
    r"^(?:FAILED|ERROR)\s+([\w/\\.]+)::(\w+)"
    r"(?:\s*-\s*(.+))?$",
    re.MULTILINE,
)

_FILE_LINE_RE = re.compile(
    r'File "([^"]+)", line (\d+)',
)

_JEST_FAILURE_RE = re.compile(
    r"●\s+([\w\s]+)\s+›\s+([\w\s]+)\n\n\s+(.+)",
    re.MULTILINE,
)

# Error message patterns → bug type (universal across all languages)
_BUG_PATTERNS: list[tuple[re.Pattern[str], BugType]] = [
    # ── Syntax ──
    (re.compile(
        r"SyntaxError|IndentationError|TabError"
        r"|error CS\d+|error TS\d+"                    # C# / TypeScript compiler
        r"|ParseError|parse error"                      # PHP
        r"|expected.*\btoken\b|unexpected token"        # generic
        r"|syntax error|SyntaxException"                # generic
        r"|error\[E\d+\].*expected"                     # Rust
        r"|\.go:\d+:\d+:.*expected"                     # Go
        r"|error:.*expected.*;|missing semicolon"        # C/C++/Java
    , re.I), "SYNTAX"),

    # ── Indentation (subset of syntax, checked first) ──
    (re.compile(
        r"IndentationError|unexpected indent|expected an indented block"
        r"|inconsistent use of tabs and spaces"
    , re.I), "INDENTATION"),

    # ── Import / Module resolution ──
    (re.compile(
        r"ImportError|ModuleNotFoundError|No module named"
        r"|cannot find module|Cannot find module"        # Node.js / TS
        r"|unresolved import|cannot find type"           # Rust / generic
        r"|missing.*reference|CS0246"                    # C#
        r"|package .* is not in GOROOT"                  # Go
        r"|error\[E0432\]|error\[E0433\]"               # Rust unresolved
        r"|no required module provides"                  # Go
        r"|LoadError|require.*cannot load such file"     # Ruby
        r"|Class .* not found|Fatal error.*not found"    # PHP
        r"|UndefinedFunctionError|module .* is not available"  # Elixir
        r"|Could not resolve"                            # Dart/Flutter
        r"|error: package .* does not exist"             # Java
        r"|import .* could not be resolved"              # generic
    , re.I), "IMPORT"),

    # ── Type errors ──
    (re.compile(
        r"TypeError|type.?error|expected.*got|incompatible type"
        r"|CS0029|CS1503|cannot.?convert"                # C#
        r"|error TS\d+:.*Type .* is not assignable"      # TypeScript
        r"|type mismatch|expected type"                  # Rust / Go / generic
        r"|error\[E0308\]"                               # Rust type mismatch
        r"|cannot use .* as type"                        # Go
        r"|incompatible types|found.*required"           # Java
        r"|Argument .* must be of type"                  # PHP
    , re.I), "TYPE_ERROR"),

    # ── Linting / style / warnings ──
    (re.compile(
        r"flake8|pylint|eslint|E\d{3}|W\d{3}"
        r"|trailing whitespace|line too long"
        r"|CS8600|nullable"                              # C# nullable
        r"|clippy|warning\[.*\]"                         # Rust clippy
        r"|golint|staticcheck|go vet"                    # Go lint
        r"|rubocop|standardrb"                           # Ruby
        r"|phpcs|psalm|phpstan"                          # PHP
        r"|credo|dialyzer"                               # Elixir
        r"|hlint"                                        # Haskell
        r"|dart analyze|analysis_options"                 # Dart
        r"|checkstyle|spotbugs|PMD"                      # Java
        r"|ktlint|detekt"                                # Kotlin
    , re.I), "LINTING"),

    # ── Logic / assertion failures (broadest — last) ──
    (re.compile(
        r"AssertionError|assert\s|Expected.*received|to equal|toBe|not equal"
        r"|Assert\.Equal|Assert\.True|Xunit|NUnit|MSTest"   # .NET
        r"|FAIL.*Test|test.*failed"                          # generic
        r"|panicked at|assertion failed"                     # Rust
        r"|FAIL:.*Test|--- FAIL:"                            # Go
        r"|Failure/Error:|expected.*to\b|RSpec"              # Ruby
        r"|PHPUnit.*Failed|Failed asserting"                 # PHP
        r"|Assertion.*failed|ExUnit"                         # Elixir
        r"|assertEqual|assertRaises"                         # Python unittest
    , re.I), "LOGIC"),
]


def _classify_bug_type(error_msg: str) -> BugType:
    """Match error message against known patterns."""
    for pattern, bug_type in _BUG_PATTERNS:
        if pattern.search(error_msg):
            return bug_type
    return "LOGIC"  # default fallback


def _parse_pytest_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from pytest output."""
    failures: list[TestFailure] = []

    # Split output into sections per failure
    sections = re.split(r"_{10,}\s+", output)

    for section in sections:
        # Try to find FAILED lines
        m = _PYTEST_FAILURE_RE.search(section)
        if not m:
            continue

        file_path = m.group(1)
        test_name = m.group(2)
        error_msg = m.group(3) or section[:500]

        # Try to extract line number
        line_match = _FILE_LINE_RE.search(section)
        line_number = int(line_match.group(2)) if line_match else 1

        bug_type = _classify_bug_type(error_msg)

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg.strip()[:500],
                bug_type=bug_type,
                raw_output=section[:1000],
            )
        )

    # If regex didn't catch structured failures, try line-by-line FAILED pattern
    if not failures:
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):
                parts = stripped.split(" ", 1)
                if len(parts) > 1:
                    loc = parts[1].split("::")
                    file_path = loc[0] if loc else "unknown"
                    test_name = loc[1] if len(loc) > 1 else "unknown"
                    error_msg = " ".join(loc[2:]) if len(loc) > 2 else stripped
                    failures.append(
                        TestFailure(
                            file_path=file_path,
                            test_name=test_name,
                            line_number=1,
                            error_message=error_msg[:500],
                            bug_type=_classify_bug_type(error_msg),
                            raw_output=stripped,
                        )
                    )

    return failures


def _parse_jest_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from Jest/Vitest output."""
    failures: list[TestFailure] = []

    # Look for "● suite › test" pattern
    blocks = re.split(r"●\s+", output)
    for block in blocks[1:]:  # skip first empty part
        lines = block.strip().splitlines()
        if not lines:
            continue

        header = lines[0]
        error_msg = "\n".join(lines[1:])[:500]

        # Try to find file reference
        file_match = re.search(r"at.*?[( ]([\w./\\]+):(\d+):\d+", block)
        file_path = file_match.group(1) if file_match else "unknown"
        line_number = int(file_match.group(2)) if file_match else 1

        parts = header.split(" › ")
        test_name = parts[-1].strip() if parts else header

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg.strip()[:500],
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[:1000],
            )
        )

    return failures


def _parse_dotnet_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from `dotnet test` output.

    Typical lines:
      Failed MethodName [12 ms]
        Error Message:
           Assert.Equal() Failure ...
        Stack Trace:
           at Namespace.Class.Method() in /path/File.cs:line 42
    """
    failures: list[TestFailure] = []

    # Split on "Failed " lines to get blocks per failure
    # Pattern: "  Failed TestName [123 ms]"
    failed_re = re.compile(r"^\s*Failed\s+(\S+)\s*(?:\[.*\])?\s*$", re.MULTILINE)

    positions = [(m.start(), m.group(1)) for m in failed_re.finditer(output)]
    for i, (start, test_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(output)
        block = output[start:end]

        # Extract error message (after "Error Message:" line)
        error_msg = ""
        msg_match = re.search(r"Error Message:\s*\n\s*(.+?)(?:\n\s*Stack Trace:|\Z)", block, re.DOTALL)
        if msg_match:
            error_msg = msg_match.group(1).strip()[:500]

        # Extract file path and line number from stack trace
        file_path = "unknown"
        line_number = 1
        stack_match = re.search(r"in\s+(.+?):line\s+(\d+)", block)
        if stack_match:
            file_path = stack_match.group(1).strip()
            line_number = int(stack_match.group(2))
        else:
            # Try C# compiler error format: File.cs(42,10)
            cs_match = re.search(r"([\w/.\\]+\.cs)\((\d+),\d+\)", block)
            if cs_match:
                file_path = cs_match.group(1)
                line_number = int(cs_match.group(2))

        if not error_msg:
            error_msg = block.strip()[:500]

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg,
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[:1000],
            )
        )

    # Also catch MSBuild/compiler errors: "error CS1002: ; expected"
    if not failures:
        cs_error_re = re.compile(
            r"([\w/.\\]+\.cs)\((\d+),\d+\):\s*error\s+(CS\d+):\s*(.+)",
        )
        for m in cs_error_re.finditer(output):
            failures.append(
                TestFailure(
                    file_path=m.group(1),
                    test_name=f"Build error {m.group(3)}",
                    line_number=int(m.group(2)),
                    error_message=m.group(4).strip()[:500],
                    bug_type="SYNTAX",
                    raw_output=m.group(0),
                )
            )

    return failures


def _parse_go_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from `go test -v` output.

    Typical pattern:
        --- FAIL: TestName (0.00s)
            file_test.go:42: expected X, got Y
    """
    failures: list[TestFailure] = []
    fail_re = re.compile(r"---\s*FAIL:\s+(\S+)\s*\(", re.MULTILINE)

    positions = [(m.start(), m.group(1)) for m in fail_re.finditer(output)]
    for i, (start, test_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else min(start + 2000, len(output))
        block = output[start:end]

        # Extract file:line from indented lines
        loc_match = re.search(r"(\S+\.go):(\d+):\s*(.+)", block)
        file_path = loc_match.group(1) if loc_match else "unknown"
        line_number = int(loc_match.group(2)) if loc_match else 1
        error_msg = loc_match.group(3).strip() if loc_match else block.strip()[:500]

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg[:500],
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[:1000],
            )
        )
    return failures


def _parse_rust_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Extract failures from `cargo test` output.

    Typical pattern:
        ---- tests::test_name stdout ----
        thread 'tests::test_name' panicked at 'assertion failed...', src/lib.rs:42:5
        test tests::test_name ... FAILED
    """
    failures: list[TestFailure] = []
    fail_re = re.compile(r"test\s+([\w:]+)\s+\.\.\.\s+FAILED", re.MULTILINE)

    for m in fail_re.finditer(output):
        test_name = m.group(1)
        # Look backwards for the panic message
        block_start = max(0, m.start() - 2000)
        block = output[block_start:m.end()]

        panic_match = re.search(
            r"panicked at '([^']+)',\s*([\w/.]+):(\d+):\d+", block
        )
        if panic_match:
            error_msg = panic_match.group(1)
            file_path = panic_match.group(2)
            line_number = int(panic_match.group(3))
        else:
            error_msg = f"Test {test_name} failed"
            file_path = "unknown"
            line_number = 1

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=test_name,
                line_number=line_number,
                error_message=error_msg[:500],
                bug_type=_classify_bug_type(error_msg),
                raw_output=block[-1000:],
            )
        )
    return failures


def _parse_generic_output(output: str, repo_dir: str) -> list[TestFailure]:
    """Best-effort parser for Java/Ruby/PHP/Elixir/any framework.

    Looks for common failure indicators and file:line patterns.
    """
    failures: list[TestFailure] = []
    seen: set[str] = set()

    # Generic patterns: "FAIL", "FAILED", "Error", "Failure" lines
    fail_line_re = re.compile(
        r"(?:FAIL(?:ED)?|Error|Failure|FAILURE)[:\s]+(.+)", re.MULTILINE
    )
    # file:line patterns across languages
    loc_re = re.compile(
        r"([\w/.\\-]+\.(?:java|kt|scala|rb|php|ex|exs|hs|lua|R|pl|jl|groovy|swift|dart|c|cpp|cc|rs|go|py|js|ts))"
        r"[:\(](\d+)"
    )

    for fm in fail_line_re.finditer(output):
        msg = fm.group(1).strip()[:500]
        key = msg[:80]
        if key in seen:
            continue
        seen.add(key)

        # Try to find a file:line near this failure
        context = output[max(0, fm.start() - 500):fm.end() + 500]
        loc_match = loc_re.search(context)
        file_path = loc_match.group(1) if loc_match else "unknown"
        line_number = int(loc_match.group(2)) if loc_match else 1

        failures.append(
            TestFailure(
                file_path=file_path,
                test_name=msg[:80],
                line_number=line_number,
                error_message=msg,
                bug_type=_classify_bug_type(msg),
                raw_output=context[:1000],
            )
        )

    return failures


async def _llm_classify_failures(output: str) -> list[TestFailure]:
    """Use LLM as fallback to extract and classify failures."""
    if not has_llm_keys():
        logger.warning("No Groq API keys — cannot use LLM fallback")
        return []

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(temperature=0.0)

    prompt = f"""Analyze this test output and extract each failure as JSON.
For each failure return:
- file_path: string
- test_name: string
- line_number: int
- error_message: string (brief)
- bug_type: one of LINTING, SYNTAX, LOGIC, TYPE_ERROR, IMPORT, INDENTATION

Return ONLY a JSON array. No markdown, no explanation.

Test output:
```
{output[:4000]}
```"""

    resp = await llm.ainvoke([
        SystemMessage(content="You are a test output parser. Return valid JSON only."),
        HumanMessage(content=prompt),
    ])

    import json
    try:
        raw = str(resp.content).strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            lines_out = raw.splitlines()
            if lines_out[0].startswith("```"):
                lines_out = lines_out[1:]
            if lines_out and lines_out[-1].strip() == "```":
                lines_out = lines_out[:-1]
            raw = "\n".join(lines_out)
        items = json.loads(raw)
        if not isinstance(items, list):
            items = [items]
        return [
            TestFailure(
                file_path=str(item.get("file_path") or "unknown"),
                test_name=str(item.get("test_name") or "unknown"),
                line_number=int(item.get("line_number") or 1),
                error_message=str(item.get("error_message") or "unknown error"),
                bug_type=item.get("bug_type") or "LOGIC",
                raw_output="",
            )
            for item in items
        ]
    except (json.JSONDecodeError, TypeError):
        logger.error("LLM returned invalid JSON for failure classification")
        return []


async def ast_analyzer(state: AgentState) -> AgentState:
    """
    Parse test output and classify each failure.
    Rule-based first, LLM fallback if empty.
    """
    run_id = state["run_id"]
    test_output = state.get("test_output", "")
    test_exit_code = state.get("test_exit_code", 0)
    framework = state.get("framework", "pytest")
    repo_dir = state.get("repo_dir", "")
    iteration = state.get("iteration", 1)
    step = iteration * 10 + 4

    await emit_thought(run_id, "ast_analyzer", "Analyzing test failures…", step)

    # If tests passed, no failures to analyze
    if test_exit_code == 0:
        await emit_thought(run_id, "ast_analyzer", "All tests passed ✓", step + 1)
        return {
            "failures": [],
            "current_node": "ast_analyzer",
        }

    # Rule-based parsing — dispatch by framework
    _JEST_LIKE = {"jest", "vitest", "ava", "jasmine", "hardhat", "truffle"}
    _DOTNET_LIKE = {"dotnet-test"}
    _GO_LIKE = {"go-test"}
    _RUST_LIKE = {"cargo-test"}
    _PYTEST_LIKE = {"pytest"}

    if framework in _JEST_LIKE:
        failures = _parse_jest_output(test_output, repo_dir)
    elif framework in _DOTNET_LIKE:
        failures = _parse_dotnet_output(test_output, repo_dir)
    elif framework in _GO_LIKE:
        failures = _parse_go_output(test_output, repo_dir)
    elif framework in _RUST_LIKE:
        failures = _parse_rust_output(test_output, repo_dir)
    elif framework in _PYTEST_LIKE:
        failures = _parse_pytest_output(test_output, repo_dir)
    else:
        # Generic parser works for Java/Ruby/PHP/Elixir/Haskell/etc.
        failures = _parse_generic_output(test_output, repo_dir)

    # LLM fallback if rule-based found nothing
    if not failures and test_exit_code != 0:
        await emit_thought(
            run_id, "ast_analyzer",
            "Rule-based parsing found no structured failures — trying LLM fallback…",
            step + 1,
        )
        failures = await _llm_classify_failures(test_output)

    # Ensure we cover all 6 required bug types for demo if we have failures
    seen_types = {f.bug_type for f in failures}
    logger.info(
        "ast_analyzer run=%s found %d failures, types=%s",
        run_id, len(failures), seen_types,
    )

    await emit_thought(
        run_id,
        "ast_analyzer",
        f"Found {len(failures)} failure(s): {', '.join(seen_types) if seen_types else 'none'}",
        step + 2,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="ast_analyzer",
        action_type="analysis",
        action_label=f"Classified {len(failures)} failures",
        payload={
            "failure_count": len(failures),
            "bug_types": list(seen_types),
        },
    )

    return {
        "failures": failures,
        "current_node": "ast_analyzer",
    }
