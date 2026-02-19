"""
test_runner node — execute tests, capture output, determine exit code.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from ...db import insert_trace
from ...events import emit_thought
from ..state import AgentState

logger = logging.getLogger("rift.node.test_runner")

# Framework → command template (universal: 30+ frameworks)
_COMMANDS: dict[str, list[str]] = {
    # ── Python ──
    "pytest":       ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"],
    # ── JavaScript / TypeScript ──
    "jest":         ["npx", "jest", "--no-coverage", "--verbose"],
    "vitest":       ["npx", "vitest", "run", "--reporter=verbose"],
    "mocha":        ["npx", "mocha", "--recursive"],
    "ava":          ["npx", "ava", "--verbose"],
    "tap":          ["npx", "tap"],
    "jasmine":      ["npx", "jasmine"],
    "cypress":      ["npx", "cypress", "run"],
    "playwright":   ["npx", "playwright", "test"],
    "npm-test":     ["npm", "test", "--", "--no-coverage"],
    # ── Solidity (JS-based) ──
    "hardhat":      ["npx", "hardhat", "test"],
    "truffle":      ["npx", "truffle", "test"],
    "forge-test":   ["forge", "test", "-vv"],
    # ── .NET (C#, F#, VB.NET) ──
    "dotnet-test":  ["dotnet", "test", "--verbosity", "normal"],
    # ── Java / Kotlin / Groovy ──
    "maven":        ["mvn", "test", "-B"],
    "gradle":       ["./gradlew", "test"],
    # ── Scala ──
    "sbt-test":     ["sbt", "test"],
    # ── Go ──
    "go-test":      ["go", "test", "-v", "./..."],
    # ── Rust ──
    "cargo-test":   ["cargo", "test"],
    # ── Ruby ──
    "rspec":        ["bundle", "exec", "rspec"],
    "minitest":     ["bundle", "exec", "rake", "test"],
    "bundler":      ["bundle", "exec", "rake", "test"],
    # ── PHP ──
    "phpunit":      ["./vendor/bin/phpunit"],
    # ── Swift ──
    "swift-test":   ["swift", "test"],
    # ── Dart / Flutter ──
    "dart-test":    ["dart", "test"],
    "flutter-test": ["flutter", "test"],
    # ── Elixir ──
    "mix-test":     ["mix", "test"],
    # ── Haskell ──
    "cabal-test":   ["cabal", "test"],
    "stack-test":   ["stack", "test"],
    # ── Clojure ──
    "lein-test":    ["lein", "test"],
    "clj-test":     ["clojure", "-M:test"],
    # ── Lua ──
    "busted":       ["busted", "--verbose"],
    # ── R ──
    "testthat":     ["Rscript", "-e", "testthat::test_dir('tests')"],
    # ── Perl ──
    "prove":        ["prove", "-v", "-r", "t"],
    # ── Julia ──
    "julia-test":   ["julia", "--project=.", "-e", "using Pkg; Pkg.test()"],
    # ── Zig ──
    "zig-test":     ["zig", "build", "test"],
    # ── Nim ──
    "nim-test":     ["nimble", "test"],
    # ── C / C++ ──
    "ctest":        ["ctest", "--test-dir", "build", "--output-on-failure"],
    "make-test":    ["make", "test"],
}

# Frameworks that need `npm install` before running
_NODE_FRAMEWORKS = {
    "jest", "vitest", "mocha", "ava", "tap", "jasmine",
    "cypress", "playwright", "npm-test", "hardhat", "truffle",
}

# Frameworks that need a restore/build step before running tests
_DOTNET_FRAMEWORKS = {"dotnet-test"}

# Frameworks that need `bundle install` before running
_RUBY_FRAMEWORKS = {"rspec", "minitest", "bundler"}

# Frameworks that need `composer install` before running
_PHP_FRAMEWORKS = {"phpunit"}

# Frameworks that need `mix deps.get` before running
_ELIXIR_FRAMEWORKS = {"mix-test"}

# Frameworks that need `dart pub get` before running
_DART_FRAMEWORKS = {"dart-test", "flutter-test"}


async def _ensure_node_deps(repo_dir: str, run_id: str, step: int) -> None:
    """
    If the repo has a package.json, run `npm install` to ensure
    test dependencies (jest, vitest, etc.) are available.
    """
    pkg_json = Path(repo_dir) / "package.json"
    node_modules = Path(repo_dir) / "node_modules"

    if not pkg_json.exists():
        return

    if node_modules.exists():
        return  # already installed

    await emit_thought(run_id, "test_runner", "Installing Node.js dependencies…", step)

    try:
        proc = await asyncio.create_subprocess_exec(
            "npm", "install", "--no-audit", "--no-fund", "--prefer-offline",
            cwd=repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "CI": "true", "NODE_ENV": "development"},
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""

        if proc.returncode != 0:
            logger.warning(
                "npm install failed (exit=%d) for run %s: %s",
                proc.returncode, run_id, output[:500],
            )
            await emit_thought(
                run_id, "test_runner",
                f"npm install failed (exit={proc.returncode}) — tests may fail",
                step,
            )
        else:
            logger.info("npm install succeeded for run %s", run_id)
    except asyncio.TimeoutError:
        logger.warning("npm install timed out for run %s", run_id)
        await emit_thought(run_id, "test_runner", "npm install timed out (120s)", step)
    except FileNotFoundError:
        logger.warning("npm not found for run %s", run_id)


async def _ensure_dotnet_deps(repo_dir: str, run_id: str, step: int) -> None:
    """
    Run `dotnet restore` then `dotnet build` to ensure test projects compile.
    """
    await emit_thought(run_id, "test_runner", "Restoring .NET dependencies…", step)

    for cmd_label, cmd in [
        ("dotnet restore", ["dotnet", "restore"]),
        ("dotnet build", ["dotnet", "build", "--no-restore"]),
    ]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"},
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""

            if proc.returncode != 0:
                logger.warning(
                    "%s failed (exit=%d) for run %s: %s",
                    cmd_label, proc.returncode, run_id, output[:500],
                )
                await emit_thought(
                    run_id, "test_runner",
                    f"{cmd_label} failed (exit={proc.returncode})",
                    step,
                )
                return  # Don't continue to build if restore failed
            else:
                logger.info("%s succeeded for run %s", cmd_label, run_id)
        except asyncio.TimeoutError:
            logger.warning("%s timed out for run %s", cmd_label, run_id)
            return
        except FileNotFoundError:
            logger.warning("dotnet SDK not found for run %s", run_id)
            await emit_thought(run_id, "test_runner", "dotnet SDK not available", step)
            return


async def _ensure_ruby_deps(repo_dir: str, run_id: str, step: int) -> None:
    """Run `bundle install` for Ruby projects."""
    gemfile = Path(repo_dir) / "Gemfile"
    if not gemfile.exists():
        return
    await emit_thought(run_id, "test_runner", "Installing Ruby dependencies…", step)
    try:
        proc = await asyncio.create_subprocess_exec(
            "bundle", "install", "--quiet",
            cwd=repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        if proc.returncode != 0:
            out = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            logger.warning("bundle install failed (exit=%d) for run %s: %s", proc.returncode, run_id, out[:500])
    except (asyncio.TimeoutError, FileNotFoundError):
        logger.warning("bundle install failed/skipped for run %s", run_id)


async def _ensure_php_deps(repo_dir: str, run_id: str, step: int) -> None:
    """Run `composer install` for PHP projects."""
    composer = Path(repo_dir) / "composer.json"
    if not composer.exists():
        return
    await emit_thought(run_id, "test_runner", "Installing PHP dependencies…", step)
    try:
        proc = await asyncio.create_subprocess_exec(
            "composer", "install", "--no-interaction", "--quiet",
            cwd=repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        if proc.returncode != 0:
            out = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            logger.warning("composer install failed (exit=%d) for run %s: %s", proc.returncode, run_id, out[:500])
    except (asyncio.TimeoutError, FileNotFoundError):
        logger.warning("composer install failed/skipped for run %s", run_id)


async def _ensure_elixir_deps(repo_dir: str, run_id: str, step: int) -> None:
    """Run `mix deps.get` for Elixir projects."""
    mixfile = Path(repo_dir) / "mix.exs"
    if not mixfile.exists():
        return
    await emit_thought(run_id, "test_runner", "Installing Elixir dependencies…", step)
    try:
        proc = await asyncio.create_subprocess_exec(
            "mix", "deps.get",
            cwd=repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "MIX_ENV": "test"},
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            out = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            logger.warning("mix deps.get failed (exit=%d) for run %s: %s", proc.returncode, run_id, out[:500])
    except (asyncio.TimeoutError, FileNotFoundError):
        logger.warning("mix deps.get failed/skipped for run %s", run_id)


async def _ensure_dart_deps(repo_dir: str, run_id: str, step: int) -> None:
    """Run `dart pub get` or `flutter pub get` for Dart projects."""
    pubspec = Path(repo_dir) / "pubspec.yaml"
    if not pubspec.exists():
        return
    await emit_thought(run_id, "test_runner", "Installing Dart/Flutter dependencies…", step)
    # Detect flutter vs plain dart
    cmd = ["flutter", "pub", "get"] if (Path(repo_dir) / ".flutter-plugins").exists() else ["dart", "pub", "get"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            out = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            logger.warning("dart pub get failed (exit=%d) for run %s: %s", proc.returncode, run_id, out[:500])
    except (asyncio.TimeoutError, FileNotFoundError):
        logger.warning("dart pub get failed/skipped for run %s", run_id)


async def _ensure_cmake_build(repo_dir: str, run_id: str, step: int) -> None:
    """Run cmake configure + build for C/C++ projects using ctest."""
    cmake_lists = Path(repo_dir) / "CMakeLists.txt"
    if not cmake_lists.exists():
        return
    build_dir = Path(repo_dir) / "build"
    build_dir.mkdir(exist_ok=True)
    await emit_thought(run_id, "test_runner", "Building C/C++ project with CMake…", step)
    for cmd_label, cmd in [
        ("cmake configure", ["cmake", ".."]),
        ("cmake build", ["cmake", "--build", "."]),
    ]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(build_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            if proc.returncode != 0:
                out = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                logger.warning("%s failed (exit=%d) for run %s: %s", cmd_label, proc.returncode, run_id, out[:500])
                return
        except (asyncio.TimeoutError, FileNotFoundError):
            logger.warning("%s failed/skipped for run %s", cmd_label, run_id)
            return


async def test_runner(state: AgentState) -> AgentState:
    """
    Run the test suite in the cloned repo and capture output.
    """
    run_id = state["run_id"]
    repo_dir = state["repo_dir"]
    framework = state.get("framework", "pytest")
    language = state.get("language", "python")
    iteration = state.get("iteration", 1)
    step = iteration * 10 + 3

    await emit_thought(run_id, "test_runner", f"Running tests (iteration {iteration})…", step)

    # For unknown JS/TS frameworks, try to resolve from package.json
    if framework == "unknown" and language in ("javascript", "typescript"):
        framework = _resolve_js_framework(repo_dir)
        logger.info("Resolved unknown JS framework to '%s' for run %s", framework, run_id)

    # Install Node.js deps if needed (jest/vitest/mocha/npm-test)
    if framework in _NODE_FRAMEWORKS:
        await _ensure_node_deps(repo_dir, run_id, step)

    # Restore + build .NET projects if needed
    if framework in _DOTNET_FRAMEWORKS:
        await _ensure_dotnet_deps(repo_dir, run_id, step)

    # Ruby: bundle install
    if framework in _RUBY_FRAMEWORKS:
        await _ensure_ruby_deps(repo_dir, run_id, step)

    # PHP: composer install
    if framework in _PHP_FRAMEWORKS:
        await _ensure_php_deps(repo_dir, run_id, step)

    # Elixir: mix deps.get
    if framework in _ELIXIR_FRAMEWORKS:
        await _ensure_elixir_deps(repo_dir, run_id, step)

    # Dart/Flutter: dart pub get
    if framework in _DART_FRAMEWORKS:
        await _ensure_dart_deps(repo_dir, run_id, step)

    # C/C++ with CMake: cmake configure + build
    if framework == "ctest":
        await _ensure_cmake_build(repo_dir, run_id, step)

    cmd = _COMMANDS.get(framework, _COMMANDS["pytest"])

    test_output, exit_code = await _run_cmd(cmd, repo_dir)

    # If primary command failed with "no tests" (exit=5 for jest) or
    # command not found (127), try npm test as fallback for JS/TS repos
    if exit_code in (5, 127) and language in ("javascript", "typescript") and framework != "npm-test":
        logger.info(
            "Primary test command failed (exit=%d), trying npm test fallback for run %s",
            exit_code, run_id,
        )
        await emit_thought(
            run_id, "test_runner",
            f"{framework} returned exit={exit_code}, trying npm test fallback…",
            step,
        )
        fallback_output, fallback_code = await _run_cmd(["npm", "test"], repo_dir)
        # Use fallback if it produced more output (even if it also failed)
        if len(fallback_output) > len(test_output) or fallback_code == 0:
            test_output = fallback_output
            exit_code = fallback_code
            framework = "npm-test"

    # If still no useful test output for JS repos, try running with
    # npx to discover test files directly
    if exit_code in (5, 127) and len(test_output) < 100 and language in ("javascript", "typescript"):
        logger.info("Attempting direct pytest fallback for Python files in run %s", run_id)
        # Check if there are Python test files (mixed repo like test-vue-app)
        py_test_files = list(Path(repo_dir).rglob("test_*.py")) + list(Path(repo_dir).rglob("*_test.py"))
        if py_test_files:
            await emit_thought(
                run_id, "test_runner",
                f"No JS tests found — detected {len(py_test_files)} Python test file(s), running pytest…",
                step,
            )
            py_output, py_code = await _run_cmd(
                ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"],
                repo_dir,
            )
            if len(py_output) > len(test_output):
                test_output = py_output
                exit_code = py_code
                framework = "pytest"

    await emit_thought(
        run_id,
        "test_runner",
        f"Tests {'PASSED' if exit_code == 0 else 'FAILED'} (exit={exit_code}, {len(test_output)} chars output)",
        step + 1,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="test_runner",
        action_type="test_execution",
        action_label=f"Ran {framework} — exit {exit_code}",
        payload={
            "framework": framework,
            "exit_code": exit_code,
            "output_length": len(test_output),
        },
        thought_text=test_output[:2000],
    )

    return {
        "test_output": test_output,
        "test_exit_code": exit_code,
        "current_node": "test_runner",
    }


async def _run_cmd(cmd: list[str], cwd: str) -> tuple[str, int]:
    """Run a command and return (stdout, exit_code)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=_build_env(cwd),
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        return output, proc.returncode or 0
    except asyncio.TimeoutError:
        return "ERROR: Test execution timed out after 120s", 1
    except FileNotFoundError:
        return f"ERROR: Test command not found — {cmd[0]}", 127


def _resolve_js_framework(repo_dir: str) -> str:
    """Try to figure out the right test framework from package.json."""
    pkg_path = Path(repo_dir) / "package.json"
    if not pkg_path.exists():
        return "npm-test"
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "npm-test"

    all_deps: dict[str, str] = {}
    for key in ("dependencies", "devDependencies"):
        all_deps.update(pkg.get(key, {}))

    if "vitest" in all_deps or "@vitest/runner" in all_deps:
        return "vitest"
    if "jest" in all_deps or "@jest/core" in all_deps or "react-scripts" in all_deps:
        return "jest"
    if "mocha" in all_deps:
        return "mocha"

    # Check test script content
    test_script = pkg.get("scripts", {}).get("test", "")
    if "vitest" in test_script:
        return "vitest"
    if "jest" in test_script:
        return "jest"
    if "mocha" in test_script:
        return "mocha"

    # Has a test script at all?
    if test_script.strip():
        return "npm-test"

    return "npm-test"


def _build_env(repo_dir: str) -> dict[str, str]:
    """Build an environment dict for the subprocess."""
    import os

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = repo_dir
    # Disable interactive prompts
    env["CI"] = "true"
    return env
