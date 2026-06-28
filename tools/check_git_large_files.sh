#!/usr/bin/env bash
set -e

echo "Checking tracked large model files..."

FOUND=$(git ls-files | grep -Ei '\.(safetensors|bin|pt|pth|onnx|rknn|rkllm)$' || true)

if [ -n "$FOUND" ]; then
    echo "ERROR: Large model files are tracked by Git:"
    echo "$FOUND"
    exit 1
fi

echo "OK: no large model files are tracked by Git."
