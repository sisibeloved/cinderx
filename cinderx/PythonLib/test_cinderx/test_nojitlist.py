# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-strict

import tempfile
import unittest

import cinderx.jit
from cinderx.test_support import passUnless, skip_unless_jit


@skip_unless_jit("Tests nojit list behavior")
@passUnless(
    cinderx.jit.get_compile_after_n_calls() is None
    or cinderx.jit.get_compile_after_n_calls() == 0,
    "Expecting functions to compile on first call",
)
class NoJitListTest(unittest.TestCase):
    def test_append_nojit_list_and_get_nojit_list(self) -> None:
        def victim() -> None:
            pass

        entry = f"{victim.__module__}:{victim.__qualname__}".replace(
            "victim", "func"
        )
        cinderx.jit.append_nojit_list(entry)

        def func() -> None:
            pass

        entries = cinderx.jit.get_nojit_list()[0]
        self.assertIn(func.__module__, entries)
        self.assertIn(func.__qualname__, entries[func.__module__])

    def test_nojit_list_overrides_jit_list(self) -> None:
        def victim() -> int:
            return 1

        entry = f"{victim.__module__}:{victim.__qualname__}".replace(
            "victim", "func"
        )
        cinderx.jit.append_jit_list(entry)
        cinderx.jit.append_nojit_list(entry)

        def func() -> int:
            return 24

        self.assertEqual(func(), 24)
        self.assertFalse(cinderx.jit.is_jit_compiled(func))

    def test_read_nojit_list(self) -> None:
        def victim() -> None:
            pass

        entry = f"{victim.__module__}:{victim.__qualname__}".replace(
            "victim", "func"
        )
        with tempfile.NamedTemporaryFile("w+") as nojit_list_file:
            nojit_list_file.write(entry)
            nojit_list_file.flush()
            cinderx.jit.read_nojit_list(nojit_list_file.name)

        def func() -> None:
            pass

        func()
        self.assertFalse(cinderx.jit.is_jit_compiled(func))


if __name__ == "__main__":
    unittest.main()
