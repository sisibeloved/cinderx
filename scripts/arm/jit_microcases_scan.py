#!/usr/bin/env python3
"""Scan benchmark-derived AArch64 JIT microcases and summarize inefficiency patterns."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import benchmark_hotspot_scan as hotspot


MicrocaseRunner = Callable[[], tuple[bool, str, list[str]]]
STORE_STATUS_SOURCE_OPS = (
    "StoreAttr",
    "StoreAttrCached",
    "StoreSubscr",
    "DeleteAttr",
)


def _run_nbody_attr_update() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/nbody_attr_update_case.py"
    ns: dict[str, Any] = {}
    source = """
class Body:
    def __init__(self, x, y, z, vx, vy, vz, mass):
        self.x = x
        self.y = y
        self.z = z
        self.vx = vx
        self.vy = vy
        self.vz = vz
        self.mass = mass


def advance_step(bodies, dt, n_bodies):
    for i in range(n_bodies):
        bi = bodies[i]
        bi_x = bi.x
        bi_y = bi.y
        bi_z = bi.z
        bi_mass = bi.mass
        bi_vx = bi.vx
        bi_vy = bi.vy
        bi_vz = bi.vz
        for j in range(i + 1, n_bodies):
            bj = bodies[j]
            dx = bi_x - bj.x
            dy = bi_y - bj.y
            dz = bi_z - bj.z
            dist_sq = dx * dx + dy * dy + dz * dz
            dist = dist_sq ** 0.5
            mag = dt / (dist_sq * dist)
            bj_mass = bj.mass
            bi_vx -= dx * bj_mass * mag
            bi_vy -= dy * bj_mass * mag
            bi_vz -= dz * bj_mass * mag
            bj.vx += dx * bi_mass * mag
            bj.vy += dy * bi_mass * mag
            bj.vz += dz * bi_mass * mag
        bi.vx = bi_vx
        bi.vy = bi_vy
        bi.vz = bi_vz
    return bodies[0].vx


def run():
    bodies = [
        Body(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        Body(4.8, -1.1, -0.1, 1.6, 7.6, -0.06, 0.95),
        Body(8.3, 4.1, -0.4, -2.7, 4.9, 2.3, 0.28),
    ]
    out = 0.0
    for _ in range(120):
        out += advance_step(bodies, 0.01, len(bodies))
    return out != 0.0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["advance_step"])
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, ["advance_step", "run"]


def _run_store_init_inline_values() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/store_init_inline_values_case.py"
    ns: dict[str, Any] = {}
    source = """
class Box:
    def __init__(self):
        pass


def init_attrs(box, a, b, c, d, e, f):
    box.a = a
    box.b = b
    box.c = c
    box.d = d
    box.e = e
    box.f = f
    return f


def run():
    total = 0
    for i in range(400):
        total += init_attrs(Box(), i, i + 1, i + 2, i + 3, i + 4, i + 5)
    return total > 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["init_attrs"])
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, ["init_attrs", "run"]


def _run_store_overwrite_inline_values() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/store_overwrite_inline_values_case.py"
    ns: dict[str, Any] = {}
    source = """
class Box:
    def __init__(self):
        self.a = 0
        self.b = 0
        self.c = 0
        self.d = 0


def overwrite_attrs(box, base):
    box.a = base
    box.b = base + 1
    box.c = box.a + box.b
    box.d = box.c + 1
    return box.d


def run():
    box = Box()
    total = 0
    for i in range(800):
        total += overwrite_attrs(box, i)
    return total > 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["overwrite_attrs"])
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, ["overwrite_attrs", "run"]


def _run_store_overwrite_existing() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/store_overwrite_existing_case.py"
    ns: dict[str, Any] = {}
    source = """
class Box:
    def __init__(self):
        self.a = 0
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.f = 0


def overwrite_existing(box, a, b, c, d, e, f):
    box.a = a
    box.b = b
    box.c = c
    box.d = d
    box.e = e
    box.f = f
    return f


def run():
    box = Box()
    total = 0
    for i in range(600):
        total += overwrite_existing(box, i, i + 1, i + 2, i + 3, i + 4, i + 5)
    return total > 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["overwrite_existing"])
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, ["overwrite_existing", "run"]


def _run_richards_queue_dispatch() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/richards_queue_dispatch_case.py"
    ns: dict[str, Any] = {}
    source = """
