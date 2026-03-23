#!/bin/bash
# Copyright (c) Meta Platforms, Inc. and affiliates.

# LTO Build Integration Test Script
# Tests that LTO builds complete successfully and produce correct binaries

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "================================"
echo "CinderX LTO Build Integration Test"
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

TEST_FAILED=0

# Test 1: Check for required tools
echo ""
echo "Test 1: Checking for LTO toolchain tools..."
if command -v llvm-ar &> /dev/null || command -v gcc-ar &> /dev/null; then
    echo -e "${GREEN}✓${NC} LTO archiver found"
else
    echo -e "${RED}✗${NC} No LTO archiver found (llvm-ar or gcc-ar)"
    TEST_FAILED=1
fi

# Test 2: Clean build directory
echo ""
echo "Test 2: Cleaning build directory..."
cd "${PROJECT_ROOT}"
rm -rf build/ *.so
echo -e "${GREEN}✓${NC} Build directory cleaned"

# Test 3: LTO Build
echo ""
echo "Test 3: Building with LTO (this may take a while)..."
if CINDERX_ENABLE_LTO=1 python setup.py build_ext --inplace 2>&1 | tee /tmp/lto_build.log; then
    echo -e "${GREEN}✓${NC} LTO build completed"
else
    echo -e "${RED}✗${NC} LTO build failed"
    echo "See /tmp/lto_build.log for details"
    TEST_FAILED=1
fi

# Test 4: Module import
echo ""
echo "Test 4: Testing module import..."
cd "${PROJECT_ROOT}"
if python -c "import cinderx; print('OK')" 2>&1; then
    echo -e "${GREEN}✓${NC} Module imports successfully"
else
    echo -e "${RED}✗${NC} Module import failed"
    TEST_FAILED=1
fi

# Test 5: Symbol table check
echo ""
echo "Test 5: Checking JITRT symbol table..."
SO_FILE=$(find . -name "_cinderx*.so" | head -1)
if [ -f "$SO_FILE" ]; then
    if nm -C "$SO_FILE" | grep -q "JITRT_ReCompileCached"; then
        echo -e "${GREEN}✓${NC} JITRT_ReCompileCached found in symbols"
    else
        echo -e "${RED}✗${NC} JITRT_ReCompileCached not found"
        TEST_FAILED=1
    fi
    
    # Check for inlined versions (should not exist)
    if nm -C "$SO_FILE" | grep -E "JITRT_.*\.(isra|part)" | head -5; then
        echo -e "${RED}✗${NC} Found inlined JITRT functions (may indicate LTO issues)"
        TEST_FAILED=1
    else
        echo -e "${GREEN}✓${NC} No inlined JITRT functions detected"
    fi
else
    echo -e "${RED}✗${NC} _cinderx.so not found"
    TEST_FAILED=1
fi

# Test 6: Run regression tests
echo ""
echo "Test 6: Running LTO regression tests..."
if python -m pytest cinderx/PythonLib/test_cinderx/test_lto_regression.py -v 2>&1 | tail -20; then
    echo -e "${GREEN}✓${NC} Regression tests passed"
else
    echo -e "${RED}✗${NC} Some regression tests failed"
    TEST_FAILED=1
fi

# Summary
echo ""
echo "================================"
if [ $TEST_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    echo "================================"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    echo "================================"
    exit 1
fi
