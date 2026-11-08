"""Validate application release metadata without importing runtime dependencies."""

import argparse
import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(root: Path, tag: str | None = None) -> str:
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ValueError(f"Expected MAJOR.MINOR.PATCH, got {version!r}")
    module = ast.parse((root / "src/local_market_agent/__init__.py").read_text())
    declared = [
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
    ]
    if declared != [version]:
        raise ValueError(f"Python version {declared!r} does not match package {version}")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match v{version}")
    for name in ("README.md", "README.zh-CN.md"):
        if f"**{version}**" not in (root / name).read_text():
            raise ValueError(f"{name} must display **{version}**")
    changelog = (root / "CHANGELOG.md").read_text()
    if not re.search(rf"^## {re.escape(version)} — \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.M):
        raise ValueError(f"CHANGELOG.md lacks a dated {version} entry")
    for suffix in (".md", ".zh-CN.md"):
        path = root / "docs/releases" / f"{version}{suffix}"
        if not path.is_file() or not path.read_text().startswith(f"# Local Market Agent {version}\n"):
            raise ValueError(f"Missing or incorrect release notes: {path.relative_to(root)}")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Expected Git release tag, e.g. v0.2.0")
    args = parser.parse_args()
    try:
        version = validate(ROOT, args.tag)
    except (ValueError, OSError, KeyError, SyntaxError) as exc:
        parser.exit(1, f"Release check failed: {exc}\n")
    print(f"Release metadata consistent: {version}")


if __name__ == "__main__":
    main()
