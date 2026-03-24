#!/bin/bash
# Smart build monitor - detect C++ compilation start

OUTPUT_FILE="/private/tmp/claude-501/-Users-luchen-Agents-Repo-OpenCode-cinderx/3307f30a-7a9e-4979-a117-e99dfb2c067d/tasks/blqb3n32a.output"

if [[ ! -f "$OUTPUT_FILE" ]]; then
    echo "❌ Build output file not found"
    exit 1
fi

LINES=$(wc -l < "$OUTPUT_FILE")

echo "=== CinderX LTO Build Progress ==="
echo "Time: $(date '+%H:%M:%S')"
echo "Output lines: $LINES"
echo ""

# Detect build stage
if grep -q "running build_ext" "$OUTPUT_FILE"; then
    echo "✅ Stage: C++ COMPILATION (LTO optimization happening)"

    # Count compiled files
    COMPILED=$(grep -c "Compiling" "$OUTPUT_FILE" 2>/dev/null || echo "0")
    echo "   Compiled files: $COMPILED"

    # Check for LTO-specific output
    if grep -q "flto" "$OUTPUT_FILE"; then
        echo "   ✅ LTO flags detected in build"
    fi

elif grep -q "Successfully tagged" "$OUTPUT_FILE"; then
    echo "✅ Stage: Wheel packaging (build complete)"
elif grep -q "running bdist_wheel" "$OUTPUT_FILE"; then
    if grep -q "running build_ext" "$OUTPUT_FILE"; then
        echo "✅ Stage: C++ COMPILATION (LTO optimization happening)"
    else
        echo "⏳ Stage: Python file preparation (C++ compilation not started yet)"
        PYTHON_FILES=$(grep -c "copying.*\.py" "$OUTPUT_FILE" 2>/dev/null || echo "0")
        echo "   Python files copied: $PYTHON_FILES"
    fi
else
    echo "⏳ Stage: Initialization"
fi

echo ""

# Check for errors
if grep -q -i "error\|failed" "$OUTPUT_FILE"; then
    echo "❌ ERRORS DETECTED:"
    grep -i "error\|failed" "$OUTPUT_FILE" | tail -5
else
    echo "✅ No errors detected"
fi

echo ""

# Show recent progress
echo "📋 Recent activity (last 10 lines):"
tail -10 "$OUTPUT_FILE"

echo ""

# Check wheel status
if ls dist/cinderx-*-linux_aarch64.whl 2>/dev/null; then
    echo "✅ WHEEL CREATED:"
    ls -lh dist/cinderx-*-linux_aarch64.whl

    # Check build time
    if grep -q "Build complete" "$OUTPUT_FILE"; then
        echo ""
        grep "Build complete" "$OUTPUT_FILE" | tail -1
    fi
else
    echo "⏳ Wheel not yet created"
    echo ""
    echo "💡 Tip: Single-threaded ARM64 build takes 15-30 minutes"
    echo "   Use: watch -n 60 bash scripts/bench/smart_monitor.sh"
fi
