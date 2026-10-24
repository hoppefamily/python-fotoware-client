# Editor-agnostic repositories

All template-based repositories follow an editor-agnostic policy:

- No editor-specific configuration is required to work on the codebase.
- Shared behavior is defined via project tooling and config files (Makefile, pytest.ini, ruff.toml, mypy.ini, pyproject.toml, etc.).
- Editor folders (e.g., `.vscode/`, `.idea/`) are ignored via `.gitignore`.

## Rationale

- Keeps the codebase portable across VS Code, PyCharm, Vim, etc.
- Reduces config drift and "works on my machine" issues.
- CI is the source of truth; local workflows mirror CI with the same commands.

## What we commit

- Language/tooling config: `pyproject.toml`, `ruff.toml`, `mypy.ini`, `pytest.ini`, `Makefile`.
- Scripts that run the application or support CI tasks: `scripts/`.

## What we do not commit

- Editor-specific settings and launch/task files (e.g., `.vscode/*`, `.idea/*`).
- Local env files: `.env`, `.envrc`, virtual envs (e.g., `.venv/`).

These are enforced by `.gitignore`.

## Local convenience

You can keep local editor helpers (e.g., `.vscode/launch.json`, `.vscode/tasks.json`) on your machine. They are intentionally ignored by Git.

If a team decides to share a specific helper for onboarding, prefer documenting the equivalent CLI/Makefile command in `README.md` and `docs/development.md` rather than committing editor files.

## How to run tasks

- Lint: `ruff check . && ruff format --check .`
- Types: `mypy .`
- Tests: `pytest` (driven by `pytest.ini`)
- All via Makefile: `make lint type test`

## Exceptions

If a cross-editor standard exists (e.g., `.editorconfig`), it may be committed.

Any exception must be discussed and documented in a PR, including rationale and rollback plan.
