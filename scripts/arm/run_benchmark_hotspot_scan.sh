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

OUT_DIR="$OUT_ROOT/benchmark_hotspot_scan_${RUN_ID}"
mkdir -p "$OUT_DIR"

cd "$WORKDIR"

for bench in nbody richards fannkuch spectral_norm; do
  echo ">> hotspot scan: $bench"
  "$PY" scripts/arm/benchmark_hotspot_scan.py \
    --bench "$bench" \
    --top "$TOP" \
    --output "$OUT_DIR/${bench}.json" \
    >"$OUT_DIR/${bench}.stdout" \
    2>"$OUT_DIR/${bench}.stderr"
done

python3 - <<'PY' "$OUT_DIR" "$RUN_ID"
import json
import pathlib
import sys

out_dir = pathlib.Path(sys.argv[1])
run_id = sys.argv[2]
benchmarks = {}
global_suggestions = []
for path in sorted(out_dir.glob("*.json")):
    if path.name == "summary.json":
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    bench = data["benchmark"]
    benchmarks[bench] = {
        "benchmark_compiled_functions": data["benchmark_compiled_functions"],
        "top_hir_ops": data["top_hir_ops"][:8],
        "top_pattern_counts": data["top_pattern_counts"][:8],
        "top_functions": [
            {
                "qualname": fn["qualname"],
                "compiled_size": fn["compiled_size"],
                "top_hir_ops": fn["top_hir_ops"][:6],
                "pattern_counts": fn.get("pattern_counts", {}),
            }
            for fn in data["top_functions"][:4]
        ],
        "suggestions": data["suggestions"],
    }
    global_suggestions.extend(data["suggestions"])

summary = {
    "run_id": run_id,
    "out_dir": str(out_dir),
    "benchmarks": benchmarks,
    "all_suggestions": global_suggestions,
}

(out_dir / "summary.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, ensure_ascii=False))
PY

echo "summary_json=$OUT_DIR/summary.json"
