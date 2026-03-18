#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shlex
import textwrap
from pathlib import Path


def build_setup_script(
    repo_root: Path,
    venv_path: Path,
    python_exe: str = "python3.14",
) -> str:
    return textwrap.dedent(
        f"""\
        cd {shlex.quote(str(repo_root))}

        {shlex.quote(python_exe)} -m venv {shlex.quote(str(venv_path))}
        source {shlex.quote(str(venv_path / "bin" / "activate"))}
        python -m pip install -U pip setuptools wheel

        CMAKE_BUILD_TYPE=Debug \\
        python -m pip install -e . --no-build-isolation
        """
    )


def build_mdp_hir_dump_script(
    repo_root: Path,
    pyperformance_root: Path,
    python_exe: str,
    targets: tuple[str, ...],
) -> str:
    target_patterns = ", ".join(f'"fun bm_mdp:{name} {{"' for name in targets)
    target_json = json.dumps(list(targets))
    return textwrap.dedent(
        f"""\
cd {shlex.quote(str(repo_root))}

PYTHONPATH=cinderx/PythonLib \\
PYTHONJITDEBUG=1 \\
PYTHONJITDUMPFINALHIR=1 \\
{shlex.quote(python_exe)} - <<'PY'
import json
import os
import pathlib
import subprocess
import textwrap

targets = json.loads({target_json!r})

script = textwrap.dedent(\"\"\"\
import importlib.util
import pathlib
import sys
import time
import types

pyperf = types.SimpleNamespace(perf_counter=time.perf_counter)
sys.modules['pyperf'] = pyperf

spec = importlib.util.spec_from_file_location('bm_mdp', pathlib.Path({str(pyperformance_root / "pyperformance/data-files/benchmarks/bm_mdp/run_benchmark.py")!r}))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

import cinderx
cinderx.init()
import cinderjit
cinderjit.enable()
cinderjit.compile_after_n_calls(1)

for _ in range(3):
    mod.bench_mdp(1)

call_args = {{
    'applyHPChange': (
        mod.halfstate_t(
            mod.fixeddata_t(59, mod.stats_t(40, 44, 56, 50), 11, mod.NOMODS, 115),
            59,
            0,
            mod.NOMODS,
            mod.stats_t(40, 44, 56, 50),
        ),
        0,
    ),
    'getCritDist': (10, mod.Fraction(1, 2), 1, 2, 3, 4, 5, True, 1),
}}

for name in {target_json!r}:
    fn = getattr(mod, name)
    cinderjit.force_compile(fn)
    fn(*call_args[name])
\"\"\")

proc = subprocess.run(
    [{python_exe!r}, "-c", script],
    cwd={str(repo_root)!r},
    env=dict(os.environ),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    check=False,
)
lines = proc.stdout.splitlines()
wanted = {{f"fun bm_mdp:{{name}} {{{{" for name in targets}}
for i, line in enumerate(lines):
    if line in wanted:
        print("=" * 20)
        print(line)
        for extra in lines[i + 1 : i + 51]:
            print(extra)
PY

# 目标函数头部形状示例：{target_patterns}
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit local debug HIR helper commands")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    setup_parser.add_argument("--venv", default="/tmp/cinderx-debug")
    setup_parser.add_argument("--python", dest="python_exe", default="python3.14")

    mdp_parser = subparsers.add_parser("mdp-hir")
    mdp_parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    mdp_parser.add_argument("--pyperformance-root", default="/Users/luchen/Repo/pyperformance")
    mdp_parser.add_argument("--python", dest="python_exe", default="/tmp/cinderx-debug/bin/python")
    mdp_parser.add_argument(
        "--targets",
        default="applyHPChange,getCritDist",
        help="Comma-separated bm_mdp function names",
    )

    args = parser.parse_args()
    repo_root = Path(args.repo_root)

    if args.cmd == "setup":
        print(
            build_setup_script(
                repo_root=repo_root,
                venv_path=Path(args.venv),
                python_exe=args.python_exe,
            )
        )
        return 0

    targets = tuple(name.strip() for name in args.targets.split(",") if name.strip())
    print(
        build_mdp_hir_dump_script(
            repo_root=repo_root,
            pyperformance_root=Path(args.pyperformance_root),
            python_exe=args.python_exe,
            targets=targets,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