BUFSIZE = 4
K_DEV = 1000
K_WORK = 1001


class Packet:
    def __init__(self, link, ident, kind):
        self.link = link
        self.ident = ident
        self.kind = kind
        self.datum = 0
        self.data = [0] * BUFSIZE

    def append_to(self, lst):
        self.link = None
        if lst is None:
            return self
        p = lst
        nxt = p.link
        while nxt is not None:
            p = nxt
            nxt = p.link
        p.link = self
        return lst


class HandlerTaskRec:
    def __init__(self):
        self.work_in = None
        self.device_in = None

    def workInAdd(self, p):
        self.work_in = p.append_to(self.work_in)
        return self.work_in

    def deviceInAdd(self, p):
        self.device_in = p.append_to(self.device_in)
        return self.device_in


class HandlerTask:
    def qpkt(self, pkt):
        return pkt.ident + pkt.datum

    def waitTask(self):
        return -1

    def fn(self, pkt, r):
        h = r
        if pkt is not None:
            if pkt.kind == K_WORK:
                h.workInAdd(pkt)
            else:
                h.deviceInAdd(pkt)
        work = h.work_in
        if work is None:
            return self.waitTask()
        count = work.datum
        if count >= BUFSIZE:
            h.work_in = work.link
            return self.qpkt(work)

        dev = h.device_in
        if dev is None:
            return self.waitTask()

        h.device_in = dev.link
        dev.datum = work.data[count]
        work.datum = count + 1
        return self.qpkt(dev)


def run():
    task = HandlerTask()
    rec = HandlerTaskRec()
    base = Packet(None, 1, K_WORK)
    base.data = [1, 2, 3, 4]
    dev = Packet(None, 2, K_DEV)
    total = 0
    for _ in range(400):
        total += task.fn(base, rec)
        total += task.fn(dev, rec)
    return total != 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["Packet"].append_to)
    jit.force_compile(ns["HandlerTaskRec"].workInAdd)
    jit.force_compile(ns["HandlerTaskRec"].deviceInAdd)
    jit.force_compile(ns["HandlerTask"].fn)
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, ["Packet.append_to", "HandlerTask.fn", "run"]


def _run_richards_method_chain() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/richards_method_chain_case.py"
    ns: dict[str, Any] = {}
    source = """
class Packet:
    def __init__(self, link, ident):
        self.link = link
        self.ident = ident

    def append_to(self, lst):
        self.link = None
        if lst is None:
            return self
        p = lst
        nxt = p.link
        while nxt is not None:
            p = nxt
            nxt = p.link
        p.link = self
        return lst


class HandlerTaskRec:
    def __init__(self):
        self.work_in = None
        self.device_in = None

    def workInAdd(self, p):
        self.work_in = p.append_to(self.work_in)
        return self.work_in

    def deviceInAdd(self, p):
        self.device_in = p.append_to(self.device_in)
        return self.device_in


def run():
    rec = HandlerTaskRec()
    total = 0
    for i in range(400):
        total += rec.workInAdd(Packet(None, i)).ident
        total += rec.deviceInAdd(Packet(None, i + 1)).ident
    return total > 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["Packet"].append_to)
    jit.force_compile(ns["HandlerTaskRec"].workInAdd)
    jit.force_compile(ns["HandlerTaskRec"].deviceInAdd)
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, [
        "Packet.append_to",
        "HandlerTaskRec.workInAdd",
        "HandlerTaskRec.deviceInAdd",
        "run",
    ]


def _run_richards_attr_flow() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/richards_attr_flow_case.py"
    ns: dict[str, Any] = {}
    source = """
BUFSIZE = 4
K_DEV = 1000
K_WORK = 1001


