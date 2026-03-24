#!/bin/bash
# Monitor CinderX LTO build progress

OUTPUT_FILE="/private/tmp/claude-501/-Users-luchen-Agents-Repo-OpenCode-cinderx/3307f30a-7a9e-4979-a117-e99dfb2c067d/tasks/blqb3n32a.output"

if [[ ! -f "$OUTPUT_FILE" ]]; then
    echo "❌ Build output file not found: $OUTPUT_FILE"
    exit 1
fi

echo "=== CinderX LTO Build Monitor ==="
echo "Output file: $OUTPUT_FILE"
echo ""

# File size
SIZE=$(wc -l < "$OUTPUT_FILE")
echo "📄 Output lines: $SIZE"

# Build stage
echo ""
echo "🔍 Build Stage:"
if grep -q "Installing build dependencies" "$OUTPUT_FILE"; then
    echo "  ✅ Dependencies installed"
fi
if grep -q "Building wheel" "$OUTPUT_FILE"; then
    echo "  ✅ Wheel build started"
fi
if grep -q "running build_ext" "$OUTPUT_FILE"; then
    echo "  ⏳ C++ compilation in progress..."
fi
if grep -q "Build complete" "$OUTPUT_FILE"; then
    echo "  ✅ Build completed!"
fi

# Check for errors
echo ""
echo "⚠️  Errors:"
ERRORS=$(grep -i "error\|failed" "$OUTPUT_FILE" | grep -v "errors.h" | wc -l)
if [[ $ERRORS -gt 0 ]]; then
    echo "  ❌ Found $ERRORS error(s)"
    echo ""
    echo "Last errors:"
    grep -i "error\|failed" "$OUTPUT_FILE" | grep -v "errors.h" | tail -5
else
    echo "  ✅ No errors detected"
fi

# Latest output
echo ""
echo "📋 Latest 20 lines:"
tail -20 "$OUTPUT_FILE"

# Check for wheel
echo ""
echo "📦 Wheel Status:"
if ls dist/cinderx-*-linux_aarch64.whl 2>/dev/null; then
    echo "  ✅ Wheel created:"
    ls -lh dist/cinderx-*-linux_aarch64.whl
else
    echo "  ⏳ Wheel not yet created"
fi
