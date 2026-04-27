# Diagnostic scripts

All scripts are read-only. They print labelled output to stdout. If any
script needs to write somewhere transient (a temp dir, `/tmp`), it
prints the path it wrote to and cleans up at the end.

Run them in numerical order:

```bash
for s in scripts/0[1-9]*.sh scripts/1[0-9]*.sh; do
  echo
  echo "============================================================"
  echo "  $s"
  echo "============================================================"
  bash "$s" 2>&1 || echo "[script $s exited $?]"
done > diagnostic_run_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1
```

Or run individually and copy/paste relevant sections into the report.
