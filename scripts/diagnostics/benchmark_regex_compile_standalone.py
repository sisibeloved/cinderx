#!/usr/bin/env python3
"""
regex_compile 性能诊断工具 (独立版本)
使用预导出的正则表达式列表
"""

import sys
import time
import statistics
import json
from pathlib import Path


def load_regexes():
    """从 JSON 文件加载正则表达式"""
    json_path = Path("/root/regex_list.json")
    if not json_path.exists():
        json_path = Path("regex_list.json")

    with open(json_path) as f:
        data = json.load(f)

    return [(item["pattern"], item["flags"]) for item in data]


def bench_cpython(regexes, loops=10):
    """使用 CPython 运行基准测试"""
    import re

    times = []
    for _ in range(loops):
        start = time.perf_counter()
        for regex, flags in regexes:
            re.purge()
            re.compile(regex, flags)
        times.append(time.perf_counter() - start)

    return statistics.mean(times), statistics.stdev(times)


def bench_with_cinderjit(regexes, loops=10):
    """使用 CinderX JIT 运行基准测试"""
    import re
    import cinderjit

    # 启用 JIT
    cinderjit.enable()

    # 预热 - 让 JIT 有机会编译
    print("    预热中...")
    for _ in range(3):
        for regex, flags in regexes[:100]:  # 只用前100个预热
            re.purge()
            re.compile(regex, flags)

    times = []
    for _ in range(loops):
        start = time.perf_counter()
        for regex, flags in regexes:
            re.purge()
            re.compile(regex, flags)
        times.append(time.perf_counter() - start)

    return statistics.mean(times), statistics.stdev(times)


def main():
    print("=" * 70)
    print("regex_compile 性能诊断")
    print("=" * 70)

    # 加载正则表达式
    print("\n[1] 加载正则表达式...")
    try:
        regexes = load_regexes()
        print(f"    加载了 {len(regexes)} 个正则表达式")
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        return 1

    if len(regexes) == 0:
        print("\n❌ 错误: 没有正则表达式")
        return 1

    loops = 10

    # 测试 1: CPython 基线
    print(f"\n[2] CPython 基线测试 ({loops} 次循环)...")
    mean_cpython, std_cpython = bench_cpython(regexes, loops)
    print(f"    时间: {mean_cpython * 1000:.3f}ms ± {std_cpython * 1000:.3f}ms")

    # 测试 2: CinderX JIT
    print(f"\n[3] CinderX JIT 测试 ({loops} 次循环)...")
    try:
        mean_jit, std_jit = bench_with_cinderjit(regexes, loops)
        print(f"    时间: {mean_jit * 1000:.3f}ms ± {std_jit * 1000:.3f}ms")

        # 计算慢化因子
        slowdown = mean_jit / mean_cpython
        print(f"\n[4] 性能对比")
        print(f"    CPython:    {mean_cpython * 1000:.3f}ms")
        print(f"    CinderX:    {mean_jit * 1000:.3f}ms")
        print(f"    慢化因子:   {slowdown:.2f}x")

        if slowdown > 1.05:
            print(f"    ⚠️  性能劣化: {(slowdown - 1) * 100:.1f}%")
        else:
            print(f"    ✅ 性能达标或更好")

    except ImportError as e:
        print(f"    ⚠️  CinderX 不可用: {e}")
        print("\n[4] 性能对比")
        print(f"    CPython: {mean_cpython * 1000:.3f}ms")
        print("    CinderX: 未测试")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
