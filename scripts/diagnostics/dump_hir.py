#!/usr/bin/env python3
"""
提取生成器的 HIR dump 用于优化对比分析。
"""

import sys
import os
from pathlib import Path

# Add PythonLib to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))

# Add built library to path
build_path = Path(__file__).parent.parent.parent / "scratch" / "lib.macosx-26.0-arm64-cpython-314"
if build_path.exists():
    sys.path.insert(0, str(build_path))

class Node:
    """递归生成器迭代器（yield-from 模式）。"""
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        if self.left:
            yield from self.left
        yield self.value
        if self.right:
            yield from self.right

class StackNode:
    """栈式迭代器（非递归）。"""
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        stack = [(self, False, False)]
        while stack:
            node, left_done, right_done = stack.pop()
            if not left_done and node.left:
                stack.append((node, True, False))
                stack.append((node.left, False, False))
            elif not right_done:
                yield node.value
                if node.right:
                    stack.append((node, True, True))
                    stack.append((node.right, False, False))

def main():
    print("=" * 60)
    print("HIR Dump 提取工具")
    print("=" * 60)

    # 启用 JIT
    try:
        import cinderx
        import cinderx.jit as jit
        jit.enable()
    except ImportError as e:
        print(f"\n错误：CinderX 不可用: {e}")
        print("请先构建并安装 CinderX")
        return 1

    # 强制编译目标函数
    print("\n强制编译 Node.__iter__ 和 StackNode.__iter__...")
    jit.force_compile(Node.__iter__)
    jit.force_compile(StackNode.__iter__)

    print(f"  Node.__iter__ 已编译: {jit.is_jit_compiled(Node.__iter__)}")
    print(f"  StackNode.__iter__ 已编译: {jit.is_jit_compiled(StackNode.__iter__)}")

    # 构建简单测试树
    print("\n构建测试树...")
    node = Node(2, Node(1), Node(3))
    stack_node = StackNode(2, StackNode(1), StackNode(3))

    # 执行以触发 HIR dump
    print("\n执行生成器（HIR 将输出到日志文件）...")
    result1 = list(node)
    result2 = list(stack_node)

    print(f"  Node 结果: {result1}")
    print(f"  StackNode 结果: {result2}")

    print("\n" + "=" * 60)
    print("✓ HIR dump 完成")
    print("=" * 60)
    print("\n请检查日志文件：")
    print(f"  PYTHONJITLOGFILE={os.environ.get('PYTHONJITLOGFILE', '/tmp/jit.log')}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
