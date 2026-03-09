#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${WORKDIR:-/root/work/cinderx-main}"
PY="${PYTHON:-/root/venv-cinderx314/bin/python}"
OUT_ROOT="${OUT_ROOT:-/root/work/arm-sync}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
TOP="${TOP:-6}"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: python not executable: $PY" >&2
  exit 1
fi

OUT_DIR="$OUT_ROOT/jit_microcases_scan_${RUN_ID}"
mkdir -p "$OUT_DIR"

cd "$WORKDIR"

"$PY" scripts/arm/jit_microcases_scan.py \
  --case all \
  --top "$TOP" \
  --output "$OUT_DIR/microcases.json" \
  >"$OUT_DIR/microcases.stdout" \
  2>"$OUT_DIR/microcases.stderr"

echo "microcases_json=$OUT_DIR/microcases.json"
