"""Package a Claude skill folder into a `.skill` (zip) archive.

Mirrors the packaging behavior of Anthropic's `skill-creator`:
  * Output is a ZIP archive with `.skill` extension using ZIP_DEFLATED
  * The top-level entry in the zip is the skill folder name (e.g. ``hpc-cluster/``)
  * The following are excluded: ``__pycache__`` dirs, ``node_modules`` dirs,
    ``*.pyc`` files, ``.DS_Store`` files, and any ``evals/`` directory at the
    skill root.

Usage:
    python scripts/package_skill.py <path/to/skill-folder> [--output <dir-or-file>]

Defaults to writing ``<skill-name>.skill`` into ``dist/``.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

EXCLUDED_DIRS = {"__pycache__", "node_modules"}
EXCLUDED_FILENAMES = {".DS_Store"}


def _should_include(path: Path, skill_root: Path) -> bool:
    if path.is_dir():
        return False
    if path.name in EXCLUDED_FILENAMES:
        return False
    if path.suffix == ".pyc":
        return False
    rel_parts = path.relative_to(skill_root).parts
    if rel_parts and rel_parts[0] == "evals":
        return False
    for part in rel_parts:
        if part in EXCLUDED_DIRS:
            return False
    return True


def package_skill(skill_path: Path, output: Path) -> Path:
    skill_path = skill_path.resolve()
    if not skill_path.is_dir():
        raise SystemExit(f"error: not a directory: {skill_path}")
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        raise SystemExit(f"error: no SKILL.md in {skill_path}")

    if output.is_dir() or (not output.suffix and not output.exists()):
        output.mkdir(parents=True, exist_ok=True)
        out_file = output / f"{skill_path.name}.skill"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        out_file = output

    parent = skill_path.parent
    with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_path.rglob("*")):
            if not _should_include(path, skill_path):
                continue
            arcname = path.relative_to(parent).as_posix()
            zf.write(path, arcname)
    return out_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", type=Path, help="Path to the skill folder")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("dist"),
        help="Output directory or explicit .skill file path (default: dist/)",
    )
    args = parser.parse_args(argv)
    out = package_skill(args.skill_path, args.output)
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
