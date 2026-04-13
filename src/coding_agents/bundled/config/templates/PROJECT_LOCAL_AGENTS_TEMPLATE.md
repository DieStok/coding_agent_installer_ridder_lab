# Project: {PROJECT_NAME}

> This file guides AI coding agents working in this repository.
> It is read by Claude Code, Codex CLI, OpenCode, Pi, Gemini CLI, Amp, and others.

## 🧠 Before You Start

AI agents are powerful tools, but **the thinking is the work**. Use agents to
augment your understanding, not replace it. If you find yourself accepting code
you don't fully understand, pause and work through it manually first.

The project is not the deliverable. The project is the vehicle. The deliverable
is the scientist — or engineer — that comes out the other end.

Read more: https://ergosphere.blog/posts/the-machines-are-fine/

## Recommended Workflow

For substantial work (new features, refactors, investigations), the
compound-engineering workflow produces the best results:

1. **`/ce:brainstorm`** — Explore the problem, produce a requirements doc in `docs/brainstorms/`
2. **`/ce:plan`** — Create a technical spec with acceptance criteria in `docs/plans/`
3. **`/ce:work`** — Implement with tests, referencing the plan
4. **`/ce:review`** — Adversarial review of the implementation

For small changes (typos, config tweaks, one-liner fixes), skip directly to implementation.

## Environment

- **Platform**: UMC Utrecht HPC cluster (SLURM-based)
- **Submit jobs**: Use `srun` for interactive, `sbatch` for batch
- **Project data**: `/hpc/compgen/projects/{PROJECT_NAME}/`
- **Your analysis output**: `<subproject>/analysis/{USERNAME}/`
- **No sudo** available — all tools are user-space installed
- **Python**: Use `uv` for package management where possible
- **Jobs**: Always specify `--account=compgen` in SLURM directives

## Code Conventions

- Language/framework: [fill in]
- Testing approach: [fill in]
- Style guide: [fill in — ruff is available for Python linting]

## Directory Structure

Follow the mandatory HPC project structure:

```
/hpc/compgen/projects/<project>/
    <subproject>/
        raw/               # Input/reference data (shared, read-carefully)
        analysis/
            <username>/    # YOUR analysis outputs go here
```

Do NOT write files directly into the project root or subproject root.
Do NOT write into another user's `analysis/<username>/` directory.

## Agent Configuration

Agent configs for this project are in `.claude/`, `.codex/`, `.pi/`, and `opencode.json`.
Global skills and hooks are managed by `coding-agents sync`.
Run `coding-agents doctor` to verify your setup.
