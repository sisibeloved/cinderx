#!/usr/bin/env python3
"""Scan benchmark-specific AArch64 JIT hotspots and summarize inefficiency patterns."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable


MNEMONIC_RE = re.compile(r"^\s*[0-9a-fx]+:\s+[0-9a-f]+\s+([a-z0-9.]+)\b", re.IGNORECASE)
DISASM_LINE_RE = re.compile(
    r"^\s*[0-9a-fx]+:\s+[0-9a-f]+\s+([a-z0-9.]+)\s+(.*)$",
    re.IGNORECASE,
)
OBJ_SYMBOL_RE = re.compile(r"^\s*[0-9a-f]+\s+<(.+)>:\s*$")

NOT_NEGATIVE_SOURCE_OPS = (
    "DeleteAttr",
    "IsInstance",
    "Compare",
    "StoreAttr",
    "StoreAttrCached",
    "StoreSubscr",
)


def count_instruction_mix(disasm_text: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in disasm_text.splitlines():
        match = MNEMONIC_RE.match(line)
        if match is None:
            continue
        counts[match.group(1)] += 1
    return dict(counts)


def count_aarch64_patterns(disasm_text: str) -> dict[str, int]:
    lines: list[tuple[str, str]] = []
    for line in disasm_text.splitlines():
        match = DISASM_LINE_RE.match(line)
        if match is None:
            continue
        lines.append((match.group(1), match.group(2).strip()))

    guard_mnemonics = {"cbz", "cbnz", "tbz", "tbnz"}

    def is_cond_branch(mnemonic: str) -> bool:
        return mnemonic.startswith("b.") and mnemonic not in {"br", "blr"}

    def is_literal_load(mnemonic: str, operands: str) -> bool:
        return mnemonic == "ldr" and "[" not in operands

    counts: Counter[str] = Counter()
    for idx, (mnemonic, operands) in enumerate(lines):
        if mnemonic == "blr":
            counts["blr"] += 1
        if mnemonic == "bl":
            counts["bl"] += 1
        if mnemonic == "movk":
            counts["movk"] += 1
        if mnemonic == "ret":
            counts["ret"] += 1
        if mnemonic == "cbz":
            counts["cbz"] += 1
        if mnemonic == "cbnz":
            counts["cbnz"] += 1
        if mnemonic == "tbz":
            counts["tbz"] += 1
        if mnemonic == "tbnz":
            counts["tbnz"] += 1
        if is_cond_branch(mnemonic):
            counts["b_cond"] += 1
        if is_literal_load(mnemonic, operands):
            counts["ldr_literal"] += 1

        if idx + 1 >= len(lines):
            continue
        next_mnemonic, next_operands = lines[idx + 1]
        if is_literal_load(mnemonic, operands) and next_mnemonic == "blr":
            reg = operands.split(",", 1)[0].strip()
            if next_operands.strip() == reg:
                counts["ldr_literal_blr_pair"] += 1
        if is_literal_load(mnemonic, operands) and next_mnemonic == "br":
            reg = operands.split(",", 1)[0].strip()
            if next_operands.strip() == reg:
                counts["ldr_literal_br_pair"] += 1
        if mnemonic in {"bl", "blr"} and (
            next_mnemonic in guard_mnemonics or is_cond_branch(next_mnemonic)
        ):
            counts["post_call_branch_check"] += 1
        if (
            mnemonic in {"bl", "blr"}
            and next_mnemonic == "tbz"
            and next_operands.startswith("w0, #31")
        ):
            counts["post_call_tbz_w0_signbit"] += 1
        if mnemonic == "adr" and next_mnemonic == "bl":
            counts["adr_bl_pair"] += 1

        if idx + 2 < len(lines):
            next2_mnemonic, next2_operands = lines[idx + 2]
            if (
                (mnemonic in guard_mnemonics or is_cond_branch(mnemonic))
                and is_literal_load(next_mnemonic, next_operands)
                and next2_mnemonic == "blr"
            ):
                reg = next_operands.split(",", 1)[0].strip()
                if next2_operands.strip() == reg:
                    counts["guard_then_literal_blr"] += 1

        if mnemonic in {"bl", "blr"}:
            window = lines[max(0, idx - 4) : idx]
            movk_in_window = sum(1 for win_mnemonic, _ in window if win_mnemonic == "movk")
            if movk_in_window >= 2:
                counts["movk_heavy_call_window"] += 1

    return dict(counts)


def normalize_objdump_symbol_name(symbol: str) -> str:
    name = symbol.strip()
    if ":" in name:
        name = name.split(":")[-1]
    return name.strip(">")


def split_objdump_functions(disasm_text: str) -> list[dict[str, str]]:
    functions: list[dict[str, str]] = []
    current_symbol: str | None = None
    current_lines: list[str] = []

    for line in disasm_text.splitlines():
        match = OBJ_SYMBOL_RE.match(line)
        if match is not None:
            if current_symbol is not None:
                functions.append(
                    {
                        "symbol": current_symbol,
                        "normalized_symbol": normalize_objdump_symbol_name(current_symbol),
                        "disasm": "\n".join(current_lines),
                    }
                )
            current_symbol = match.group(1)
            current_lines = []
            continue
        if current_symbol is not None:
            current_lines.append(line)

    if current_symbol is not None:
        functions.append(
            {
                "symbol": current_symbol,
                "normalized_symbol": normalize_objdump_symbol_name(current_symbol),
                "disasm": "\n".join(current_lines),
            }
        )
    return functions


def parse_disasm_lines(disasm_text: str) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for raw in disasm_text.splitlines():
        match = DISASM_LINE_RE.match(raw)
        if match is None:
            continue
        parsed.append(
            {
                "mnemonic": match.group(1),
                "operands": match.group(2).strip(),
                "line": raw.rstrip(),
            }
        )
    return parsed


def match_objdump_function(
    qualname: str,
    filename: str,
    objdump_functions: list[dict[str, str]],
) -> dict[str, str] | None:
    normalized_qualname = qualname.strip()
    code_filename = filename.replace("\\", "/")
    candidates = [
        fn
        for fn in objdump_functions
        if fn["normalized_symbol"] == normalized_qualname
    ]
    if candidates:
        return candidates[0]

    short_qualname = normalized_qualname.split(".")[-1]
    for fn in objdump_functions:
        norm = fn["normalized_symbol"]
        if norm == short_qualname or norm.endswith("." + normalized_qualname):
            return fn
        if code_filename.endswith("fannkuch_canonical.py") and norm == normalized_qualname:
            return fn
    return None


def enrich_functions_with_objdump(
    functions: list[dict[str, Any]],
    whole_disasm: str,
) -> None:
    objdump_functions = split_objdump_functions(whole_disasm)
    for info in functions:
        match = match_objdump_function(
            info["qualname"],
            info.get("filename", ""),
            objdump_functions,
        )
        if match is None:
            continue
        disasm = match["disasm"]
        info["objdump_symbol"] = match["symbol"]
        info["objdump_instruction_mix"] = count_instruction_mix(disasm)
        info["objdump_pattern_counts"] = count_aarch64_patterns(disasm)
        info["objdump_interesting_windows"] = extract_interesting_windows(disasm)
        excerpt_lines = [line for line in disasm.splitlines() if line.strip()][:24]
        info["objdump_excerpt"] = "\n".join(excerpt_lines)


def extract_interesting_windows(disasm_text: str, limit: int = 8) -> list[dict[str, Any]]:
    lines = parse_disasm_lines(disasm_text)
    windows_raw: list[dict[str, Any]] = []

    body_start_idx = 0
    for idx, entry in enumerate(lines):
        if entry["mnemonic"] == "sub" and entry["operands"].startswith("sp, sp"):
            body_start_idx = idx
            break

    def add_window(kind: str, start: int, end: int) -> None:
        snippet_start = max(0, start)
        snippet_end = min(len(lines), end)
        snippet = "\n".join(line["line"] for line in lines[snippet_start:snippet_end])
        if not snippet:
            return
        phase = "body" if snippet_start >= body_start_idx else "entry"
        windows_raw.append(
            {
                "kind": kind,
                "phase": phase,
                "start_index": snippet_start,
                "snippet": snippet,
            }
        )

    for idx, entry in enumerate(lines):
        mnemonic = entry["mnemonic"]
        operands = entry["operands"]

        if idx + 1 < len(lines):
            nxt = lines[idx + 1]
            if mnemonic == "ldr" and "[" not in operands and nxt["mnemonic"] == "blr":
                reg = operands.split(",", 1)[0].strip()
                if nxt["operands"].strip() == reg:
                    add_window("ldr_literal_blr_pair", idx, idx + 2)
            if mnemonic == "ldr" and "[" not in operands and nxt["mnemonic"] == "br":
                reg = operands.split(",", 1)[0].strip()
                if nxt["operands"].strip() == reg:
                    add_window("ldr_literal_br_pair", idx, idx + 2)
            if mnemonic in {"bl", "blr"} and (
                nxt["mnemonic"] in {"cbz", "cbnz", "tbz", "tbnz"}
                or (nxt["mnemonic"].startswith("b.") and nxt["mnemonic"] not in {"br", "blr"})
            ):
                add_window("post_call_branch_check", idx, idx + 2)

        if mnemonic in {"bl", "blr"}:
            window_start = max(0, idx - 4)
            movk_in_window = sum(
                1 for line in lines[window_start:idx] if line["mnemonic"] == "movk"
            )
            if movk_in_window >= 2:
                add_window("movk_heavy_call_window", window_start, idx + 1)

    windows_raw.sort(
        key=lambda item: (0 if item["phase"] == "body" else 1, item["start_index"])
    )
    windows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in windows_raw:
        key = (item["kind"], item["snippet"])
        if key in seen:
            continue
        seen.add(key)
        windows.append({"kind": item["kind"], "phase": item["phase"], "snippet": item["snippet"]})
        if len(windows) >= limit:
            break
    return windows


def aggregate_hir_counts(functions: list[dict[str, Any]]) -> dict[str, int]:
    total: Counter[str] = Counter()
    for func in functions:
        total.update(func.get("hir_counts") or {})
    return dict(total)


def top_items(mapping: dict[str, int], limit: int = 10) -> list[list[Any]]:
    items = sorted(mapping.items(), key=lambda item: (-item[1], item[0]))
    return [[key, value] for key, value in items[:limit]]


def filter_nonzero_items(mapping: dict[str, int], keys: tuple[str, ...]) -> dict[str, int]:
    return {key: int(mapping.get(key, 0)) for key in keys if int(mapping.get(key, 0)) > 0}


def suggest_optimization_points(
    bench: str,
    instruction_mix: dict[str, int],
    pattern_counts: dict[str, int],
    hir_totals: dict[str, int],
) -> list[str]:
    suggestions: list[str] = []

    if pattern_counts.get("ldr_literal_blr_pair", 0) >= 8:
        suggestions.append(
            f"{bench}: helper-heavy hot path still spends significant code on literal-pool indirect calls; look for more direct-call or shared-stub opportunities."
        )
    if pattern_counts.get("movk_heavy_call_window", 0) >= 6:
        suggestions.append(
            f"{bench}: many calls are preceded by movk-heavy address materialization; inspect whether helper targets can be reached through literal loads, shared stubs, or shorter immediate sequences."
        )
    if pattern_counts.get("post_call_branch_check", 0) >= 8:
        suggestions.append(
            f"{bench}: many calls are immediately followed by branch checks; this suggests helper/error-check scaffolding is amplifying ARM front-end pressure."
        )
    if hir_totals.get("LoadAttrCached", 0) + hir_totals.get("LoadModuleAttrCached", 0) >= 4:
        suggestions.append(
            f"{bench}: attribute-cache traffic remains prominent; inspect typed or shared fast paths around attr/module-attr helpers."
        )
    if hir_totals.get("Decref", 0) >= 4 and instruction_mix.get("movk", 0) >= 12:
        suggestions.append(
            f"{bench}: refcount/deopt scaffolding still materializes many constants; look for cheaper helper target reuse or refcount fast-path lowering."
        )
    if hir_totals.get("VectorCall", 0) + hir_totals.get("CallMethod", 0) + hir_totals.get("Call", 0) >= 4:
        suggestions.append(
            f"{bench}: Python call overhead is still visible in final HIR; inspect whether stable call chains can be collapsed into cheaper call forms."
        )
    if bench == "spectral_norm" and hir_totals.get("VectorCall", 0) >= 2:
        suggestions.append(
            "spectral_norm: repeated helper-level function calls inside matrix kernels are a likely target; investigate whether local pure-Python helpers can specialize or inline more aggressively."
        )
    if bench == "nbody" and hir_totals.get("LoadAttrCached", 0) >= 4:
        suggestions.append(
            "nbody: inner-loop object attribute loads remain a likely bottleneck; prioritize attr fast-path work before arithmetic tuning."
        )
    if bench == "richards" and (
        pattern_counts.get("b_cond", 0)
        + pattern_counts.get("cbz", 0)
        + pattern_counts.get("cbnz", 0)
        >= 16
    ):
        suggestions.append(
            "richards: branch-dense control flow still dominates; favor optimizations that reduce helper calls and queue-manipulation overhead instead of arithmetic tuning."
        )
    if bench == "fannkuch" and hir_totals.get("BinarySubscr", 0) + hir_totals.get("StoreSubscr", 0) >= 2:
        suggestions.append(
            "fannkuch: list indexing and mutation still dominate; consider list/subscript fast paths before broader call-lowering changes."
        )

    if not suggestions:
        suggestions.append(
            f"{bench}: no single dominant pattern crossed the current heuristic thresholds; inspect the largest compiled functions and aggregate instruction mix manually."
        )
    return suggestions


def _flush_all_stdio() -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        ctypes.CDLL(None).fflush(None)
    except Exception:
        pass


def capture_native_stdout(callback: Callable[[], None]) -> str:
    saved_fd = os.dup(1)
    try:
        with tempfile.TemporaryFile(mode="w+b") as tmp:
            _flush_all_stdio()
            os.dup2(tmp.fileno(), 1)
            try:
                callback()
                _flush_all_stdio()
            finally:
                os.dup2(saved_fd, 1)
            tmp.seek(0)
            return tmp.read().decode("utf-8", errors="replace")
    finally:
        os.close(saved_fd)


def load_module_from_repo(name: str, relative_path: str) -> Any:
    path = Path.cwd() / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_nbody() -> tuple[bool, str]:
    module = load_module_from_repo("bench_nbody", "cinderx/benchmarks/nbody.py")

    return module.NBody().run(1), "cinderx/benchmarks/nbody.py"


def _run_richards() -> tuple[bool, str]:
    module = load_module_from_repo("bench_richards", "cinderx/benchmarks/richards.py")

    return module.Richards().run(1), "cinderx/benchmarks/richards.py"


def _run_spectral_norm() -> tuple[bool, str]:
    module = load_module_from_repo(
        "bench_spectral_norm",
        "cinderx/benchmarks/spectral_norm.py",
    )

    return module.SpectralNorm().run(1), "cinderx/benchmarks/spectral_norm.py"


def _run_fannkuch() -> tuple[bool, str]:
    import cinderx.jit as jit

    ns: dict[str, Any] = {}
    source = """
