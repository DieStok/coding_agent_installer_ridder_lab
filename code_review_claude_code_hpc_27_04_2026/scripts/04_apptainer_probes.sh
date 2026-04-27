#!/usr/bin/env bash
# 04 — Apptainer-flag probes. These run apptainer-exec directly (NOT
# through our wrapper) to confirm the SIF behaves as expected under the
# flag combos our wrapper uses.
set -u

SIF=${SIF:-/hpc/compgen/users/shared/agent/current.sif}
if [ ! -r "$SIF" ]; then
  echo "[04] SIF not readable at $SIF — set SIF=/path/to/sif and re-run."
  exit 1
fi

echo "[04] HOME-mechanism probe (--env HOME=$HOME with --no-mount home)"
echo "----------------------------------------------------------------"
apptainer exec \
  --containall --no-mount home --writable-tmpfs \
  --env "HOME=$HOME" \
  "$SIF" \
  sh -c 'echo HOME=$HOME; id; ls -la $HOME 2>&1 | head -3' 2>&1 \
  || echo "[apptainer exited $?]"
echo

echo "[04] /tmp source probe (no --no-mount tmp; expect host /tmp visible)"
echo "----------------------------------------------------------------"
apptainer exec \
  --containall --no-mount home --writable-tmpfs \
  --env "HOME=$HOME" \
  "$SIF" \
  sh -c 'mkdir -p /tmp/probe-uid-$(id -u) && \
         touch /tmp/probe-uid-$(id -u)/foo && \
         stat -c "%a %u %g %n" /tmp /tmp/probe-uid-$(id -u) /tmp/probe-uid-$(id -u)/foo; \
         echo "---"; \
         mount | grep -E " on /tmp " | head -3' 2>&1 \
  || echo "[apptainer exited $?]"
echo

echo "[04] biome on PATH inside SIF (post-9b87b0b verification)"
echo "----------------------------------------------------------------"
apptainer exec --containall --no-mount home --writable-tmpfs "$SIF" \
  biome --version 2>&1 \
  || echo "[biome --version exited $?]"
echo

echo "[04] Pi defaults baked in (post-c3ab926 verification)"
echo "----------------------------------------------------------------"
apptainer exec --containall --no-mount home --writable-tmpfs "$SIF" \
  cat /opt/pi-default-settings.json 2>&1 \
  || echo "[cat /opt/pi-default-settings.json exited $?]"
echo

echo "[04] Cleanup probe artifacts"
rm -rf /tmp/probe-uid-$(id -u) 2>/dev/null
