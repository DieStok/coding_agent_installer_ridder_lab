# Global Agent Instructions

> User-level instructions loaded by all coding agents in all projects.
> Project-specific AGENTS.md files take precedence over this file.

## Environment

- Local workstation (auto-detected: macOS/Linux)
- Python 3.12+ via system, brew, or pyenv
- Node.js via system, brew, or nvm
- Use `uv` for Python package management

## Code Quality

- Python: follow ruff defaults, type-hint all function signatures
- Use docstrings for public functions
- Write tests for non-trivial logic
- Prefer `pathlib.Path` over string path manipulation

## Workflow Recommendation

For substantial work, use the compound-engineering workflow:
/ce:brainstorm → /ce:plan → /ce:work → /ce:review
