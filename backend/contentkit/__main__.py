"""python -m contentkit validate <content-root> | schemas <content-root>"""

import sys
from pathlib import Path

from .schema_export import export_schemas
from .validate import format_issues, validate_repository


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"validate", "schemas"}:
        print(__doc__)
        return 2
    root = Path(sys.argv[2])
    if sys.argv[1] == "schemas":
        for path in export_schemas(root / "schemas"):
            print(f"wrote {path}")
        return 0
    repo = validate_repository(root)
    if repo.issues:
        print(format_issues(repo.issues))
    print(
        f"{len(repo.lessons)} lessons, {len(repo.outlines)} outlined; "
        f"{len(repo.errors)} errors, {len(repo.issues) - len(repo.errors)} warnings"
    )
    return 1 if repo.errors else 0


if __name__ == "__main__":
    sys.exit(main())
