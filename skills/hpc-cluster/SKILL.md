---
name: hpc-cluster
description: >
  Reference skill for the UMC Utrecht HPC cluster (SLURM-based). Use this skill whenever the user
  mentions HPC, SLURM, sbatch, srun, salloc, compute cluster, GPU jobs, job submission, job queues,
  partitions, cluster nodes, scratch space, tmpspace, or anything related to running workloads on
  the UMC Utrecht high-performance computing infrastructure. Also trigger when the user asks about
  SSH access to hpcs05/hpcs06, conda on the cluster, module load, Open OnDemand, data transfers
  to/from the cluster, iRODS, Cromwell/WDL pipelines, or cluster resource limits. If the user
  mentions "the cluster", "our cluster", "HPC", "compute nodes", "GPU nodes", or refers to SLURM
  commands, always consult this skill. Trigger even for casual mentions like "run this on the cluster"
  or "submit a job".
---

# UMC Utrecht HPC Cluster Skill

This skill contains the complete documentation for the UMC Utrecht HPC cluster. Use it to answer
any question about cluster usage, job submission, resource requests, GPU access, software setup,
data management, and connectivity.

## How to Use This Skill

1. **Match the user's query** to a section using the Query Routing table below.
2. **For quick answers**: use the information in this file (templates, GPU table, guidelines).
3. **For detailed/edge-case questions**: read the full reference document at
   `references/HPC_Cluster_Documentation_Complete.md` — use the line numbers below to jump
   to the relevant section.

---

## Query Routing

| User asks about... | Section in reference doc | Lines |
|---|---|---|
| How to connect / SSH / login | Login Overview + OS-specific | 865–1300 |
| Login from Linux or Mac | Login from Linux/Mac | 899–1067 |
| Login from Windows / PuTTY / MobaXterm | Login from Windows | 1068–1300 |
| Submitting jobs / sbatch / srun / salloc | SLURM Guide | 1408–1675 |
| GPU jobs / GPU types / GPU partition | SLURM Guide (GPU) + GPU Nodes | 1525–1540, 2439–2522 |
| Resource limits / group limits | Resource Limits in SLURM | 1560–1662 |
| Scratch / tmpspace / $TMPDIR | Local scratch disk space | 1515–1524 |
| Installing software / conda / modules | Software & Environments | 1679–2170 |
| Conda setup / environments | Conda | 1897–1945 |
| Module load / Lmod | Lmod Modules | 1946–2121 |
| Cluster architecture / node specs | Setup Overview | 2172–2440 |
| CPU node specs | CPU Nodes | 2375–2438 |
| GPU node specs | GPU Nodes | 2439–2522 |
| All compute nodes inventory | All Compute Nodes | 2525–2606 |
| File transfers / scp / rsync | Transferring Data | 2664–2754 |
| iRODS | iRODS | 2755–2781 |
| Open OnDemand / web interface | Open OnDemand | 2782–2807 |
| RStudio on cluster | RStudio Server | 2808+ |
| Cromwell / WDL pipelines | Cromwell | (check reference) |
| Support / contact | Support & Contact | 3122–3205 |

---

## Project Directory Structure (Mandatory)

```
/hpc/compgen/projects/<project>/
    <subproject>/
        raw/                    # Downloaded/sequencing data
        analysis/
            <username>/         # Your analysis output, scripts, results
    raw/                        # Optional: shared raw data across subprojects
```

### Quick Reference

| Resource | Path/Command |
|----------|--------------|
| Group directory | `/hpc/compgen/` |
| Projects | `/hpc/compgen/projects/<project>/` |
| User space | `/hpc/compgen/users/<username>/` |
| Home (5GB limit) | `~/` — **DO NOT WRITE HERE unless explicitly confirmed with user** |
| SLURM account | `--account=compgen` |
| Get username | `whoami` |

