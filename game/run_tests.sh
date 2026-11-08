#!/usr/bin/env bash
# 在 Linux/macOS 上无头运行 GUT 单元测试。
# 用法：GODOT=/path/to/godot ./run_tests.sh
set -euo pipefail

cd "$(dirname "$0")"
GODOT="${GODOT:-godot}"

if ! command -v "$GODOT" >/dev/null 2>&1 && [ ! -x "$GODOT" ]; then
  echo "找不到 Godot 可执行文件：$GODOT（可通过 GODOT=/path/to/godot 指定）" >&2
  exit 1
fi

# 第一次运行先导入资源，生成 .godot/ 缓存（包括全局 class_name 索引）。
"$GODOT" --headless --path . --import >/dev/null 2>&1 || true

"$GODOT" --headless --path . -s addons/gut/gut_cmdln.gd -gconfig=.gutconfig.json -gexit
