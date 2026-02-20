from __future__ import annotations

import json
from pathlib import Path

from app.graph.nodes.fix_generator import _fix_import
from app.graph.state import TestFailure


def _failure(error: str, line: int = 1) -> TestFailure:
    return TestFailure(
        file_path="sample.py",
        test_name="sample_test",
        line_number=line,
        error_message=error,
        bug_type="IMPORT",
        raw_output="",
    )


def test_fix_import_rewrites_local_absolute_import_to_relative(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    pkg_dir = repo_dir / "pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "utils.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

    source = "from utils import helper\n\nprint(helper())\n"
    source_path = pkg_dir / "app.py"
    source_path.write_text(source, encoding="utf-8")

    fixed = _fix_import(
        _failure("ModuleNotFoundError: No module named 'utils'"),
        source,
        source_path,
        repo_dir,
    )

    assert fixed is not None
    assert "from .utils import helper" in fixed


def test_fix_import_adds_missing_requirement(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    req_path = repo_dir / "requirements.txt"
    original = "pytest==8.3.4\n"

    fixed = _fix_import(
        _failure("No module named 'requests'"),
        original,
        req_path,
        repo_dir,
    )

    assert fixed is not None
    assert "requests" in fixed
    assert fixed.endswith("\n")


def test_fix_import_adds_missing_dev_dependency_to_package_json(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    pkg_path = repo_dir / "package.json"
    original = json.dumps({"name": "demo", "devDependencies": {"vitest": "^1.6.0"}})

    fixed = _fix_import(
        _failure("Cannot find module 'lodash'"),
        original,
        pkg_path,
        repo_dir,
    )

    assert fixed is not None
    parsed = json.loads(fixed)
    assert parsed["devDependencies"]["lodash"] == "latest"
