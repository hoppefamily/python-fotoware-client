# Contributing

This template follows the Foerde Baumarkt engineering guidance.

- Editor-agnostic: do not commit editor-specific files (see docs/editor-agnostic.md)
- Pre-commit hooks: install with `pre-commit install` for automated quality checks
- CI must pass: Pre-commit, Ruff lint/format, MyPy, PyTest, Gitleaks
- No secrets in code or logs

## Local workflow

Use the Makefile/CLI documented in docs/ci-cd.md, or leverage pre-commit hooks for automated quality assurance.
