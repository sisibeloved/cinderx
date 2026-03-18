#!/usr/bin/env python3
"""
完整对比测试: CPython JIT vs CinderX JIT
在单个脚本中对比两种 JIT 实现
"""

import sys
import time
import statistics
import json
from pathlib import Path
import os


def load_regexes():
    """加载正则表达式"""
    json_path = Path("/root/regex_list.json")
    if not json_path.exists():
        json_path = Path("regex_list.json")

    with open(json_path) as f:
        data = json.load(f)

    return [(item["pattern"], item["flags"]) for item in data]


def bench_cpython_jit(regexes, loops=10):
    """使用 CPython JIT 运行基准测试"""
    import re

    # 预热 - 让 JIT 有机会编译
    print("    CPython JIT 预热中...")
    for _ in range(5):
        for regex, flags in regexes[:100]:
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


def bench_cinderx_jit(regexes, loops=10):
    """使用 CinderX JIT 运行基准测试"""
    import re
    import cinderjit

    # 启用 CinderX JIT
    cinderjit.enable()

    # 预热
    print("    CinderX JIT 预热中...")
    for _ in range(5):
        for regex, flags in regexes[:100]:
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
    print("完整对比测试: CPython JIT vs CinderX JIT")
    print("=" * 70)

    # 检查环境
    print("\n[1] 环境检查")

    # CPython JIT status
    python_jit = os.environ.get("PYTHON_JIT", "not set")
    print(f"    PYTHON_JIT 环境变量: {python_jit}")

    # CinderX availability
    cinderx_available = False
    try:
        import cinderjit

        cinderx_available = True
        print(f"    CinderX: ✅ 可用")
    except ImportError:
        print(f"    CinderX: ❌ 不可用")

    # 加载正则表达式
    print("\n[2] 加载正则表达式...")
    try:
        regexes = load_regexes()
        print(f"    加载了 {len(regexes)} 个正则表达式")
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        return 1

    loops = 10
    results = {}

    # 测试 1: CPython JIT
    print(f"\n[3] CPython JIT 测试 ({loops} 次循环)...")
    try:
        mean_cpython, std_cpython = bench_cpython_jit(regexes, loops)
        results["cpython_jit"] = {"mean": mean_cpython, "std": std_cpython}
        print(f"    时间: {mean_cpython * 1000:.3f}ms ± {std_cpython * 1000:.3f}ms")
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        results["cpython_jit"] = {"error": str(e)}

    # 测试 2: CinderX JIT（如果可用）
    if cinderx_available:
        print(f"\n[4] CinderX JIT 测试 ({loops} 次循环)...")
        try:
            mean_cinderx, std_cinderx = bench_cinderx_jit(regexes, loops)
            results["cinderx_jit"] = {"mean": mean_cinderx, "std": std_cinderx}
            print(f"    时间: {mean_cinderx * 1000:.3f}ms ± {std_cinderx * 1000:.3f}ms")
        except Exception as e:
            print(f"    ❌ 错误: {e}")
            results["cinderx_jit"] = {"error": str(e)}

    # 对比分析
    print("\n[5] 性能对比")
    if "cpython_jit" in results and "mean" in results["cpython_jit"]:
        cpython_time = results["cpython_jit"]["mean"] * 1000
        print(f"    CPython JIT: {cpython_time:.3f}ms")

        if "cinderx_jit" in results and "mean" in results["cinderx_jit"]:
            cinderx_time = results["cinderx_jit"]["mean"] * 1000
            print(f"    CinderX JIT: {cinderx_time:.3f}ms")

            ratio = cinderx_time / cpython_time
            print(f"\n    比率 (CinderX/CPython): {ratio:.2f}x")

            if ratio < 1.0:
                improvement = (1.0 - ratio) * 100
                print(f"    ✅ CinderX 更快: {improvement:.1f}%")
            elif ratio > 1.05:
                slowdown = (ratio - 1.0) * 100
                print(f"    ⚠️  CinderX 更慢: {slowdown:.1f}%")
            else:
                print(f"    ⚡ 性能相当")

    # 保存结果
    import json

    results_file = "/tmp/comparison_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n    结果已保存: {results_file}")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
