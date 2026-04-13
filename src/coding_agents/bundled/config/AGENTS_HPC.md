# Global Agent Instructions

> User-level instructions loaded by all coding agents in all projects.
> Project-specific AGENTS.md files take precedence over this file.

## Environment

- UMC Utrecht HPC cluster (SLURM, no sudo, NFS home directories)
- Python 3.12 available at /usr/bin/python3.12
- Node.js 18 available at /usr/bin/node
- Use `uv` for Python package management
- Use `srun` for interactive jobs, `sbatch` for batch jobs
- Always specify `--account=compgen` in SLURM directives

## File Placement Rules

- Project data goes in `/hpc/compgen/projects/<project>/`
- Your analysis outputs go in `<subproject>/analysis/$(whoami)/`
- Personal scratch goes in `/hpc/compgen/users/$(whoami)/`
- NEVER write to another user's directories
- NEVER store secrets, API keys, or credentials in project files

## Code Quality

- Python: follow ruff defaults, type-hint all function signatures
- Use docstrings for public functions
- Write tests for non-trivial logic
- Prefer `pathlib.Path` over string path manipulation

## Workflow Recommendation

For substantial work, use the compound-engineering workflow:
/ce:brainstorm → /ce:plan → /ce:work → /ce:review
