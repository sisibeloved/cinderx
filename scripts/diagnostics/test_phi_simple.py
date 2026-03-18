#!/usr/bin/env python3
"""
简单测试脚本 - 验证 Phi 节点优化检测
"""
import sys
from pathlib import Path

# 添加 PythonLib 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "cinderx" / "PythonLib"))

class Node:
    """使用递归生成器迭代器的树节点。"""

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


def build_tree(depth):
    """构建平衡二叉树。"""
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return Node(
        mid, build_tree(depth - 1), build_tree(depth - 1)
    )


def main():
    print("开始测试...")
    tree = build_tree(5)  # 较小的树

    # 遍历一次以触发 JIT 编译
    result = list(tree)
    print(f"遍历结果: {len(result)} 个节点")
    print("测试完成")


if __name__ == "__main__":
    main()
