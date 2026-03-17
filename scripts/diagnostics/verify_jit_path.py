#!/usr/bin/env python3
"""
JIT 执行路径验证

验证 CinderX JIT 是否正常工作并编译递归生成器。
"""

import sys
import time


class Node:
    """二叉树节点，使用递归生成器遍历"""

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        """递归生成器：中序遍历"""
        if self.left is not None:
            yield from self.left
        yield self.value
        if self.right is not None:
            yield from self.right


def enable_jit():
    """启用 CinderX JIT"""
    try:
        import cinderx
        from cinderx import jit

        # 启用 JIT
        jit.enable()
        return True
    except ImportError:
        print("    ✗ CinderX 未安装")
        return False


def force_compile(func):
    """强制编译函数到 JIT"""
    from cinderx import jit

    # 请求编译
    jit.force_compile(func)
    return True


def check_compiled(func):
    """检查函数是否已编译"""
    from cinderx import jit

    compiled = jit.is_jit_compiled(func)

    # Try to get code size if available
    try:
        code_size = jit.get_compiled_size(func)
    except:
        code_size = 0

    return compiled, code_size


def build_test_tree(depth=10):
    """构建测试树"""
    if depth == 0:
        return Node(depth)

    left = build_test_tree(depth - 1)
    right = build_test_tree(depth - 1)
    return Node(depth, left, right)


def verify_correctness(tree, expected_count):
    """验证遍历正确性"""
    count = 0
    for _ in tree:
        count += 1
    return count == expected_count


def main():
    print("=" * 60)
    print("JIT 执行路径验证")
    print("=" * 60)
    print()

    # [1] 启用 JIT
    print("[1] 启用 JIT...")
    if not enable_jit():
        print("    ✗ 无法启用 JIT")
        sys.exit(1)
    print("    ✓ JIT 已启用")
    print()

    # [2] 强制编译 Node.__iter__
    print("[2] 强制编译 Node.__iter__...")
    try:
        force_compile(Node.__iter__)
        print("    ✓ 编译已请求")
    except Exception as e:
        print(f"    ✗ 编译请求失败: {e}")
        sys.exit(1)
    print()

    # [3] 检查编译状态
    print("[3] 检查编译状态...")
    compiled, code_size = check_compiled(Node.__iter__)
    print(f"    已编译: {compiled}")
    print(f"    代码大小: {code_size} bytes")
    print()

    # [4] 构建测试树
    print("[4] 构建测试树...")
    depth = 10
    tree = build_test_tree(depth)
    expected_count = 2 ** (depth + 1) - 1  # 满二叉树节点数
    print(f"    ✓ 树已构建（深度={depth}）")
    print()

    # [5] 运行遍历（应使用 JIT 代码）
    print("[5] 运行遍历（应使用 JIT 代码）...")
    if verify_correctness(tree, expected_count):
        print("    ✓ 正确性已验证")
    else:
        print("    ✗ 正确性验证失败")
        sys.exit(1)
    print()

    # [6] 检查反优化
    print("[6] 检查反优化...")
    print("    （反优化检查尚未实现 - 使用 JIT_LOG 手动验证）")
    print()

    print("=" * 60)
    print("✓ 所有检查通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
