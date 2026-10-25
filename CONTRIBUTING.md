# Contributing

- **One call, one request.** The client does what the FotoWare API does and
  nothing more: no hidden batching, repeated queries or retries beyond the
  configured policy. Knowledge of a particular archive (its fields, filters or
  folders) belongs in the applications, not here.
- **Checks.** `make lint type test deadcode`; CI runs pre-commit, pytest and
  gitleaks on every pull request. Install the hooks with `pre-commit install`.
- **Changelog.** A change a user of the package would notice gets an entry
  under `[Unreleased]` in CHANGELOG.md, in the same pull request; the
  `changelog` check asks for one whenever `src/` changes. A change nobody
  would notice takes the label `skip-changelog` instead.
- **Releasing.** One pull request bumps the version in `pyproject.toml` and
  `__version__` and moves the `[Unreleased]` entries under the new version
  and its date. After the merge, the release takes its notes from that
  section:

  ```sh
  gh release create vX.Y.Z --notes "$(python scripts/changelog.py X.Y.Z)"
  ```

  The publish workflow refuses a tag whose version disagrees with the
  package or has no changelog section.
- **Editor-agnostic:** no editor-specific files (see docs/editor-agnostic.md).
- **No secrets** in code, tests or logs.
