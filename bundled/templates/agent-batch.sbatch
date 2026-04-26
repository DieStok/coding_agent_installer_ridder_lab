#!/bin/bash
# Canonical sbatch template for non-interactive agent runs on the UMC HPC.
# Edit the body below to put your `agent-<name>` invocation; do NOT edit the
# --export line unless you know exactly which env vars your conda/uv setup needs.
#
# Submit with:  sbatch agent-batch.sbatch
#
# See coding-agents project-init <path> for an auto-customised copy.

#SBATCH --account=compgen
#SBATCH --time=08:00:00
#SBATCH --mem=5G
#SBATCH --gres=tmpspace:5G
#SBATCH --cpus-per-task=2
#SBATCH --export=PATH,VIRTUAL_ENV,CONDA_PREFIX,CONDA_DEFAULT_ENV,LD_LIBRARY_PATH,HOME,USER,TERM,LANG,LC_ALL
#SBATCH --output=/hpc/compgen/users/%u/agent-logs/%x-%j.out
#SBATCH --job-name=claude_managed_de_ridder_lab
# Lab convention: <agent>_managed_de_ridder_lab — change the prefix to
# match the agent in the body below (codex_managed_de_ridder_lab,
# opencode_managed_de_ridder_lab, etc.). The agent-* wrapper auto-renames
# the job at runtime if you forgot to set the right name here.

# Activate your env BEFORE submitting this script (the --export above
# carries the activation into the SLURM job; --export=NONE would break
# the conda/uv carry-through expected by the agent-* wrapper).
#
# Example:
#   conda activate myproj
#   sbatch agent-batch.sbatch

set -euo pipefail
agent-claude -p "your prompt here"
