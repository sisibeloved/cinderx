import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import cinderx.jit


@unittest.skipUnless(cinderx.jit.is_enabled(), "Tests functionality on cinderjit")
class MdpGetSuccessorsExperimentTests(unittest.TestCase):
    def test_miss_helper_reduces_get_successors_deopts(self) -> None:
        code = textwrap.dedent(
            """
            import importlib.util
            import json

            import cinderx.jit as jit
            import cinderjit

            spec = importlib.util.spec_from_file_location(
                "bm_mdp",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_mdp/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            badges = (1, 0, 0, 0)
            starfixed = mod.fixeddata_t(
                59, mod.stats_t(40, 44, 56, 50), 11, mod.NOMODS, 115
            )
            starhalf = mod.halfstate_t(
                starfixed, 59, 0, mod.NOMODS, mod.stats_t(40, 44, 56, 50)
            )
            charfixed = mod.fixeddata_t(
                63, mod.stats_t(39, 34, 46, 38), 26, badges, 65
            )
            charhalf = mod.halfstate_t(
                charfixed,
                63,
                0,
                mod.NOMODS,
                mod.applyBadgeBoosts(badges, mod.stats_t(39, 34, 46, 38)),
            )
            statep = (1, (charhalf, starhalf, 0), "Dig")

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            for _ in range(1000):
                mod.Battle().getSuccessors(statep)

            assert jit.force_compile(mod.Battle.getSuccessors)
            counts = cinderjit.get_function_hir_opcode_counts(mod.Battle.getSuccessors)
            jit.get_and_clear_runtime_stats()

            total = 0
            summary = None
            for _ in range(2000):
                result = mod.Battle().getSuccessors(statep)
                total += len(result)
                summary = [(repr(item[0]), item[1]) for item in result]

            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "Battle.getSuccessors"
            )
            print(counts.get("BinaryOp", 0))
            print(counts.get("CallStatic", 0))
            print(counts.get("DeoptPatchpoint", 0))
            print(deopt_count)
            print(json.dumps(summary))
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/mdp_get_successors.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc_baseline = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc_baseline.returncode,
                0,
                f"stdout:\n{proc_baseline.stdout}\nstderr:\n{proc_baseline.stderr}",
            )

            env_optimized = dict(os.environ)
            env_optimized["PYTHONJIT_ARM_MDP_GET_SUCCESSORS_MISS_HELPER"] = "1"
            proc_optimized = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env_optimized,
            )
            self.assertEqual(
                proc_optimized.returncode,
                0,
                f"stdout:\n{proc_optimized.stdout}\nstderr:\n{proc_optimized.stderr}",
            )

            baseline = [
                line.strip() for line in proc_baseline.stdout.splitlines() if line.strip()
            ]
            optimized = [
                line.strip() for line in proc_optimized.stdout.splitlines() if line.strip()
            ]
            self.assertEqual(len(baseline), 6, proc_baseline.stdout)
            self.assertEqual(len(optimized), 6, proc_optimized.stdout)

            b_binary_op = int(baseline[0])
            b_call_static = int(baseline[1])
            b_deopt_patchpoint = int(baseline[2])
            b_deopt = int(baseline[3])
            b_summary = baseline[4]
            b_total = int(baseline[5])

            o_binary_op = int(optimized[0])
            o_call_static = int(optimized[1])
            o_deopt_patchpoint = int(optimized[2])
            o_deopt = int(optimized[3])
            o_summary = optimized[4]
            o_total = int(optimized[5])

            self.assertGreater(b_binary_op, 0, proc_baseline.stdout)
            self.assertEqual(b_call_static, 0, proc_baseline.stdout)
            self.assertGreater(b_deopt_patchpoint, 0, proc_baseline.stdout)
            self.assertGreater(b_deopt, 0, proc_baseline.stdout)
            self.assertEqual(b_summary, o_summary, (proc_baseline.stdout, proc_optimized.stdout))
            self.assertEqual(b_total, o_total, (proc_baseline.stdout, proc_optimized.stdout))
            self.assertLess(o_binary_op, b_binary_op, (proc_baseline.stdout, proc_optimized.stdout))
            self.assertGreaterEqual(o_call_static, 1, proc_optimized.stdout)
            self.assertLess(o_deopt, b_deopt, (proc_baseline.stdout, proc_optimized.stdout))
            self.assertGreaterEqual(
                o_deopt_patchpoint, 0, (proc_baseline.stdout, proc_optimized.stdout)
            )
