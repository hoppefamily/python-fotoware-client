# CI/CD

Three workflows live under `.github/workflows/`, and every check below really
runs in one of them — a check that is only documented is not a check.

| Workflow | Runs | Covers |
| --- | --- | --- |
| `pre-commit.yml` | `pre-commit` over **all** files | hygiene hooks, ruff lint + format, mypy, vulture, gitleaks, the editor guardrail |
| `tests.yml` | `pytest` | the test suite |
| `gitleaks.yml` | gitleaks over the history | secrets that a commit-time scan would miss |

Because `pre-commit.yml` runs with `--all-files`, the hooks judge the whole
repository, not just what a pull request touched. A check added here therefore
speaks about code that was already in the tree.

**Editor guardrail**: `.gitignore` keeps `.vscode/` and `.idea/` out, and the
`no-editor-files` hook fails the build if one is committed anyway — see
[editor-agnostic.md](editor-agnostic.md).

**Dead code**: `vulture` reports what nothing calls. `tests/` is deliberately
not among the scanned paths in `[tool.vulture]`, so a function whose only
caller is its own test counts as uncalled. See `make deadcode`.

## Pre-commit Setup

The repository includes a comprehensive pre-commit configuration with:

### Hygiene Hooks

- Trailing whitespace removal
- End-of-file fixing
- Merge conflict detection
- YAML/JSON/TOML validation
- Large file detection

### Security

- Branch protection (prevents direct commits to main)
- Secrets scanning with gitleaks

### Policy

- No committed editor files (`.vscode/`, `.idea/`)

### Python Quality

- Ruff linting and formatting
- MyPy type checking
- Vulture dead-code gate

### Local Development

To use pre-commit hooks locally:

```bash
# Install pre-commit (if not already installed)
pip install pre-commit

# Install the hooks
pre-commit install

# Run hooks on all files (optional)
pre-commit run --all-files
```

After installation, hooks will run automatically on each commit. You can bypass hooks temporarily with `git commit --no-verify` if needed.
