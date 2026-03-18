#!/usr/bin/env python3
"""
测试启用 HIR Inliner 的效果
"""

import sys
import time
import statistics
import json

sys.path.insert(0, "/Users/luchen/Agents-Repo/OpenCode/cinderx/cinderx/PythonLib")

import cinderx.jit as jit

# 加载正则表达式
with open("/tmp/regex_list.json") as f:
    data = json.load(f)
    regexes = [(item["pattern"], item["flags"]) for item in data]

print("=" * 70)
print("HIR Inliner 效果测试")
print("=" * 70)

print(f"\n[1] 测试数据: {len(regexes)} 个正则表达式")

# 定义测试函数
import re


def bench_regex_compile():
    for regex, flags in regexes:
        re.purge()
        re.compile(regex, flags)


# 测试配置
configs = [
    ("HIR Inliner 禁用", lambda: None),
    ("HIR Inliner 启用", jit.enable_hir_inliner),
]

results = {}

for config_name, setup_fn in configs:
    print(f"\n[2] 测试配置: {config_name}")

    # 重置 JIT
    jit.disable()
    jit.enable()

    # 应用配置
    setup_fn()

    print(f"    HIR Inliner 状态: {'启用' if jit.is_hir_inliner_enabled() else '禁用'}")

    # 编译函数
    jit.compile_after_n_calls(0)
    jit.force_compile(bench_regex_compile)

    if not jit.is_jit_compiled(bench_regex_compile):
        print(f"    ❌ 编译失败")
        continue

    print(f"    ✅ 函数已编译 ({jit.get_compiled_size(bench_regex_compile)} bytes)")

    # 预热
    for _ in range(3):
        bench_regex_compile()

    # 测试
    times = []
    for _ in range(10):
        start = time.perf_counter()
        bench_regex_compile()
        times.append(time.perf_counter() - start)

    mean_time = statistics.mean(times)
    std_time = statistics.stdev(times)

    results[config_name] = mean_time
    print(f"    平均时间: {mean_time * 1000:.2f}ms ± {std_time * 1000:.2f}ms")

# 对比结果
print(f"\n[3] 性能对比")
if len(results) == 2:
    baseline = results["HIR Inliner 禁用"]
    optimized = results["HIR Inliner 启用"]

    improvement = (baseline - optimized) / baseline * 100

    print(f"    基线 (禁用): {baseline * 1000:.2f}ms")
    print(f"    优化 (启用): {optimized * 1000:.2f}ms")
    print(f"    改进: {improvement:+.2f}%")

    if improvement > 0:
        print(f"    ✅ HIR Inliner 有效")
    elif improvement < -5:
        print(f"    ⚠️  HIR Inliner 导致性能下降")
    else:
        print(f"    ⚡ 性能相当")

print("\n" + "=" * 70)
