# SIF build inputs

Files in this directory are consumed by the `%files` block of
`bundled/coding_agent_hpc.def` and reproducibly installed into the SIF
via `npm ci --omit=dev`.

## Building the SIF

The `package-lock.json` must be **committed** before building. Generate
it on a Linux box (or in the same Docker container you'll build with)
to ensure platform-correct `optionalDependencies` are recorded:

```bash
cd bundled/sif/
docker run --rm -v "$PWD:/work" -w /work node:20 npm install --package-lock-only
git add package-lock.json && git commit -m "chore(sif): pin npm lockfile"
```

Then build the SIF (from the repo root, on a host with Apptainer or
Docker):

### Mac (via Apptainer-in-Docker, official image — recommended)

```bash
docker run --rm --privileged \
  -v "$PWD:/work" \
  ghcr.io/apptainer/apptainer:1.4.5 \
  build /work/coding_agent_hpc.sif /work/bundled/coding_agent_hpc.def
```

### Mac (via Lima — clean Apptainer host)

```bash
brew install lima
limactl start template://apptainer
limactl shell apptainer apptainer build coding_agent_hpc.sif /tmp/lima/bundled/coding_agent_hpc.def
```

### Linux (native Apptainer)

```bash
apptainer build coding_agent_hpc.sif bundled/coding_agent_hpc.def
```

Then upload to the lab share + atomic symlink swap:

```bash
scp coding_agent_hpc.sif <hpc>:/hpc/compgen/users/shared/agent/coding_agent_hpc-2026.04.sif
ssh <hpc> 'ln -sfn coding_agent_hpc-2026.04.sif /hpc/compgen/users/shared/agent/current.sif'
```

`coding-agents install` (or `coding-agents sync`) writes a
`current.sif.sha256` sidecar so the wrapper hot path skips per-invocation
hashing (see plan §4.2 perf-oracle finding).
