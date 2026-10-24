# Contributing

- **One call, one request.** The client does what the FotoWare API does and
  nothing more: no hidden batching, repeated queries or retries beyond the
  configured policy. Knowledge of a particular archive (its fields, filters or
  folders) belongs in the applications, not here.
- **Checks.** `make lint type test deadcode`; CI runs pre-commit, pytest and
  gitleaks on every pull request. Install the hooks with `pre-commit install`.
- **Editor-agnostic:** no editor-specific files (see docs/editor-agnostic.md).
- **No secrets** in code, tests or logs.