### Directory Rules
- `<username>` = HPC login name (`whoami`)
- **No spaces or dots** in directory names
- **Lowercase only** for project/subproject names
- Use underscores: `my_project` (not `my-project` or `My Project`)
- If no subproject needed, reuse project name: `myproject/myproject/`
- New project? Copy structure from `/hpc/compgen/projects/my_project/`

### What Goes Where

| Data Type | Location |
|-----------|----------|
| Downloaded files, sequencing data | `raw/` |
| Analysis output, results | `analysis/<username>/` |
| Scripts, code | `analysis/<username>/` or `~/` |
| Conda, tools, personal tests | `/hpc/compgen/users/<username>/` |

---

## Node Types

| Type | Hostname | Use |
|------|----------|-----|
| Submit | hpcs05, hpcs06 | Job submission, light commands, editing |
| Transfer | hpct04, hpct05 | Data transfers, Yoda access |
| Compute | N#### | Heavy workloads (via SLURM only) |

---

## SLURM Defaults

- Partition: `cpu` (default) or `gpu`
- Default runtime: **10 minutes**
- Default memory: **10 GB**
- Default scratch: **1 GB** in `$TMPDIR` (`/scratch/$SLURM_JOB_ID`)
- 1 SLURM "cpu" = 1 hyperthread (2 hyperthreads = 1 physical core)
- Requesting odd CPUs rounds up to even

---

## SLURM Quick Commands

```bash
# Interactive session
srun -J taskname --time=01:00:00 --mem=10G bash

# Submit batch job
sbatch script.sh

# GPU job
sbatch --partition=gpu --gpus-per-node=1 script.sh

# Array job
sbatch --array=1-100 script.sh

# Check your jobs
squeue -u $USER

# Job efficiency (after completion)
seff <jobid>

# Cancel job
scancel <jobid>

# Delay job start
scontrol update StartTime=18:00 JobId=<jobid>

# Lower priority / off-hours
sbatch --nice=1000 script.sh
sbatch --begin=18:00 script.sh

# Check group resource limits
showuserlimits
```

---

## Available GPU Hardware

| SLURM device name | GPU Card | VRAM | Nodes | GPUs/node |
|---|---|---|---|---|
| `quadro_rtx_6000` | Quadro RTX 6000 | 24 GB | n0096, n0098–n0102 | 4 |
| `tesla_p100-pcie-16gb` | Tesla P100 | 16 GB | n0097 | 2 |
| `tesla_v100-pcie-16gb` | Tesla V100 | 16 GB | n0108 | 4 |
| `2g.20gb` | A100 80GB (MIG, 1/3 slice) | 20 GB | n0124–n0126, n0131–n0132 | 6 (3 slices × 2 physical) |
| `7g.79gb` | A100 80GB (full) | 79 GB | n0127–n0130, n0133 | 2 |

### GPU Request Syntax

```bash
# Any available GPU
srun -p gpu --gpus-per-node=1 --pty bash

# Specific GPU type
srun -p gpu --gpus-per-node=quadro_rtx_6000:1 --pty bash
srun -p gpu --gpus-per-node=tesla_v100-pcie-16gb:1 --pty bash
srun -p gpu --gpus-per-node=2g.20gb:1 --pty bash      # A100 MIG slice (20GB)
srun -p gpu --gpus-per-node=7g.79gb:1 --pty bash       # A100 full (79GB)

# sbatch equivalent
#SBATCH --partition=gpu
#SBATCH --gpus-per-node=quadro_rtx_6000:1
```

---

## sbatch Script Template (CPU)

```bash
#!/bin/bash
#SBATCH --job-name=myjob
#SBATCH --account=compgen
#SBATCH --time=01:00:00
#SBATCH --mem=10G
#SBATCH --cpus-per-task=1
#SBATCH --gres=tmpspace:10G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

# Your commands here
```

## sbatch Script Template (Array Job)

