import unittest

import benchmark_hotspot_scan as scan


SAMPLE_DISASM = """
   14:    58001ad0    ldr x16, 0x370
   1c:    d63f0200    blr x16
   20:    540000e0    b.eq 0x4c
   24:    b40000c3    cbz x3, 0x2c
   28:    b50000c3    cbnz x3, 0x2c
   2c:    36000043    tbz w3, #0, 0x34
   30:    37000043    tbnz w3, #0, 0x38
   34:    f2b4090a    movk x10, #0xa048, lsl #16
   38:    94000001    bl 0x40
   3c:    d65f03c0    ret
   40:    d2800009    mov x9, #0x0
   44:    f2a00029    movk x9, #0x1, lsl #16
   48:    f2c00049    movk x9, #0x2, lsl #32
   4c:    d63f0120    blr x9
   50:    36f80040    tbz w0, #31, 0x58
   54:    10000061    adr x1, 0x60
   58:    94000001    bl 0x5c
   5c:    b4000040    cbz x0, 0x64
   60:    58000090    ldr x16, 0x70
   64:    d63f0200    blr x16
   68:    580000b0    ldr x16, 0x78
   6c:    d61f0200    br x16
"""

OBJDISASM_SAMPLE = """
0000000000001000 <<invalid>:Packet.append_to>:
    1000:    58001ad0    ldr x16, 0x370
    1004:    d63f0200    blr x16

0000000000001100 <<invalid>:HandlerTask.fn>:
    1100:    58001ad0    ldr x16, 0x470
    1104:    d63f0200    blr x16
"""


class BenchmarkHotspotScanTests(unittest.TestCase):
    def test_count_instruction_mix_extracts_mnemonics(self) -> None:
        mix = scan.count_instruction_mix(SAMPLE_DISASM)
        self.assertEqual(mix["ldr"], 3)
        self.assertEqual(mix["blr"], 3)
        self.assertEqual(mix["movk"], 3)
        self.assertEqual(mix["ret"], 1)

    def test_count_aarch64_patterns_detects_literal_call_pairs(self) -> None:
        patterns = scan.count_aarch64_patterns(SAMPLE_DISASM)
        self.assertEqual(patterns["ldr_literal"], 3)
        self.assertEqual(patterns["blr"], 3)
        self.assertEqual(patterns["ldr_literal_blr_pair"], 2)
        self.assertEqual(patterns["ldr_literal_br_pair"], 1)
        self.assertEqual(patterns["b_cond"], 1)
        self.assertEqual(patterns["cbz"], 2)
        self.assertEqual(patterns["cbnz"], 1)
        self.assertEqual(patterns["tbz"], 2)
        self.assertEqual(patterns["tbnz"], 1)
        self.assertEqual(patterns["movk"], 3)
        self.assertEqual(patterns["bl"], 2)
        self.assertEqual(patterns["post_call_branch_check"], 3)
        self.assertEqual(patterns["post_call_tbz_w0_signbit"], 1)
        self.assertEqual(patterns["adr_bl_pair"], 1)
        self.assertEqual(patterns["guard_then_literal_blr"], 1)
        self.assertEqual(patterns["movk_heavy_call_window"], 1)

    def test_suggestions_flag_attr_and_call_heavy_bench(self) -> None:
        suggestions = scan.suggest_optimization_points(
            "nbody",
            instruction_mix={"movk": 20},
            pattern_counts={"ldr_literal_blr_pair": 12},
            hir_totals={"LoadAttrCached": 8, "Decref": 10, "VectorCall": 0},
        )
        text = "\n".join(suggestions)
        self.assertIn("literal-pool indirect calls", text)
        self.assertIn("attribute-cache traffic", text)
        self.assertIn("refcount/deopt scaffolding", text)

    def test_split_objdump_functions_extracts_symbols(self) -> None:
        funcs = scan.split_objdump_functions(OBJDISASM_SAMPLE)
        self.assertEqual(len(funcs), 2)
        self.assertEqual(funcs[0]["normalized_symbol"], "Packet.append_to")
        self.assertEqual(funcs[1]["normalized_symbol"], "HandlerTask.fn")

    def test_match_objdump_function_matches_qualname(self) -> None:
        funcs = scan.split_objdump_functions(OBJDISASM_SAMPLE)
        match = scan.match_objdump_function(
            "HandlerTask.fn",
            "/tmp/richards_queue_dispatch_case.py",
            funcs,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["normalized_symbol"], "HandlerTask.fn")

    def test_extract_interesting_windows_finds_motifs(self) -> None:
        windows = scan.extract_interesting_windows(SAMPLE_DISASM, limit=10)
        kinds = [window["kind"] for window in windows]
        self.assertIn("ldr_literal_blr_pair", kinds)
        self.assertIn("post_call_branch_check", kinds)
        self.assertIn("movk_heavy_call_window", kinds)
        self.assertTrue(all(window["phase"] in {"entry", "body"} for window in windows))

    def test_filter_nonzero_items_extracts_not_negative_sources(self) -> None:
        filtered = scan.filter_nonzero_items(
            {"StoreAttrCached": 4, "Compare": 2, "VectorCall": 9},
            scan.NOT_NEGATIVE_SOURCE_OPS,
        )
        self.assertEqual(filtered, {"Compare": 2, "StoreAttrCached": 4})


if __name__ == "__main__":
    unittest.main()