def fannkuch(n):
    perm = list(range(n))
    perm1 = list(range(n))
    count = list(range(1, n + 1))
    max_flips = 0
    r = n
    while True:
        while r != 1:
            count[r - 1] = r
            r -= 1
        if perm1[0] != 0 and perm1[-1] != n - 1:
            perm[:] = perm1
            flips = 0
            k = perm[0]
            while k:
                perm[: k + 1] = perm[k::-1]
                flips += 1
                k = perm[0]
            if flips > max_flips:
                max_flips = flips
        while True:
            if r == n:
                return max_flips
            perm0 = perm1[0]
            i = 0
            while i < r:
                perm1[i] = perm1[i + 1]
                i += 1
            perm1[r] = perm0
            count[r] -= 1
            if count[r] > 0:
                break
            r += 1

def run():
    return fannkuch(10) == 38
    """
    code = compile(source, "/tmp/fannkuch_canonical.py", "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["fannkuch"])
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), "fannkuch_canonical.py"


BENCH_RUNNERS: dict[str, Callable[[], tuple[bool, str]]] = {
    "nbody": _run_nbody,
    "richards": _run_richards,
    "fannkuch": _run_fannkuch,
    "spectral_norm": _run_spectral_norm,
}


def run_benchmark(bench: str) -> tuple[bool, str]:
    runner = BENCH_RUNNERS[bench]
    return runner()


def collect_function_info(
    func: Any,
    jit_mod: Any,
    cinderjit_mod: Any,
    include_disasm: bool,
) -> dict[str, Any]:
    hir_counts = jit_mod.get_function_hir_opcode_counts(func) or {}
    info: dict[str, Any] = {
        "qualname": getattr(func, "__qualname__", getattr(func, "__name__", "<unknown>")),
        "name": getattr(func, "__name__", "<unknown>"),
        "filename": getattr(getattr(func, "__code__", None), "co_filename", ""),
        "compiled_size": int(cinderjit_mod.get_compiled_size(func)),
        "stack_size": int(cinderjit_mod.get_compiled_stack_size(func))
        if hasattr(cinderjit_mod, "get_compiled_stack_size")
        else 0,
        "spill_stack_size": int(cinderjit_mod.get_compiled_spill_stack_size(func))
        if hasattr(cinderjit_mod, "get_compiled_spill_stack_size")
        else 0,
        "compilation_time_ns": int(jit_mod.get_function_compilation_time(func))
        if hasattr(jit_mod, "get_function_compilation_time")
        else 0,
        "hir_counts": hir_counts,
        "top_hir_ops": top_items(hir_counts, limit=8),
    }
    not_negative_sources = filter_nonzero_items(hir_counts, NOT_NEGATIVE_SOURCE_OPS)
    if not_negative_sources:
        info["likely_not_negative_hir_sources"] = top_items(not_negative_sources, limit=8)
        info["likely_not_negative_hir_total"] = int(sum(not_negative_sources.values()))
    if include_disasm and hasattr(cinderjit_mod, "disassemble"):
        disasm = capture_native_stdout(lambda: cinderjit_mod.disassemble(func))
        info["instruction_mix"] = count_instruction_mix(disasm)
        info["pattern_counts"] = count_aarch64_patterns(disasm)
    return info


def scan_benchmark(bench: str, top: int, include_disasm: bool) -> dict[str, Any]:
    import cinderx.jit as jit
    import cinderjit

    jit.enable()
    jit.compile_after_n_calls(1)

    ok, marker = run_benchmark(bench)
    if not ok:
        raise RuntimeError(f"{bench} benchmark returned failure")

    compiled_funcs = list(cinderjit.get_compiled_functions())
    benchmark_funcs = [
        func
        for func in compiled_funcs
        if marker in getattr(getattr(func, "__code__", None), "co_filename", "").replace("\\", "/")
    ]
    benchmark_funcs.sort(key=lambda func: int(cinderjit.get_compiled_size(func)), reverse=True)

    top_funcs = [
        collect_function_info(func, jit, cinderjit, include_disasm)
        for func in benchmark_funcs[:top]
    ]

    with tempfile.TemporaryDirectory() as td:
        elf_path = Path(td) / f"{bench}.elf"
        cinderjit.dump_elf(str(elf_path))
        objdump = subprocess.run(
            ["objdump", "-d", str(elf_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        whole_disasm = objdump.stdout

    instruction_mix = count_instruction_mix(whole_disasm)
    pattern_counts = count_aarch64_patterns(whole_disasm)
    hir_totals = aggregate_hir_counts(top_funcs)
    enrich_functions_with_objdump(top_funcs, whole_disasm)

    return {
        "benchmark": bench,
        "marker": marker,
        "compiled_functions_total": len(compiled_funcs),
        "benchmark_compiled_functions": len(benchmark_funcs),
        "instruction_mix": instruction_mix,
        "pattern_counts": pattern_counts,
        "top_instruction_mix": top_items(instruction_mix, limit=12),
        "top_pattern_counts": top_items(pattern_counts, limit=12),
        "top_functions": top_funcs,
        "aggregate_hir_counts": hir_totals,
        "top_hir_ops": top_items(hir_totals, limit=12),
        "suggestions": suggest_optimization_points(
            bench,
            instruction_mix,
            pattern_counts,
            hir_totals,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bench",
        choices=sorted(BENCH_RUNNERS),
        required=True,
        help="Benchmark to scan",
    )
    parser.add_argument("--output", required=True, help="Path to JSON output")
    parser.add_argument("--top", type=int, default=6, help="Top compiled functions to include")
    parser.add_argument(
        "--no-function-disasm",
        action="store_true",
        help="Skip per-function disassembly capture",
    )
    args = parser.parse_args()

    result = scan_benchmark(args.bench, args.top, include_disasm=not args.no_function_disasm)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
