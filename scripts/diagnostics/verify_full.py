#!/usr/bin/env python3
"""
完整验证脚本 - 包含 JIT 状态、HIR 导出、编译信息
"""

import sys
import time
import statistics
import json
from pathlib import Path


def load_regexes():
    """加载正则表达式"""
    json_path = Path("/root/regex_list.json")
    if not json_path.exists():
        json_path = Path("regex_list.json")

    with open(json_path) as f:
        data = json.load(f)

    return [(item["pattern"], item["flags"]) for item in data]


def bench_cpython(regexes, loops=10):
    """CPython 基准测试"""
    import re

    times = []
    for _ in range(loops):
        start = time.perf_counter()
        for regex, flags in regexes:
            re.purge()
            re.compile(regex, flags)
        times.append(time.perf_counter() - start)
    return statistics.mean(times), statistics.stdev(times)


def bench_cinderjit(regexes, loops=10):
    """CinderX JIT 基准测试"""
    import re
    import cinderjit

    cinderjit.enable()

    # 预热
    print("    预热中...")
    for _ in range(3):
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


def verify_cpython_jit():
    """检查 CPython 是否启用了 JIT"""
    import sys
    import os

    results = {
        "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "jit_env": os.environ.get("PYTHON_JIT", "not set"),
        "jit_compiler": None,
        "is_jit_enabled": False,
    }

    # Check for Python's experimental JIT (3.13+)
    if hasattr(sys, "_xoptions"):
        jit_opt = sys._xoptions.get("jit", False)
        if jit_opt:
            results["is_jit_enabled"] = True
            results["jit_compiler"] = "CPython Experimental JIT"

    # Check environment variable
    if os.environ.get("PYTHON_JIT", "").lower() in ("1", "true", "yes"):
        results["is_jit_enabled"] = True
        results["jit_compiler"] = "CPython Experimental JIT (via env)"

    # Check for Pyston
    try:
        import __pyston__

        results["is_jit_enabled"] = True
        results["jit_compiler"] = "Pyston"
    except ImportError:
        pass

    # Check for Pyjion
    try:
        import _pyjion

        results["is_jit_enabled"] = True
        results["jit_compiler"] = "Pyjion"
    except ImportError:
        pass

    return results


def verify_cinderjit():
    """检查 CinderX JIT 状态"""
    try:
        import cinderjit
        import json

        results = {
            "available": True,
            "enabled": cinderjit.is_enabled(),
            "hir_inliner_enabled": cinderjit.is_hir_inliner_enabled(),
            "compiled_functions": len(cinderjit.get_compiled_functions()),
            "hir_export_possible": False,
            "hir_export_error": None,
        }

        # Try to export HIR
        regexes = load_regexes()

        def test_func():
            import re

            for regex, flags in regexes[:10]:
                re.purge()
                re.compile(regex, flags)

        cinderjit.force_compile(test_func)

        if cinderjit.is_jit_compiled(test_func):
            results["test_function_compiled"] = True
            results["test_function_size"] = cinderjit.get_compiled_size(test_func)

            # Try to get HIR
            try:
                cinderjit.print_hir(test_func)
                results["hir_export_possible"] = True
            except Exception as e:
                results["hir_export_error"] = str(e)

            # Get opcode counts
            try:
                counts = cinderjit.get_function_hir_opcode_counts(test_func)
                results["hir_opcode_counts"] = counts
            except Exception as e:
                results["opcode_count_error"] = str(e)

        return results

    except ImportError as e:
        return {"available": False, "error": str(e)}