class Packet:
    def __init__(self, link, ident, kind):
        self.link = link
        self.ident = ident
        self.kind = kind
        self.datum = 0
        self.data = [1, 2, 3, 4]


class HandlerTaskRec:
    def __init__(self):
        self.work_in = None
        self.device_in = None


class HandlerTask:
    def attr_flow(self, pkt, r):
        if pkt is not None:
            if pkt.kind == K_WORK:
                r.work_in = pkt
            else:
                r.device_in = pkt
        work = r.work_in
        if work is None:
            return -1
        count = work.datum
        if count >= BUFSIZE:
            r.work_in = work.link
            return work.ident

        dev = r.device_in
        if dev is None:
            return -1

        r.device_in = dev.link
        dev.datum = work.data[count]
        work.datum = count + 1
        return dev.datum


def run():
    task = HandlerTask()
    rec = HandlerTaskRec()
    total = 0
    rec.device_in = Packet(None, 999, K_DEV)
    for i in range(500):
        total += task.attr_flow(Packet(None, i, K_WORK), rec)
        total += task.attr_flow(Packet(None, i + 1, K_DEV), rec)
    return total > 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["HandlerTask"].attr_flow)
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, ["HandlerTask.attr_flow", "run"]


def _run_richards_post_call_checks() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/richards_post_call_checks_case.py"
    ns: dict[str, Any] = {}
    source = """
BUFSIZE = 4


class Packet:
    def __init__(self, ident, datum):
        self.ident = ident
        self.datum = datum


class HandlerTask:
    def qpkt(self, pkt):
        return pkt.ident + pkt.datum

    def waitTask(self):
        return -1

    def call_edges(self, work, dev):
        if work is None:
            return self.waitTask()
        count = work.datum
        if count >= BUFSIZE:
            return self.qpkt(work)
        if dev is None:
            return self.waitTask()
        return self.qpkt(dev)


def run():
    task = HandlerTask()
    total = 0
    for i in range(800):
        total += task.call_edges(Packet(i, BUFSIZE), Packet(i + 1, 1))
        total += task.call_edges(Packet(i, 0), None)
        total += task.call_edges(None, Packet(i + 2, 2))
    return total != 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["HandlerTask"].qpkt)
    jit.force_compile(ns["HandlerTask"].waitTask)
    jit.force_compile(ns["HandlerTask"].call_edges)
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, [
        "HandlerTask.qpkt",
        "HandlerTask.waitTask",
        "HandlerTask.call_edges",
        "run",
    ]


def _run_spectral_helper_chain() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/spectral_helper_chain_case.py"
    ns: dict[str, Any] = {}
    source = """
