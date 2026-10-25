"""Print a version's section of CHANGELOG.md; fail when it has none.

    python scripts/changelog.py 0.3.2

The release workflow runs this before it builds, so no version reaches PyPI
without its entry, and the release notes are this output: the text is written
once, in the changelog.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section(text: str, version: str) -> str:
    """The body of ``## [version]``, up to the next heading of that level.

    Raises:
        LookupError: If the version has no section, or an empty one
    """
    heading = re.compile(rf"^## \[{re.escape(version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?$", re.M)
    found = heading.search(text)
    if found is None:
        raise LookupError(f"CHANGELOG.md has no section ## [{version}] - <date>")
    rest = text[found.end() :]
    following = re.search(r"^## |^\[[^\]]+\]: ", rest, re.M)
    body = rest[: following.start() if following else len(rest)].strip()
    if not body:
        raise LookupError(f"The section ## [{version}] in CHANGELOG.md is empty")
    return body


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: changelog.py VERSION", file=sys.stderr)
        return 2
    try:
        print(section(CHANGELOG.read_text(encoding="utf-8"), argv[0]))
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
