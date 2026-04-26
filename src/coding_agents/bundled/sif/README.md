# Building `coding_agent_hpc.sif`

Apptainer SIF for the four MVP coding agents (Claude Code, Codex CLI, OpenCode, Pi).
Recipe: [`bundled/coding_agent_hpc.def`](../coding_agent_hpc.def).
The lab admin runs the build once, copies the SIF to the HPC share, and atomic-swaps `current.sif`.

---

## Prerequisites

- **Docker Desktop** running (whale icon in the menu bar shows "Docker Desktop is running").
- **~10 GB free disk** in the Docker VM (Settings → Resources → Disk image size).
- **`bundled/sif/package-lock.json`** committed in the repo. Regenerate only when bumping pinned agent versions:
  ```bash
  docker run --rm --platform linux/amd64 -v "$PWD/bundled/sif:/work" -w /work \
    node:20 npm install --package-lock-only --omit=dev
  ```
  *Generates a deterministic dependency tree so SIF rebuilds are reproducible.*

---

## Build (Mac, Linux, WSL)

> **Apple Silicon users:** the `--platform linux/amd64` flag is **required** — the HPC is x86. Without it you'd build an ARM SIF that won't execute on the cluster. Adds ~2× build time via emulation.

### 1. Pull the Apptainer build image
```bash
docker pull --platform linux/amd64 ghcr.io/apptainer/apptainer:1.4.5
```
*One-time fetch of the official Apptainer 1.4 image (~150 MB). Used only as the build tool — not what ends up in the SIF.*

### 2. Build the SIF
```bash
cd <repo-root>
docker run --rm --privileged --platform linux/amd64 \
  -v "$PWD:/work" -w /work \
  ghcr.io/apptainer/apptainer:1.4.5 \
  apptainer build coding_agent_hpc.sif bundled/coding_agent_hpc.def
```
*Reads `bundled/coding_agent_hpc.def`, executes `%post` (apt + Node 20 + gitleaks + `npm ci`), bakes versions, writes `coding_agent_hpc.sif` (~1.5–2 GB). 10–15 min on Apple Silicon, 5–8 min on Intel/Linux.*

### 3. Verify labels (sub-second sanity check)
```bash
docker run --rm --platform linux/amd64 \
  -v "$PWD:/work" -w /work \
  ghcr.io/apptainer/apptainer:1.4.5 \
  apptainer inspect --json coding_agent_hpc.sif
```
*Reads the `%labels` block via the SIF header — confirms the build wrote `coding-agents.versions.{node,python,gitleaks,claude,codex,opencode,pi}`. This is what `coding-agents doctor` reads on the cluster.*

### 4. Smoke-test one agent
```bash
docker run --rm --privileged --platform linux/amd64 \
  -v "$PWD:/work" -w /work \
  ghcr.io/apptainer/apptainer:1.4.5 \
  apptainer exec coding_agent_hpc.sif claude --version
```
*Spawns the SIF and runs `claude --version` inside it. Exit 0 + a version string proves the npm install + binary symlink worked end-to-end.*

### 5. Compute SHA sidecar
```bash
shasum -a 256 coding_agent_hpc.sif | awk '{print $1}' > coding_agent_hpc.sif.sha256
```
*Used by the wrapper hot path (it reads `${SIF_REAL}.sha256` instead of hashing 1–2 GB per invocation — saves 2–8 sec per call).*

---

## Ship to the HPC

### 6. Upload the SIF + sidecar
```bash
DATED=coding_agent_hpc-$(date -u +%Y.%m).sif
scp coding_agent_hpc.sif        <user>@hpcs05.umcutrecht.nl:/hpc/compgen/users/shared/agent/${DATED}
scp coding_agent_hpc.sif.sha256 <user>@hpcs05.umcutrecht.nl:/hpc/compgen/users/shared/agent/${DATED}.sha256
```
*Date-stamps the SIF so previous builds remain available for rollback.*

### 7. Atomic-swap `current.sif`
```bash
ssh <user>@hpcs05.umcutrecht.nl \
  "ln -sfn /hpc/compgen/users/shared/agent/${DATED} \
           /hpc/compgen/users/shared/agent/current.sif"
```
*Symlink swap is atomic — already-running wrappers keep their open SIF fd; new invocations pick up the new SIF.*

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `exec: "build": executable file not found` | Missing `apptainer` keyword before `build` | Use the exact command in §2 |
| `Unable to locate package python3.12` | Old `From: ubuntu:22.04` | Confirm `.def` says `From: ubuntu:24.04` |
| `unsafe-perm is not a valid npm option` | Stale `npm config set unsafe-perm` | Confirm `.def` doesn't set `unsafe-perm` (npm 9+ removed it) |
| `useradd: UID 1000 is not unique` | Hardcoded `-u 1000` collides with Ubuntu's `ubuntu` user | Confirm `.def`'s `useradd` line has no `-u` |
| `no space left on device` | Docker VM disk full | Docker Desktop → Settings → Resources → bump disk to 60 GB+ |
| ARM SIF won't run on HPC | Forgot `--platform linux/amd64` | Re-build with the flag (mandatory on Apple Silicon) |
