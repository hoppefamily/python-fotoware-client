# template-python

[![tests](https://github.com/foerdebaumarkt/template-python/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/foerdebaumarkt/template-python/actions/workflows/tests.yml)
[![pre-commit](https://github.com/foerdebaumarkt/template-python/actions/workflows/pre-commit.yml/badge.svg?branch=main)](https://github.com/foerdebaumarkt/template-python/actions/workflows/pre-commit.yml)
[![gitleaks](https://github.com/foerdebaumarkt/template-python/actions/workflows/gitleaks.yml/badge.svg?branch=main)](https://github.com/foerdebaumarkt/template-python/actions/workflows/gitleaks.yml)

Editor-agnostic Python project template.

Organization: Förde Baumarkt

## Features

- Editor-agnostic policy (see docs/editor-agnostic.md)
- Makefile with common tasks
- Pre-commit hooks with organization-wide baseline
- Ruff, mypy, pytest configured
- Dead-code gate (vulture), with tests outside the scanned paths
- Secrets scanning with gitleaks
- Guardrail that fails the build on committed editor files

Branding: see org guideline [foerdebaumarkt/.github/docs/brand-naming.md](https://github.com/foerdebaumarkt/.github/blob/main/docs/brand-naming.md)

## Getting started

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Optional: Set up pre-commit hooks for local development
pip install pre-commit
pre-commit install
```

## Docs

- docs/editor-agnostic.md
- docs/ci-cd.md
- CONTRIBUTING.md