def main():
    print("=" * 70)
    print("regex_compile 完整验证报告")
    print("=" * 70)

    # 1. CPython JIT 状态
    print("\n[1] CPython JIT 状态检查")
    cpython_jit = verify_cpython_jit()
    print(f"    Python 版本: {cpython_jit['version']}")
    print(f"    JIT 编译器: {cpython_jit['jit_compiler'] or 'None (纯解释器)'}")
    print(f"    JIT 启用: {'✅ Yes' if cpython_jit['is_jit_enabled'] else '❌ No'}")
    print(f"    PYTHON_JIT 环境变量: {cpython_jit['jit_env']}")

    # 2. CinderX JIT 状态
    print("\n[2] CinderX JIT 状态检查")
    cinderjit_info = verify_cinderjit()

    if not cinderjit_info["available"]:
        print(f"    ❌ CinderX 不可用: {cinderjit_info.get('error', 'Unknown')}")
    else:
        print(f"    ✅ CinderX 可用")
        print(f"    JIT 已启用: {'Yes' if cinderjit_info['enabled'] else 'No'}")
        print(
            f"    HIR Inliner: {'Enabled' if cinderjit_info['hir_inliner_enabled'] else 'Disabled'}"
        )
        print(f"    已编译函数数: {cinderjit_info.get('compiled_functions', 0)}")

        if cinderjit_info.get("test_function_compiled"):
            print(
                f"    测试函数已编译: ✅ ({cinderjit_info['test_function_size']} bytes)"
            )

        # HIR 导出状态
        if cinderjit_info.get("hir_export_possible"):
            print(f"    HIR 导出: ✅ 可用")
        else:
            print(f"    HIR 导出: ❌ 不可用")
            if cinderjit_info.get("hir_export_error"):
                print(f"    错误信息: {cinderjit_info['hir_export_error']}")
                if "debug build" in cinderjit_info["hir_export_error"].lower():
                    print(f"    ⚠️  需要 Debug 构建的 CinderX 才能导出 HIR")

    # 3. 性能测试
    print("\n[3] 性能测试")
    try:
        regexes = load_regexes()
        print(f"    加载了 {len(regexes)} 个正则表达式")
    except Exception as e:
        print(f"    ❌ 加载正则表达式失败: {e}")
        return 1

    loops = 10

    # CPython 测试
    print(f"\n    [3.1] CPython 基线 ({loops} 次)...")
    mean_cpython, std_cpython = bench_cpython(regexes, loops)
    print(f"          时间: {mean_cpython * 1000:.3f}ms ± {std_cpython * 1000:.3f}ms")

    # CinderX 测试（如果可用）
    if cinderjit_info.get("available"):
        print(f"\n    [3.2] CinderX JIT ({loops} 次)...")
        try:
            mean_jit, std_jit = bench_cinderjit(regexes, loops)
            print(f"          时间: {mean_jit * 1000:.3f}ms ± {std_jit * 1000:.3f}ms")

            # 对比
            slowdown = mean_jit / mean_cpython
            print(f"\n    [3.3] 性能对比")
            print(f"          CPython: {mean_cpython * 1000:.3f}ms")
            print(f"          CinderX: {mean_jit * 1000:.3f}ms")
            print(f"          比率: {slowdown:.2f}x")

            if slowdown < 1.0:
                print(f"          ✅ CinderX 更快 ({(1 - slowdown) * 100:.1f}%)")
            elif slowdown > 1.05:
                print(f"          ⚠️  CinderX 更慢 ({(slowdown - 1) * 100:.1f}%)")
            else:
                print(f"          ⚡ 性能相当")

        except Exception as e:
            print(f"          ❌ CinderX 测试失败: {e}")

    # 4. 可信度评估
    print("\n[4] 测试结果可信度评估")

    issues = []

    if not cpython_jit["is_jit_enabled"]:
        issues.append("CPython 未启用 JIT，测试的是解释器性能")

    if cinderjit_info.get("available") and not cinderjit_info.get(
        "hir_export_possible"
    ):
        issues.append("无法导出 HIR，无法验证 JIT 编译质量")

    if len(regexes) < 100:
        issues.append(f"正则表达式数量较少 ({len(regexes)} 个)，可能不够代表性")

    if issues:
        print("    ⚠️  发现以下问题影响测试结果可信度:")
        for i, issue in enumerate(issues, 1):
            print(f"        {i}. {issue}")
        print("\n    建议:")
        print("        - 确保 CPython 启用了 JIT（如果预期有 JIT 对比）")
        print("        - 使用 Debug 构建的 CinderX 以导出 HIR")
        print("        - 使用完整的 pyperformance 测试数据集")
    else:
        print("    ✅ 测试结果可信")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
