"""Release guards reject stale package declarations and incomplete bilingual notes."""

import shutil
from pathlib import Path

import pytest

from scripts.check_release import ROOT, validate


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    for name in (
        "pyproject.toml", "src/local_market_agent/__init__.py",
        "README.md", "docs/README.zh-CN.md", "docs/CHANGELOG.md",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    shutil.copytree(ROOT / "docs/releases", tmp_path / "docs/releases")
    return tmp_path


def test_release_tag_matches_package(release_tree: Path) -> None:
    version = validate(release_tree)
    assert validate(release_tree, f"v{version}") == version
    with pytest.raises(ValueError, match="Tag"):
        validate(release_tree, "v999.0.0")


def test_stale_python_version_rejected(release_tree: Path) -> None:
    (release_tree / "src/local_market_agent/__init__.py").write_text('__version__ = "0.0.0"\n')
    with pytest.raises(ValueError, match="Python version"):
        validate(release_tree)


def test_missing_chinese_notes_rejected(release_tree: Path) -> None:
    version = validate(release_tree)
    (release_tree / f"docs/releases/{version}.zh-CN.md").unlink()
    with pytest.raises(ValueError, match="release notes"):
        validate(release_tree)


def test_stale_chinese_homepage_rejected(release_tree: Path) -> None:
    (release_tree / "docs/README.zh-CN.md").write_text("# Old homepage\n")
    with pytest.raises(ValueError, match="docs/README.zh-CN.md"):
        validate(release_tree)
