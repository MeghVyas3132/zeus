"""
repo_scanner node — clone the repo, detect language / framework, list test files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from git import Repo as GitRepo  # type: ignore[import-untyped]

from ...config import REPOS_DIR
from ...db import insert_trace
from ...events import emit_thought
from ..state import AgentState

logger = logging.getLogger("rift.node.repo_scanner")

# ── Universal language detection ────────────────────────────

# File extension → language (comprehensive map covering 30+ languages)
_EXT_MAP: dict[str, str] = {
    # Python
    ".py": "python", ".pyx": "python", ".pyi": "python",
    # JavaScript / TypeScript
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".vue": "javascript", ".svelte": "javascript",
    # C# / F# / VB.NET (.NET)
    ".cs": "csharp", ".fs": "fsharp", ".fsi": "fsharp", ".vb": "vbnet",
    # Java / Kotlin / Scala
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # Ruby
    ".rb": "ruby", ".rake": "ruby",
    # PHP
    ".php": "php",
    # Swift / Objective-C
    ".swift": "swift", ".m": "objc", ".mm": "objc",
    # C / C++
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hh": "cpp",
    # Dart / Flutter
    ".dart": "dart",
    # Elixir / Erlang
    ".ex": "elixir", ".exs": "elixir", ".erl": "erlang",
    # Haskell
    ".hs": "haskell", ".lhs": "haskell",
    # Lua
    ".lua": "lua",
    # R
    ".r": "r", ".R": "r",
    # Perl
    ".pl": "perl", ".pm": "perl", ".t": "perl",
    # Shell
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    # Clojure
    ".clj": "clojure", ".cljs": "clojure", ".cljc": "clojure",
    # Groovy
    ".groovy": "groovy",
    # Zig
    ".zig": "zig",
    # Nim
    ".nim": "nim",
    # Julia
    ".jl": "julia",
    # Solidity
    ".sol": "solidity",
}

# ── Universal test file detection ──────────────────────────

# Language → list of (glob_pattern, framework)
_DETECTION_MAP: dict[str, list[tuple[str, str]]] = {
    # Python
    "python": [
        ("**/test_*.py", "pytest"),
        ("**/tests.py", "pytest"),
        ("**/*_test.py", "pytest"),
        ("**/tests/**/*.py", "pytest"),
    ],
    # JavaScript
    "javascript": [
        ("**/*.test.js", "jest"),
        ("**/*.spec.js", "jest"),
        ("**/*.test.mjs", "jest"),
        ("**/*.test.jsx", "jest"),
        ("**/test/**/*.js", "mocha"),
        ("**/__tests__/**/*.js", "jest"),
    ],
    # TypeScript
    "typescript": [
        ("**/*.test.ts", "jest"),
        ("**/*.spec.ts", "jest"),
        ("**/*.test.tsx", "jest"),
        ("**/*.spec.tsx", "jest"),
        ("**/test/**/*.ts", "vitest"),
        ("**/__tests__/**/*.ts", "jest"),
    ],
    # C# (.NET)
    "csharp": [
        ("**/*Tests.cs", "dotnet-test"),
        ("**/*Test.cs", "dotnet-test"),
        ("**/*Spec.cs", "dotnet-test"),
        ("**/Tests/**/*.cs", "dotnet-test"),
        ("**/*.Tests/**/*.cs", "dotnet-test"),
        ("**/*.Test/**/*.cs", "dotnet-test"),
    ],
    # F# (.NET)
    "fsharp": [
        ("**/*Tests.fs", "dotnet-test"),
        ("**/*Test.fs", "dotnet-test"),
    ],
    # VB.NET
    "vbnet": [
        ("**/*Tests.vb", "dotnet-test"),
        ("**/*Test.vb", "dotnet-test"),
    ],
    # Java
    "java": [
        ("**/src/test/**/*.java", "maven"),
        ("**/*Test.java", "maven"),
        ("**/*Tests.java", "maven"),
        ("**/*Spec.java", "maven"),
    ],
    # Kotlin
    "kotlin": [
        ("**/src/test/**/*.kt", "gradle"),
        ("**/*Test.kt", "gradle"),
        ("**/*Tests.kt", "gradle"),
        ("**/*Spec.kt", "gradle"),
    ],
    # Scala
    "scala": [
        ("**/src/test/**/*.scala", "sbt-test"),
        ("**/*Spec.scala", "sbt-test"),
        ("**/*Test.scala", "sbt-test"),
    ],
    # Go
    "go": [
        ("**/*_test.go", "go-test"),
    ],
    # Rust
    "rust": [
        ("**/tests/**/*.rs", "cargo-test"),
        ("**/src/**/*.rs", "cargo-test"),  # inline #[test] detected at runtime
    ],
    # Ruby
    "ruby": [
        ("**/spec/**/*_spec.rb", "rspec"),
        ("**/test/**/*_test.rb", "minitest"),
        ("**/test/**/*.rb", "minitest"),
    ],
    # PHP
    "php": [
        ("**/tests/**/*Test.php", "phpunit"),
        ("**/tests/**/*.php", "phpunit"),
        ("**/*Test.php", "phpunit"),
    ],
    # Swift
    "swift": [
        ("**/Tests/**/*.swift", "swift-test"),
        ("**/*Tests.swift", "swift-test"),
    ],
    # Dart / Flutter
    "dart": [
        ("**/test/**/*_test.dart", "dart-test"),
        ("**/*_test.dart", "dart-test"),
    ],
    # Elixir
    "elixir": [
        ("**/test/**/*_test.exs", "mix-test"),
        ("**/*_test.exs", "mix-test"),
    ],
    # Haskell
    "haskell": [
        ("**/test/**/*.hs", "cabal-test"),
        ("**/Test/**/*.hs", "cabal-test"),
    ],
    # C / C++
    "c": [
        ("**/test*/**/*.c", "ctest"),
        ("**/*_test.c", "ctest"),
    ],
    "cpp": [
        ("**/test*/**/*.cpp", "ctest"),
        ("**/*_test.cpp", "ctest"),
        ("**/*_test.cc", "ctest"),
    ],
    # Clojure
    "clojure": [
        ("**/test/**/*.clj", "lein-test"),
        ("**/*_test.clj", "lein-test"),
    ],
    # Lua
    "lua": [
        ("**/test*/**/*.lua", "busted"),
        ("**/*_spec.lua", "busted"),
    ],
    # R
    "r": [
        ("**/tests/**/*.R", "testthat"),
        ("**/tests/testthat/**/*.R", "testthat"),
    ],
    # Perl
    "perl": [
        ("**/t/**/*.t", "prove"),
        ("**/*.t", "prove"),
    ],
    # Groovy
    "groovy": [
        ("**/src/test/**/*.groovy", "gradle"),
        ("**/*Test.groovy", "gradle"),
        ("**/*Spec.groovy", "gradle"),
    ],
    # Julia
    "julia": [
        ("**/test/**/*.jl", "julia-test"),
        ("**/test/runtests.jl", "julia-test"),
    ],
    # Zig
    "zig": [
        ("**/test*.zig", "zig-test"),
    ],
    # Nim
    "nim": [
        ("**/tests/**/*.nim", "nim-test"),
        ("**/*_test.nim", "nim-test"),
    ],
    # Solidity
    "solidity": [
        ("**/test/**/*.sol", "hardhat"),
        ("**/test/**/*.js", "hardhat"),
        ("**/test/**/*.ts", "hardhat"),
    ],
}

# Known test-related npm packages → framework
_NPM_FRAMEWORK_MAP: dict[str, str] = {
    "jest": "jest",
    "@jest/core": "jest",
    "react-scripts": "jest",
    "vitest": "vitest",
    "mocha": "mocha",
    "ava": "ava",
    "tap": "tap",
    "jasmine": "jasmine",
    "cypress": "cypress",
    "playwright": "playwright",
    "@playwright/test": "playwright",
    "@vue/test-utils": "vitest",
    "@testing-library/jest-dom": "jest",
    "@testing-library/react": "jest",
    "@testing-library/vue": "vitest",
    "hardhat": "hardhat",
}

# Project file → (language, framework) — for repos where extension-based detection
# might miss (e.g. no source files yet, or only config files)
_PROJECT_FILE_MAP: list[tuple[str, str, str]] = [
    # (.NET)
    ("**/*.sln", "csharp", "dotnet-test"),
    ("**/*.csproj", "csharp", "dotnet-test"),
    ("**/*.fsproj", "fsharp", "dotnet-test"),
    ("**/*.vbproj", "vbnet", "dotnet-test"),
    # Java / Kotlin / Scala
    ("pom.xml", "java", "maven"),
    ("build.gradle", "java", "gradle"),
    ("build.gradle.kts", "kotlin", "gradle"),
    ("build.sbt", "scala", "sbt-test"),
    # Go
    ("go.mod", "go", "go-test"),
    # Rust
    ("Cargo.toml", "rust", "cargo-test"),
    # Ruby
    ("Gemfile", "ruby", "bundler"),
    # PHP
    ("composer.json", "php", "phpunit"),
    # Swift
    ("Package.swift", "swift", "swift-test"),
    # Dart / Flutter
    ("pubspec.yaml", "dart", "dart-test"),
    # Elixir
    ("mix.exs", "elixir", "mix-test"),
    # Haskell
    ("*.cabal", "haskell", "cabal-test"),
    ("stack.yaml", "haskell", "stack-test"),
    # Clojure
    ("project.clj", "clojure", "lein-test"),
    ("deps.edn", "clojure", "clj-test"),
    # Nim
    ("*.nimble", "nim", "nim-test"),
    # Julia
    ("Project.toml", "julia", "julia-test"),
    # Zig
    ("build.zig", "zig", "zig-test"),
    # Node.js / JS (last — many languages have package.json too)
    ("package.json", "javascript", "npm-test"),
    # Python (last-resort)
    ("pyproject.toml", "python", "pytest"),
    ("setup.py", "python", "pytest"),
    ("setup.cfg", "python", "pytest"),
    ("requirements.txt", "python", "pytest"),
]


_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".tox", ".venv", "venv",
               "vendor", "dist", "build", "_build", ".build", ".dart_tool",
               "Pods", ".gradle", ".idea", ".vs", "bin", "obj", "target",
               "_deps", "deps", "zig-cache", "zig-out"}


def _detect_language(repo_path: Path) -> str:
    """Heuristic: count file extensions in the repo, skip noisy dirs."""
    counts: dict[str, int] = {}
    for f in repo_path.rglob("*"):
        if f.is_file() and not (_SKIP_DIRS & set(f.parts)) and f.suffix in _EXT_MAP:
            lang = _EXT_MAP[f.suffix]
            counts[lang] = counts.get(lang, 0) + 1

    # Merge related languages: TS → JS ecosystem
    if "typescript" in counts and "javascript" in counts:
        counts["typescript"] += counts.pop("javascript")

    if counts:
        return max(counts, key=counts.get)  # type: ignore[arg-type]

    # Fallback: scan project files from _PROJECT_FILE_MAP
    for glob_pat, lang, _fw in _PROJECT_FILE_MAP:
        if list(repo_path.glob(glob_pat)):
            return lang

    return "python"  # ultimate fallback


def _read_package_json(repo_path: Path) -> dict:
    """Safely read and parse package.json if it exists."""
    pkg_path = repo_path / "package.json"
    if not pkg_path.exists():
        return {}
    try:
        return json.loads(pkg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _detect_framework_from_pkg(pkg: dict) -> str | None:
    """Detect test framework from package.json deps and scripts."""
    all_deps: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        all_deps.update(pkg.get(key, {}))

    # Check deps for known test packages
    for dep_name, framework in _NPM_FRAMEWORK_MAP.items():
        if dep_name in all_deps:
            return framework

    # Check scripts for test runner hints
    scripts = pkg.get("scripts", {})
    test_script = scripts.get("test", "")
    if "vitest" in test_script:
        return "vitest"
    if "jest" in test_script:
        return "jest"
    if "mocha" in test_script:
        return "mocha"
    if "pytest" in test_script:
        return "pytest"

    return None


def _detect_framework(repo_path: Path, language: str) -> tuple[str, list[str]]:
    """Return (framework_name, list_of_test_files)."""
    # 1. Check glob patterns for test files based on detected language
    patterns = _DETECTION_MAP.get(language, [])
    for glob_pattern, framework in patterns:
        matches = sorted(
            str(p.relative_to(repo_path))
            for p in repo_path.glob(glob_pattern)
            if not (_SKIP_DIRS & set(p.parts))
        )
        if matches:
            return framework, matches

    # 2. Config-file overrides (language-specific)
    _CONFIG_CHECKS: list[tuple[str, str, str | None]] = [
        # Python
        ("pytest.ini", "pytest", None),
        ("setup.cfg", "pytest", None),
        ("tox.ini", "pytest", None),
        # JS / TS
        ("jest.config.js", "jest", None),
        ("jest.config.ts", "jest", None),
        ("jest.config.mjs", "jest", None),
        ("jest.config.cjs", "jest", None),
        ("vitest.config.ts", "vitest", None),
        ("vitest.config.js", "vitest", None),
        ("vitest.config.mts", "vitest", None),
        (".mocharc.yml", "mocha", None),
        (".mocharc.json", "mocha", None),
        (".mocharc.js", "mocha", None),
        # Ruby
        (".rspec", "rspec", None),
        ("Rakefile", "minitest", "ruby"),
        # PHP
        ("phpunit.xml", "phpunit", None),
        ("phpunit.xml.dist", "phpunit", None),
        # Elixir
        ("mix.exs", "mix-test", "elixir"),
        # Haskell
        ("stack.yaml", "stack-test", "haskell"),
        # Solidity
        ("hardhat.config.js", "hardhat", None),
        ("hardhat.config.ts", "hardhat", None),
        ("truffle-config.js", "truffle", None),
        ("foundry.toml", "forge-test", None),
    ]
    for fname, fw, lang_guard in _CONFIG_CHECKS:
        if (repo_path / fname).exists():
            if lang_guard is None or language == lang_guard:
                return fw, []

    # 3. Project-file fallback from _PROJECT_FILE_MAP
    for glob_pat, _lang, fw in _PROJECT_FILE_MAP:
        if _lang == language and list(repo_path.glob(glob_pat)):
            return fw, []

    # 4. package.json detection for JS/TS ecosystem
    pkg = _read_package_json(repo_path)
    if pkg:
        fw = _detect_framework_from_pkg(pkg)
        if fw:
            return fw, []

        scripts = pkg.get("scripts", {})
        if "test" in scripts and scripts["test"].strip():
            return "npm-test", []

    return "unknown", []


async def repo_scanner(state: AgentState) -> AgentState:
    """
    Clone the repository, detect language/framework, list test files.
    """
    run_id = state["run_id"]
    repo_url = state["repo_url"]
    branch_name = state["branch_name"]
    step = state.get("iteration", 0) * 10 + 1

    await emit_thought(run_id, "repo_scanner", f"Cloning {repo_url}…", step)

    repo_dir = REPOS_DIR / run_id
    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)
    repo_dir.mkdir(parents=True, exist_ok=True)

    # Clone in a thread to avoid blocking the event loop
    def _clone() -> GitRepo:
        repo = GitRepo.clone_from(repo_url, str(repo_dir), depth=1)
        # Create and checkout the healing branch
        if branch_name not in [h.name for h in repo.heads]:
            repo.create_head(branch_name)
        repo.heads[branch_name].checkout()  # type: ignore[union-attr]
        return repo

    await asyncio.to_thread(_clone)

    language = _detect_language(repo_dir)
    framework, test_files = _detect_framework(repo_dir, language)

    await emit_thought(
        run_id,
        "repo_scanner",
        f"Detected {language}/{framework} — {len(test_files)} test file(s)",
        step + 1,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="repo_scanner",
        action_type="clone",
        action_label=f"Cloned {repo_url}, detected {language}/{framework}",
        payload={
            "language": language,
            "framework": framework,
            "test_file_count": len(test_files),
        },
    )

    return {
        "repo_dir": str(repo_dir),
        "language": language,
        "framework": framework,
        "test_files": test_files,
        "current_node": "repo_scanner",
    }
