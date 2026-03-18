#!/usr/bin/env python3
"""
regex_compile 性能诊断工具 (Docker ARM64 版本)
"""

import sys
import time
import statistics
from pathlib import Path


def capture_regexes_docker():
    """在 Docker 环境中捕获正则表达式"""
    import re

    regexes = []

    real_compile = re.compile
    real_search = re.search
    real_sub = re.sub

    def capture_compile(regex, flags=0):
        regexes.append((regex, flags))
        return real_compile(regex, flags)

    def capture_search(regex, target, flags=0):
        regexes.append((regex, flags))
        return real_search(regex, target, flags)

    def capture_sub(regex, *args):
        regexes.append((regex, 0))
        return real_sub(regex, *args)

    re.compile = capture_compile
    re.search = capture_search
    re.sub = capture_sub

    try:
        # Docker 环境中的路径
        sys.path.insert(
            0,
            "/root/pyperformance/pyperformance/data-files/benchmarks/bm_regex_compile",
        )
        import bm_regex_effbot

        bm_regex_effbot.bench_regex_effbot(1)

        import bm_regex_v8

        bm_regex_v8.bench_regex_v8(1)
    except ImportError as e:
        print(f"Warning: Could not import benchmark modules: {e}")
        # 备选：直接读取 run_benchmark.py 中的正则表达式
        try:
            import run_benchmark

            regexes = run_benchmark.capture_regexes()
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
    finally:
        re.compile = real_compile
        re.search = real_search
        re.sub = real_sub

    return regexes


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


def main():
    print("=" * 70)
    print("regex_compile 性能诊断 (Docker ARM64)")
    print("=" * 70)

    # 捕获正则表达式
    print("\n[1] 捕获正则表达式...")
    regexes = capture_regexes_docker()
    print(f"    捕获了 {len(regexes)} 个正则表达式")

    if len(regexes) == 0:
        print("\n❌ 错误：未能捕获任何正则表达式")
        return 1

    loops = 10

    # 测试: CPython 基线
    print(f"\n[2] CPython 基线测试 ({loops} 次循环)...")
    mean, std = bench_cpython(regexes, loops)
    print(f"    时间: {mean * 1000:.3f}ms ± {std * 1000:.3f}ms")

    print("\n" + "=" * 70)
    print(f"✅ CPython 基线: {mean * 1000:.3f}ms")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
