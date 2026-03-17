#!/usr/bin/env python3
"""
对生成器执行的各个阶段进行性能分析，以识别瓶颈。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))


class ProfiledNode:
    """带有阶段计时插桩的节点。"""

    # 类级别计时计数器
    frame_create_time = 0.0
    yield_from_delegate_time = 0.0
    yield_value_time = 0.0
    frame_cleanup_time = 0.0
    call_count = 0

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        # 测量帧创建（每次调用仅第一次）
        start_frame = time.perf_counter()
        ProfiledNode.call_count += 1
        ProfiledNode.frame_create_time += time.perf_counter() - start_frame

        try:
            # 测量 yield-from 委托
            if self.left:
                start_delegate = time.perf_counter()
                for v in self.left:
                    ProfiledNode.yield_from_delegate_time += time.perf_counter() - start_delegate

                    # 测量值 yield
                    start_yield = time.perf_counter()
                    yield v
                    ProfiledNode.yield_value_time += time.perf_counter() - start_yield

                    start_delegate = time.perf_counter()

            # 测量自身值的 yield
            start_yield = time.perf_counter()
            yield self.value
            ProfiledNode.yield_value_time += time.perf_counter() - start_yield

            # 测量 yield-from 委托（右子树）
            if self.right:
                start_delegate = time.perf_counter()
                for v in self.right:
                    ProfiledNode.yield_from_delegate_time += time.perf_counter() - start_delegate

                    start_yield = time.perf_counter()
                    yield v
                    ProfiledNode.yield_value_time += time.perf_counter() - start_yield

                    start_delegate = time.perf_counter()

        finally:
            # 测量清理
            start_cleanup = time.perf_counter()
            pass
            ProfiledNode.frame_cleanup_time += time.perf_counter() - start_cleanup

    @classmethod
    def reset_stats(cls):
        cls.frame_create_time = 0.0
        cls.yield_from_delegate_time = 0.0
        cls.yield_value_time = 0.0
        cls.frame_cleanup_time = 0.0
        cls.call_count = 0

    @classmethod
    def print_stats(cls):
        total = (cls.frame_create_time + cls.yield_from_delegate_time +
                 cls.yield_value_time + cls.frame_cleanup_time)

        print(f"\n阶段计时分析：")
        print(f"  总测量时间: {total*1000:.3f}ms")
        print(f"  帧创建:      {cls.frame_create_time*1000:.3f}ms ({cls.frame_create_time/total*100:.1f}%)")
        print(f"  Yield-from 委托: {cls.yield_from_delegate_time*1000:.3f}ms ({cls.yield_from_delegate_time/total*100:.1f}%)")
        print(f"  值 yield:         {cls.yield_value_time*1000:.3f}ms ({cls.yield_value_time/total*100:.1f}%)")
        print(f"  帧清理:       {cls.frame_cleanup_time*1000:.3f}ms ({cls.frame_cleanup_time/total*100:.1f}%)")
        print(f"  调用次数:          {cls.call_count}")


def build_profiled_tree(depth):
    """构建分析树。"""
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return ProfiledNode(
        mid,
        build_profiled_tree(depth - 1),
        build_profiled_tree(depth - 1)
    )


def main():
    print("=" * 60)
    print("生成器阶段性能分析")
    print("=" * 60)

    depth = 15

    # 构建并遍历分析树
    print(f"\n构建树（深度={depth}）...")
    tree = build_profiled_tree(depth)

    print("遍历树...")
    ProfiledNode.reset_stats()

    s = 0
    for v in tree:
        s += v

    print(f"总和: {s}")
    ProfiledNode.print_stats()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