def eval_A(i, j):
    ij = i + j
    return 1.0 / (ij * (ij + 1) // 2 + i + 1)


def eval_A_times_u(u, n):
    result = []
    for i in range(n):
        s = 0.0
        for j in range(n):
            s += eval_A(i, j) * u[j]
        result.append(s)
    return result


def eval_At_times_u(u, n):
    result = []
    for i in range(n):
        s = 0.0
        for j in range(n):
            s += eval_A(j, i) * u[j]
        result.append(s)
    return result


def eval_AtA_times_u(u, n):
    return eval_At_times_u(eval_A_times_u(u, n), n)


def run():
    u = [1.0] * 120
    v = eval_AtA_times_u(u, 120)
    return len(v) == 120 and v[0] > 0.0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    for name in ("eval_A", "eval_A_times_u", "eval_At_times_u", "eval_AtA_times_u", "run"):
        jit.force_compile(ns[name])
    return bool(ns["run"]()), marker, [
        "eval_A",
        "eval_A_times_u",
        "eval_At_times_u",
        "eval_AtA_times_u",
        "run",
    ]


def _run_fannkuch_list_ops() -> tuple[bool, str, list[str]]:
    import cinderx.jit as jit

    marker = "/tmp/fannkuch_list_ops_case.py"
    ns: dict[str, Any] = {}
    source = """
def fannkuch_step(n):
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
    return fannkuch_step(9) > 0
"""
    code = compile(source, marker, "exec")
    exec(code, ns, ns)
    assert ns["run"]()
    jit.force_compile(ns["fannkuch_step"])
    jit.force_compile(ns["run"])
    return bool(ns["run"]()), marker, ["fannkuch_step", "run"]


MICROCASE_RUNNERS: dict[str, MicrocaseRunner] = {
    "nbody_attr_update": _run_nbody_attr_update,
    "store_init_inline_values": _run_store_init_inline_values,
    "store_overwrite_existing": _run_store_overwrite_existing,
    "store_overwrite_inline_values": _run_store_overwrite_inline_values,
    "richards_attr_flow": _run_richards_attr_flow,
    "richards_method_chain": _run_richards_method_chain,
    "richards_post_call_checks": _run_richards_post_call_checks,
    "richards_queue_dispatch": _run_richards_queue_dispatch,
    "spectral_helper_chain": _run_spectral_helper_chain,
    "fannkuch_list_ops": _run_fannkuch_list_ops,
}


def suggest_microcase_points(
    case: str,
    instruction_mix: dict[str, int],
    pattern_counts: dict[str, int],
    hir_totals: dict[str, int],
) -> list[str]:
    suggestions: list[str] = []

    if pattern_counts.get("ldr_literal_blr_pair", 0) >= 6:
        suggestions.append(
            f"{case}: repeated helper/call targets still compile as literal-load indirect calls; this is a strong ARM front-end inefficiency signal."
        )
    if pattern_counts.get("movk_heavy_call_window", 0) >= 4:
        suggestions.append(
            f"{case}: many calls are preceded by movk-heavy target materialization; this is a good case for testing literal-pool or stub-based call lowering."
        )
    if pattern_counts.get("post_call_branch_check", 0) >= 4:
        suggestions.append(
            f"{case}: many calls are immediately followed by branch checks; helper/error-check scaffolding is likely bloating hot ARM paths."
        )
    if instruction_mix.get("movk", 0) >= 10:
        suggestions.append(
            f"{case}: repeated 64-bit constant materialization (high movk count) is still visible; look for address/tag reuse or shorter immediate sequences."
        )
    if (
        pattern_counts.get("cbz", 0)
        + pattern_counts.get("cbnz", 0)
        + pattern_counts.get("tbz", 0)
        + pattern_counts.get("tbnz", 0)
        + pattern_counts.get("b_cond", 0)
        >= 14
    ):
        suggestions.append(
            f"{case}: branch density is high; favor changes that reduce control-flow checks rather than arithmetic tuning."
        )
    if hir_totals.get("LoadAttrCached", 0) + hir_totals.get("StoreAttrCached", 0) >= 8:
        suggestions.append(
            f"{case}: object attribute cache traffic is dominant; attr helper lowering or typed field specialization remains a top candidate."
        )
    if hir_totals.get("VectorCall", 0) + hir_totals.get("CallMethod", 0) >= 3:
        suggestions.append(
            f"{case}: Python-level call traffic remains visible in final HIR; inspect call target shape and helper-heavy call lowering."
        )
    if hir_totals.get("BinarySubscr", 0) + hir_totals.get("StoreSubscr", 0) >= 2:
        suggestions.append(
            f"{case}: list/subscript operations are still expensive; this case is a good feeder for ARM list-index/store lowering work."
        )
    if case == "spectral_helper_chain" and hir_totals.get("VectorCall", 0) >= 2:
        suggestions.append(
            "spectral_helper_chain: local helper calls still survive as VectorCall sites; use this case to study call lowering and inlining tradeoffs."
        )
    if case == "richards_queue_dispatch" and hir_totals.get("CallMethod", 0) >= 1:
        suggestions.append(
            "richards_queue_dispatch: branchy method-heavy queue manipulation is a good reproducer for richards-style ARM inefficiency."
        )
    if case == "richards_method_chain" and hir_totals.get("CallMethod", 0) >= 2:
        suggestions.append(
            "richards_method_chain: isolates append_to/workInAdd/deviceInAdd method traffic; use this to study method-call code shape without the full HandlerTask control flow."
        )
    if case == "richards_attr_flow" and hir_totals.get("StoreAttrCached", 0) >= 2:
        suggestions.append(
            "richards_attr_flow: isolates attr load/store and branchy state updates; use this to study richards-style object state mutation separately from method dispatch."
        )
    if case == "richards_post_call_checks" and pattern_counts.get("post_call_branch_check", 0) >= 2:
        suggestions.append(
            "richards_post_call_checks: isolates branch-selected qpkt/waitTask exits; use this to study call-plus-branch scaffolding directly."
        )
    if case == "nbody_attr_update" and hir_totals.get("StoreAttrCached", 0) >= 4:
        suggestions.append(
            "nbody_attr_update: repeated attr writes are present; use this to isolate store-side code shape separately from whole-benchmark noise."
        )

    if not suggestions:
        suggestions.append(
            f"{case}: no single pattern crossed the heuristic threshold; inspect top compiled functions and per-function disassembly manually."
        )
    return suggestions


def compute_case_metrics(
    instruction_mix: dict[str, int],
    pattern_counts: dict[str, int],
    hir_totals: dict[str, int],
    total_compiled_size: int,
) -> dict[str, float | int]:
    calls_total = int(pattern_counts.get("bl", 0) + pattern_counts.get("blr", 0))
    indirect_pairs = int(pattern_counts.get("ldr_literal_blr_pair", 0))
    post_call_branch_checks = int(pattern_counts.get("post_call_branch_check", 0))
    movk_heavy_call_window = int(pattern_counts.get("movk_heavy_call_window", 0))
    guarded_helper_calls = int(pattern_counts.get("guard_then_literal_blr", 0))
    post_call_tbz_w0_signbit = int(pattern_counts.get("post_call_tbz_w0_signbit", 0))
    attr_ops = int(
        hir_totals.get("LoadAttrCached", 0)
        + hir_totals.get("StoreAttrCached", 0)
        + hir_totals.get("LoadMethodCached", 0)
        + hir_totals.get("LoadModuleAttrCached", 0)
        + hir_totals.get("CallMethod", 0)
    )
    not_negative_source_total = int(
        sum(hir_totals.get(name, 0) for name in hotspot.NOT_NEGATIVE_SOURCE_OPS)
    )
    call_ops = int(hir_totals.get("VectorCall", 0) + hir_totals.get("CallMethod", 0))
    branch_ops = int(
        hir_totals.get("Branch", 0)
        + hir_totals.get("CondBranch", 0)
        + hir_totals.get("CondBranchIterNotDone", 0)
    )
    refcount_ops = int(
        hir_totals.get("Decref", 0)
        + hir_totals.get("XDecref", 0)
        + hir_totals.get("BatchDecref", 0)
    )

    def ratio(num: int, den: int) -> float:
        return float(num) / float(den) if den else 0.0

    return {
        "total_compiled_size": int(total_compiled_size),
        "calls_total": calls_total,
        "indirect_call_pairs": indirect_pairs,
        "indirect_call_ratio": ratio(indirect_pairs, calls_total),
        "post_call_branch_checks": post_call_branch_checks,
        "post_call_branch_ratio": ratio(post_call_branch_checks, calls_total),
        "post_call_tbz_w0_signbit": post_call_tbz_w0_signbit,
        "post_call_tbz_w0_signbit_ratio": ratio(post_call_tbz_w0_signbit, calls_total),
        "movk_per_call": ratio(int(instruction_mix.get("movk", 0)), calls_total),
        "movk_heavy_call_window": movk_heavy_call_window,
        "movk_heavy_call_ratio": ratio(movk_heavy_call_window, calls_total),
        "guarded_helper_calls": guarded_helper_calls,
        "guarded_helper_ratio": ratio(guarded_helper_calls, calls_total),
        "not_negative_source_total": not_negative_source_total,
        "attr_ops": attr_ops,
        "call_ops": call_ops,
        "branch_ops": branch_ops,
        "refcount_ops": refcount_ops,
        "calls_per_kb": ratio(calls_total, max(total_compiled_size, 1)) * 1024.0,
    }


def summarize_case_rankings(results: list[dict[str, Any]]) -> dict[str, list[list[Any]]]:
    metrics_to_rank = (
        "indirect_call_ratio",
        "post_call_branch_ratio",
        "post_call_tbz_w0_signbit_ratio",
        "movk_per_call",
        "guarded_helper_ratio",
        "not_negative_source_total",
        "attr_ops",
        "call_ops",
        "branch_ops",
        "refcount_ops",
    )
    summary: dict[str, list[list[Any]]] = {}
    for metric in metrics_to_rank:
        ranking = sorted(
            (
                [result["case"], result["derived_metrics"][metric]]
                for result in results
            ),
            key=lambda item: (-float(item[1]), item[0]),
        )
        summary[metric] = ranking
    return summary


def _top_items_to_dict(items: list[list[Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, value in items:
        out[str(key)] = int(value)
    return out


def classify_store_shape(hir_counts: dict[str, int]) -> str:
    store_attr = int(hir_counts.get("StoreAttrCached", 0) + hir_counts.get("StoreAttr", 0))
    load_attr = int(hir_counts.get("LoadAttrCached", 0) + hir_counts.get("LoadAttr", 0))
    methodish = int(hir_counts.get("LoadMethodCached", 0) + hir_counts.get("CallMethod", 0))

    if store_attr > 0 and load_attr == 0 and methodish == 0:
        return "init_like"
    if store_attr > 0 and load_attr > 0:
        return "update_like"
    if store_attr > 0 and methodish > 0:
        return "mixed_store_method"
    return "other"


def build_focus_groups(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    store_entries: list[dict[str, Any]] = []
    for result in results:
        case = result["case"]
        for fn in result["top_functions"]:
            source_items = _top_items_to_dict(fn.get("likely_not_negative_hir_sources", []))
            store_sources = {
                key: value
                for key, value in source_items.items()
                if key in STORE_STATUS_SOURCE_OPS
            }
            pattern_counts = fn.get("objdump_pattern_counts", {})
            tbz_count = int(pattern_counts.get("post_call_tbz_w0_signbit", 0))
            if not store_sources and tbz_count == 0:
                continue
            hir_counts = fn.get("hir_counts", {})
            store_attr_cached = int(hir_counts.get("StoreAttrCached", 0))
            load_attr_cached = int(hir_counts.get("LoadAttrCached", 0))
            entry = {
                "case": case,
                "qualname": fn["qualname"],
                "compiled_size": int(fn["compiled_size"]),
                "store_shape": classify_store_shape(hir_counts),
                "store_attr_cached": store_attr_cached,
                "load_attr_cached": load_attr_cached,
                "store_status_sources": store_sources,
                "store_status_source_total": int(sum(store_sources.values())),
                "post_call_tbz_w0_signbit": tbz_count,
                "post_call_branch_checks": int(pattern_counts.get("post_call_branch_check", 0)),
                "ldr_literal_blr_pair": int(pattern_counts.get("ldr_literal_blr_pair", 0)),
                "movk_heavy_call_window": int(pattern_counts.get("movk_heavy_call_window", 0)),
                "interesting_windows": [
                    window
                    for window in fn.get("objdump_interesting_windows", [])
                    if window["kind"] in {"post_call_tbz_w0_signbit", "post_call_branch_check", "ldr_literal_blr_pair", "movk_heavy_call_window"}
                ][:5],
            }
            store_entries.append(entry)

    store_entries.sort(
        key=lambda item: (
            -item["store_status_source_total"],
            -item["post_call_tbz_w0_signbit"],
            -item["post_call_branch_checks"],
            -item["compiled_size"],
            item["case"],
            item["qualname"],
        )
    )
    return {"store_status_helper": store_entries}


def run_microcase(case: str) -> tuple[bool, str, list[str]]:
    return MICROCASE_RUNNERS[case]()


def collect_case_summary(
    case: str,
    top: int,
    include_disasm: bool,
) -> dict[str, Any]:
    import cinderx.jit as jit
    import cinderjit

    jit.enable()
    jit.compile_after_n_calls(1)

    ok, marker, expected = run_microcase(case)
    if not ok:
        raise RuntimeError(f"{case} microcase returned failure")

    compiled_funcs = list(cinderjit.get_compiled_functions())
    case_funcs = [
        func
        for func in compiled_funcs
        if marker in getattr(getattr(func, "__code__", None), "co_filename", "").replace("\\", "/")
    ]
    case_funcs.sort(key=lambda func: int(cinderjit.get_compiled_size(func)), reverse=True)
    total_compiled_size = sum(int(cinderjit.get_compiled_size(func)) for func in case_funcs)

    top_funcs = [
        hotspot.collect_function_info(func, jit, cinderjit, include_disasm)
        for func in case_funcs[:top]
    ]

    with tempfile.TemporaryDirectory() as td:
        elf_path = Path(td) / f"{case}.elf"
        cinderjit.dump_elf(str(elf_path))
        objdump = subprocess.run(
            ["objdump", "-d", str(elf_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        whole_disasm = objdump.stdout

    instruction_mix = hotspot.count_instruction_mix(whole_disasm)
    pattern_counts = hotspot.count_aarch64_patterns(whole_disasm)
    hir_totals = hotspot.aggregate_hir_counts(top_funcs)
    hotspot.enrich_functions_with_objdump(top_funcs, whole_disasm)
    derived_metrics = compute_case_metrics(
        instruction_mix,
        pattern_counts,
        hir_totals,
        total_compiled_size,
    )

    return {
        "case": case,
        "marker": marker,
        "expected_functions": expected,
        "compiled_functions_total": len(compiled_funcs),
        "microcase_compiled_functions": len(case_funcs),
        "total_compiled_size": total_compiled_size,
        "instruction_mix": instruction_mix,
        "pattern_counts": pattern_counts,
        "top_instruction_mix": hotspot.top_items(instruction_mix, limit=12),
        "top_pattern_counts": hotspot.top_items(pattern_counts, limit=12),
        "top_functions": top_funcs,
        "aggregate_hir_counts": hir_totals,
        "top_hir_ops": hotspot.top_items(hir_totals, limit=12),
        "derived_metrics": derived_metrics,
        "suggestions": suggest_microcase_points(
            case,
            instruction_mix,
            pattern_counts,
            hir_totals,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=["all", *sorted(MICROCASE_RUNNERS)],
        required=True,
        help="Microcase to scan",
    )
    parser.add_argument("--output", required=True, help="Path to JSON output")
    parser.add_argument("--top", type=int, default=6, help="Top compiled functions to include")
    parser.add_argument(
        "--no-function-disasm",
        action="store_true",
        help="Skip per-function disassembly capture",
    )
    args = parser.parse_args()

    cases = sorted(MICROCASE_RUNNERS) if args.case == "all" else [args.case]
    results = [
        collect_case_summary(case, args.top, include_disasm=not args.no_function_disasm)
        for case in cases
    ]
    payload: dict[str, Any]
    if args.case == "all":
        global_patterns: Counter[str] = Counter()
        global_hir: Counter[str] = Counter()
        for result in results:
            global_patterns.update(result["pattern_counts"])
            global_hir.update(result["aggregate_hir_counts"])
        payload = {
            "cases": results,
            "aggregate_pattern_counts": dict(global_patterns),
            "aggregate_hir_counts": dict(global_hir),
            "top_aggregate_patterns": hotspot.top_items(dict(global_patterns), limit=12),
            "top_aggregate_hir_ops": hotspot.top_items(dict(global_hir), limit=12),
            "case_rankings": summarize_case_rankings(results),
            "focus_groups": build_focus_groups(results),
        }
    else:
        payload = results[0]

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
