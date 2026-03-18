#!/usr/bin/env python3
"""
在 macOS 本地导出 HIR
"""

import sys
import json
from pathlib import Path

# 确保可以导入 cinderx
sys.path.insert(0, "cinderx/PythonLib")

import cinderx
import cinderjit
import re

print("=" * 70)
print("macOS 本地 HIR 导出")
print("=" * 70)

# 检查 CinderX 状态
print(f"\n[1] CinderX 状态")
print(f"    已初始化: {cinderx.is_initialized()}")
print(f"    JIT 已启用: {cinderjit.is_enabled()}")

# 启用 JIT
cinderjit.enable()
print(f"    JIT 现在已启用: {cinderjit.is_enabled()}")

# 加载正则表达式
print(f"\n[2] 加载正则表达式...")
try:
    with open("/tmp/regex_list.json") as f:
        data = json.load(f)
        regexes = [(item["pattern"], item["flags"]) for item in data]
    print(f"    加载了 {len(regexes)} 个正则表达式")
except Exception as e:
    print(f"    错误: {e}")
    # 使用备选数据
    regexes = [(r"test", 0), (r"[a-z]+", 0), (r"\d+", 0)]
    print(f"    使用备选数据: {len(regexes)} 个")

# 定义测试函数
print(f"\n[3] 定义并编译测试函数...")


def bench_test():
    for regex, flags in regexes[:100]:  # 使用100个进行测试
        re.purge()
        re.compile(regex, flags)


# 强制编译
cinderjit.force_compile(bench_test)

if cinderjit.is_jit_compiled(bench_test):
    print(f"    ✅ 函数已编译")
    print(f"    代码大小: {cinderjit.get_compiled_size(bench_test)} bytes")

    # 获取 HIR opcode 计数
    try:
        counts = cinderjit.get_function_hir_opcode_counts(bench_test)
        print(f"\n    HIR Opcode 计数:")
        if counts:
            for opcode, count in sorted(counts.items(), key=lambda x: -x[1])[:10]:
                print(f"      {opcode}: {count}")
    except Exception as e:
        print(f"    获取 opcode 计数失败: {e}")

    # 导出 HIR
    print(f"\n[4] 导出 HIR...")
    try:
        # 保存到文件
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cinderjit.print_hir(bench_test)

        hir_output = f.getvalue()

        output_file = "/tmp/hir_dump_macos.txt"
        with open(output_file, "w") as out:
            out.write(hir_output)

        print(f"    ✅ HIR 已保存到: {output_file}")
        print(f"    文件大小: {len(hir_output)} bytes")

        # 显示前50行
        print(f"\n[5] HIR 预览 (前50行):")
        print("-" * 70)
        lines = hir_output.split("\n")[:50]
        for line in lines:
            print(line)
        if len(hir_output.split("\n")) > 50:
            print(f"\n... (还有 {len(hir_output.split('\n')) - 50} 行)")
        print("-" * 70)

    except Exception as e:
        print(f"    ❌ 导出 HIR 失败: {e}")
        import traceback

        traceback.print_exc()
else:
    print(f"    ❌ 函数未编译")

print("\n" + "=" * 70)
