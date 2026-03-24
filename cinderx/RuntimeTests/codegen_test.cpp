// Copyright (c) Meta Platforms, Inc. and affiliates.

#include <gtest/gtest.h>

#include "cinderx/Jit/codegen/arch.h"
#include "cinderx/Jit/codegen/frame_asm.h"
#include "cinderx/RuntimeTests/fixtures.h"

using namespace jit::codegen;

namespace jit::codegen {

class CodegenTest : public RuntimeTest {};

TEST_F(CodegenTest, TestPhyRegisterSet) {
  auto set = PhyRegisterSet(2) | PhyRegisterSet(3) | PhyRegisterSet(5);

  ASSERT_EQ(set.Empty(), false);
  ASSERT_EQ(set.count(), 3);
  ASSERT_EQ(set.GetFirst(), 2);
  ASSERT_EQ(set.GetLast(), 5);
  ASSERT_EQ(set.Has(3), true);

  set.RemoveFirst();

  ASSERT_EQ(set.Empty(), false);
  ASSERT_EQ(set.count(), 2);
  ASSERT_EQ(set.GetFirst(), 3);
  ASSERT_EQ(set.GetLast(), 5);
  ASSERT_EQ(set.Has(3), true);

  set.RemoveLast();

  ASSERT_EQ(set.Empty(), false);
  ASSERT_EQ(set.count(), 1);
  ASSERT_EQ(set.GetFirst(), 3);
  ASSERT_EQ(set.GetLast(), 3);
  ASSERT_EQ(set.Has(3), true);

  set.RemoveFirst();

  ASSERT_EQ(set.Empty(), true);
  ASSERT_EQ(set.count(), 0);
  ASSERT_EQ(set.Has(3), false);
}

#if PY_VERSION_HEX >= 0x030C0000 && defined(CINDER_AARCH64)
TEST_F(CodegenTest, ThreadStateOffsetScannerHandlesKnownPattern) {
  const uint32_t code[] = {
      0xa9bf7bfd, // stp x29, x30, [sp, #-16]!
      0x910003fd, // mov x29, sp
      0xd53bd041, // mrs x1, tpidr_el0
      0x91010021, // add x1, x1, #0x40
      0x91400421, // add x1, x1, #0x1, lsl #12
      0xf9400020, // ldr x0, [x1]
  };
  EXPECT_EQ(getThreadStateOffsetFromAArch64Instrs(code, std::size(code)), 0x1040);
}

TEST_F(CodegenTest, ThreadStateOffsetScannerFallsBackOnUnknownPattern) {
  const uint32_t code[] = {
      0xa9bf7bfd, // stp x29, x30, [sp, #-16]!
      0x910003fd, // mov x29, sp
      0x90002540, // adrp x0, ...
      0x91020000, // add x0, x0, #0x80
      0xf9400008, // ldr x8, [x0]
      0xd63f0100, // blr x8
      0xf9400000, // ldr x0, [x0]
  };
  EXPECT_EQ(getThreadStateOffsetFromAArch64Instrs(code, std::size(code)), -1);
}
#endif

} // namespace jit::codegen