```bash
#!/bin/bash
#SBATCH --output=~/log/slurm_arrayJob_%A_%a.out
#SBATCH --error=~/log/slurm_arrayJob_%A_%a.err
#SBATCH --time=24:00:00
#SBATCH --array=1-15%3
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --gres=tmpspace:8G
#SBATCH --chdir /hpc/compgen/projects/your/project/stuff
#SBATCH --comment "Hello there!"
#SBATCH --begin 18:00
#SBATCH --nice=500

# %A = master job ID, %a = array task ID
# --array=1-15%3 means tasks 1–15, max 3 running simultaneously
# --begin 18:00 delays start until 6pm (be nice to daytime users)
# --nice=500 lowers scheduling priority

# Your commands here
# Access task ID via $SLURM_ARRAY_TASK_ID
```

## sbatch Script Template (GPU)

```bash
#!/bin/bash
#SBATCH --job-name=my_gpu_job
#SBATCH --account=compgen
#SBATCH --partition=gpu
#SBATCH --gpus-per-node=quadro_rtx_6000:1
#SBATCH --time=24:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=4
#SBATCH --gres=tmpspace:50G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

# ─── GPU options (pick ONE --gpus-per-node line) ───
# --gpus-per-node=1                          # Any available GPU
# --gpus-per-node=quadro_rtx_6000:1          # RTX 6000 (24GB VRAM)
# --gpus-per-node=tesla_p100-pcie-16gb:1     # Tesla P100 (16GB VRAM)
# --gpus-per-node=tesla_v100-pcie-16gb:1     # Tesla V100 (16GB VRAM)
# --gpus-per-node=2g.20gb:1                  # A100 MIG slice (20GB VRAM)
# --gpus-per-node=7g.79gb:1                  # A100 full (79GB VRAM)
# --gpus-per-node=quadro_rtx_6000:2          # Multiple GPUs (up to 4)

# Your GPU commands here
```

## Harmonia Experiment Template (GPU + Ollama/LLM)

For GPU jobs that run a local LLM server (Ollama) plus a Beaker experiment server,
see `references/sbatch_harmonia_gpu_template.sh`. This template includes:
- Dynamic port allocation to avoid conflicts
- Ollama auto-start via `exec_apptainer_harmonia.sh`
- Health-check polling loop with 15-min timeout
- Automatic cleanup on exit
- Run ID generation for linking logs to results

---

## Environment Management

```bash
# Use conda (NOT module load) for most software
conda activate myenv

# Or use uv for Python packages
uv pip install package
```

---

## Backup Strategy

| What | Where |
|------|-------|
| Code | GitHub (UMCUGenetics organization) |
| Raw data | Yoda (compressed, on receipt) |
| Results | Yoda (selective, what's needed) |

**Do NOT backup to Yoda:** code, scripts, tools, downloaded software.

---

## Best Practices

- Use `screen` or `tmux` on submit/transfer nodes
- Keep submit node work light (editing, job control)
- Heavy work → always a SLURM job
- Minimize small files; pack with `tar` when possible
- Use `--nice=1000` or `--begin=18:00` for non-urgent jobs
- Check efficiency after jobs complete: `seff <jobid>`
- Don't set tmpspace too small (minimum ~200M)

---

## Restrictions

- No root/sudo access
- No SSHFS
- No `module load` for most use cases (prefer conda)
- No files outside `raw/` or `analysis/<username>/`
- Home directory: **5GB limit** — do not write significant data here

---

## Support

- Email: hpcsupport@umcutrecht.nl (weekdays 9:00–17:00, best-effort evenings/weekends)
- Initial intake / new groups: Ies Nijman, Jeroen de Ridder
- HPC stats: http://hpcstats.op.umcutrecht.nl/

---

## For Detailed Information

Read the full reference document for comprehensive coverage:

```
view references/HPC_Cluster_Documentation_Complete.md
```

Use the line numbers from the Query Routing table above to jump to specific sections.
