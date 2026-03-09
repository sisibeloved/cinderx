import unittest

import jit_microcases_scan as scan


class JitMicrocasesScanTests(unittest.TestCase):
    def test_microcases_are_registered(self) -> None:
        self.assertIn("nbody_attr_update", scan.MICROCASE_RUNNERS)
        self.assertIn("richards_attr_flow", scan.MICROCASE_RUNNERS)
        self.assertIn("richards_method_chain", scan.MICROCASE_RUNNERS)
        self.assertIn("richards_post_call_checks", scan.MICROCASE_RUNNERS)
        self.assertIn("richards_queue_dispatch", scan.MICROCASE_RUNNERS)
        self.assertIn("store_init_inline_values", scan.MICROCASE_RUNNERS)
        self.assertIn("store_overwrite_existing", scan.MICROCASE_RUNNERS)
        self.assertIn("store_overwrite_inline_values", scan.MICROCASE_RUNNERS)
        self.assertIn("spectral_helper_chain", scan.MICROCASE_RUNNERS)
        self.assertIn("fannkuch_list_ops", scan.MICROCASE_RUNNERS)

    def test_suggestions_flag_attr_and_call_heavy_case(self) -> None:
        suggestions = scan.suggest_microcase_points(
            "nbody_attr_update",
            instruction_mix={"movk": 18},
            pattern_counts={
                "ldr_literal_blr_pair": 10,
                "cbz": 4,
                "cbnz": 4,
                "tbz": 3,
                "tbnz": 3,
                "b_cond": 2,
            },
            hir_totals={"LoadAttrCached": 8, "StoreAttrCached": 6, "VectorCall": 0},
        )
        text = "\n".join(suggestions)
        self.assertIn("literal-load indirect calls", text)
        self.assertIn("constant materialization", text)
        self.assertIn("attribute cache traffic", text)
        self.assertIn("store-side code shape", text)

    def test_suggestions_flag_spectral_call_chain(self) -> None:
        suggestions = scan.suggest_microcase_points(
            "spectral_helper_chain",
            instruction_mix={"movk": 4},
            pattern_counts={"ldr_literal_blr_pair": 7},
            hir_totals={"VectorCall": 3, "CallMethod": 0},
        )
        text = "\n".join(suggestions)
        self.assertIn("Python-level call traffic", text)
        self.assertIn("local helper calls", text)

    def test_compute_case_metrics(self) -> None:
        metrics = scan.compute_case_metrics(
            instruction_mix={"movk": 20},
            pattern_counts={
                "bl": 10,
                "blr": 10,
                "ldr_literal_blr_pair": 8,
                "post_call_branch_check": 6,
                "movk_heavy_call_window": 4,
                "guard_then_literal_blr": 2,
            },
            hir_totals={
                "LoadAttrCached": 4,
                "StoreAttrCached": 3,
                "LoadMethodCached": 2,
                "CallMethod": 1,
                "VectorCall": 5,
                "Branch": 6,
                "CondBranch": 4,
                "Decref": 7,
                "XDecref": 3,
            },
            total_compiled_size=2048,
        )
        self.assertEqual(metrics["calls_total"], 20)
        self.assertEqual(metrics["attr_ops"], 10)
        self.assertEqual(metrics["call_ops"], 6)
        self.assertEqual(metrics["not_negative_source_total"], 3)
        self.assertAlmostEqual(metrics["indirect_call_ratio"], 0.4)
        self.assertAlmostEqual(metrics["post_call_branch_ratio"], 0.3)

    def test_summarize_case_rankings(self) -> None:
        rankings = scan.summarize_case_rankings(
            [
                {"case": "a", "derived_metrics": {"indirect_call_ratio": 0.5, "post_call_branch_ratio": 0.2, "post_call_tbz_w0_signbit_ratio": 0.1, "movk_per_call": 1.0, "guarded_helper_ratio": 0.1, "not_negative_source_total": 4, "attr_ops": 2, "call_ops": 1, "branch_ops": 3, "refcount_ops": 4}},
                {"case": "b", "derived_metrics": {"indirect_call_ratio": 0.7, "post_call_branch_ratio": 0.1, "post_call_tbz_w0_signbit_ratio": 0.3, "movk_per_call": 0.5, "guarded_helper_ratio": 0.4, "not_negative_source_total": 1, "attr_ops": 1, "call_ops": 5, "branch_ops": 2, "refcount_ops": 1}},
            ]
        )
        self.assertEqual(rankings["indirect_call_ratio"][0][0], "b")
        self.assertEqual(rankings["call_ops"][0][0], "b")
        self.assertEqual(rankings["refcount_ops"][0][0], "a")
        self.assertEqual(rankings["post_call_tbz_w0_signbit_ratio"][0][0], "b")

    def test_build_focus_groups_collects_store_status_functions(self) -> None:
        groups = scan.build_focus_groups(
            [
                {
                    "case": "richards_attr_flow",
                    "top_functions": [
                        {
                            "qualname": "HandlerTask.attr_flow",
                            "compiled_size": 2480,
                            "likely_not_negative_hir_sources": [["StoreAttrCached", 4]],
                            "objdump_pattern_counts": {
                                "post_call_tbz_w0_signbit": 7,
                                "post_call_branch_check": 8,
                                "ldr_literal_blr_pair": 39,
                                "movk_heavy_call_window": 1,
                            },
                            "objdump_interesting_windows": [
                                {"kind": "post_call_tbz_w0_signbit", "phase": "body", "snippet": "tbz"}
                            ],
                        },
                        {
                            "qualname": "run",
                            "compiled_size": 2888,
                            "likely_not_negative_hir_sources": [],
                            "objdump_pattern_counts": {"post_call_tbz_w0_signbit": 0},
                            "objdump_interesting_windows": [],
                        },
                    ],
                }
            ]
        )
        entries = groups["store_status_helper"]
        self.assertEqual(entries[0]["qualname"], "HandlerTask.attr_flow")
        self.assertEqual(entries[0]["store_status_source_total"], 4)
        self.assertEqual(entries[0]["post_call_tbz_w0_signbit"], 7)

    def test_classify_store_shape(self) -> None:
        self.assertEqual(scan.classify_store_shape({"StoreAttrCached": 4}), "init_like")
        self.assertEqual(
            scan.classify_store_shape({"StoreAttrCached": 4, "LoadAttrCached": 2}),
            "update_like",
        )
        self.assertEqual(
            scan.classify_store_shape({"StoreAttrCached": 2, "CallMethod": 1}),
            "mixed_store_method",
        )


if __name__ == "__main__":
    unittest.main()
