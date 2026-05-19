#!/usr/bin/env bash
# Marp 形式の発表資料から HTML と PDF を生成する。
#
# Usage:
#   build-marp.sh <markdown-file> [html|pdf|all]
#
# 第 2 引数を省略すると HTML と PDF の両方を生成する。
# 第 2 引数に html / pdf を指定すると片方のみ生成する。

set -euo pipefail

TARGET="${1:?usage: build-marp.sh <markdown-file> [html|pdf|all]}"
MODE="${2:-all}"

if [[ ! -f "$TARGET" ]]; then
  echo "error: file not found: $TARGET" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$TARGET")" && pwd)"
BASE="$(basename "$TARGET" .md)"

# Markdown ファイルと同じディレクトリに出力 (html / pdf) を置くため cd する
cd "$DIR"

case "$MODE" in
  html)
    npx -y @marp-team/marp-cli@latest "$BASE.md" --html --allow-local-files
    ;;
  pdf)
    npx -y @marp-team/marp-cli@latest "$BASE.md" --pdf --allow-local-files
    ;;
  all)
    npx -y @marp-team/marp-cli@latest "$BASE.md" --html --pdf --allow-local-files
    ;;
  *)
    echo "error: unknown mode: $MODE (expected: html / pdf / all)" >&2
    exit 1
    ;;
esac
