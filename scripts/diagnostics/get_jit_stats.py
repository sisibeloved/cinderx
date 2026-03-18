#!/usr/bin/env python3
"""
获取 CinderX JIT 统计信息（Release 版本可用）
"""

import sys
import json

sys.path.insert(0, "/root")

import cinderjit
import re

# Enable JIT
cinderjit.enable()

# Load regexes
with open("/root/regex_list.json") as f:
    data = json.load(f)
    regexes = [(item["pattern"], item["flags"]) for item in data]

print("=" * 70)
print("CinderX JIT 统计信息")
print("=" * 70)


# Test function
def bench_test():
    for regex, flags in regexes:
        re.purge()
        re.compile(regex, flags)


# Force compile
cinderjit.force_compile(bench_test)

if cinderjit.is_jit_compiled(bench_test):
    print("\n✅ 测试函数已编译")
    print(f"   代码大小: {cinderjit.get_compiled_size(bench_test)} bytes")
    print(f"   栈大小: {cinderjit.get_compiled_stack_size(bench_test)} bytes")

    # Get HIR opcode counts
    try:
        counts = cinderjit.get_function_hir_opcode_counts(bench_test)
        print(f"\n📊 HIR Opcode 计数:")
        if counts:
            for opcode, count in sorted(counts.items(), key=lambda x: -x[1])[:20]:
                print(f"   {opcode}: {count}")
        else:
            print("   (无数据)")
    except Exception as e:
        print(f"\n⚠️  无法获取 HIR opcode 计数: {e}")

    # Get runtime stats
    try:
        stats = cinderjit.get_and_clear_runtime_stats()
        print(f"\n📈 运行时统计:")
        print(f"   {stats}")
    except Exception as e:
        print(f"\n⚠️  无法获取运行时统计: {e}")

    # Get compilation time
    try:
        comp_time = cinderjit.get_function_compilation_time(bench_test)
        print(f"\n⏱️  编译时间: {comp_time:.3f}ms")
    except Exception as e:
        print(f"\n⚠️  无法获取编译时间: {e}")

    # Run the function to collect runtime data
    print("\n🚀 执行测试函数...")
    bench_test()

    # Get stats after execution
    try:
        stats = cinderjit.get_and_clear_runtime_stats()
        print(f"\n📈 执行后统计:")
        print(f"   {stats}")
    except Exception as e:
        print(f"\n⚠️  无法获取执行后统计: {e}")

    # Get allocator stats
    try:
        alloc_stats = cinderjit.get_allocator_stats()
        print(f"\n💾 分配器统计:")
        print(f"   {alloc_stats}")
    except Exception as e:
        print(f"\n⚠️  无法获取分配器统计: {e}")

    # Check if HIR inliner is enabled
    print(
        f"\n🔧 HIR Inliner: {'启用' if cinderjit.is_hir_inliner_enabled() else '禁用'}"
    )

    # Get number of compiled functions
    compiled_funcs = cinderjit.get_compiled_functions()
    print(f"\n📋 已编译函数数: {len(compiled_funcs)}")

else:
    print("\n❌ 测试函数未编译")

print("\n" + "=" * 70)
print("\n⚠️  注意: 完整 HIR 导出需要 Debug 构建的 CinderX")
print("   Debug 构建正在进行中...")
print("=" * 70)
