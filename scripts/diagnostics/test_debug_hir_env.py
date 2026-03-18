import importlib.util
import pathlib
import unittest


def _load_module():
    path = (
        pathlib.Path(__file__).resolve().parent / "debug_hir_env.py"
    )
    spec = importlib.util.spec_from_file_location("debug_hir_env", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DebugHIREnvTests(unittest.TestCase):
    def test_build_setup_script_uses_debug_build_type(self) -> None:
        module = _load_module()
        script = module.build_setup_script(
            repo_root=pathlib.Path("/repo/cinderx"),
            venv_path=pathlib.Path("/tmp/cinderx-debug"),
            python_exe="python3.14",
        )
        self.assertIn("python3.14 -m venv /tmp/cinderx-debug", script)
        self.assertIn("CMAKE_BUILD_TYPE=Debug", script)
        self.assertIn("python -m pip install -e . --no-build-isolation", script)

    def test_build_mdp_hir_dump_script_targets_named_functions(self) -> None:
        module = _load_module()
        script = module.build_mdp_hir_dump_script(
            repo_root=pathlib.Path("/repo/cinderx"),
            pyperformance_root=pathlib.Path("/repo/pyperformance"),
            python_exe="/tmp/cinderx-debug/bin/python",
            targets=("applyHPChange", "getCritDist"),
        )
        self.assertIn("PYTHONJITDEBUG=1", script)
        self.assertIn("PYTHONJITDUMPFINALHIR=1", script)
        self.assertIn("/repo/pyperformance/pyperformance/data-files/benchmarks/bm_mdp/run_benchmark.py", script)
        self.assertIn("fun bm_mdp:applyHPChange {", script)
        self.assertIn("fun bm_mdp:getCritDist {", script)
        self.assertIn('wanted = {f"fun bm_mdp:{name} {{" for name in targets}', script)


if __name__ == "__main__":
    unittest.main()
