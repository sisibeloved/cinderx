#!/usr/bin/env python3
"""
Recursive generator benchmark for CinderX JIT optimization
"""
import sys
from pathlib import Path

class Node:
    """Tree node with recursive generator iterator."""

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
    """Build balanced binary tree."""
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return Node(
        mid, build_tree(depth - 1), build_tree(depth - 1)
    )


def main():
    print("Starting benchmark...")
    tree = build_tree(5)

    # Run multiple iterations to trigger JIT
    for i in range(10):
        result = list(tree)
        print(f"Iteration {i+1}: {len(result)} nodes")

    print("Benchmark complete")


if __name__ == "__main__":
    main()
