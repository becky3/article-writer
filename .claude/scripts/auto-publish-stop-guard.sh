#!/usr/bin/env bash
# /auto-publish-diary の finalize 未実行ガード（Stop hook）
#
# setup が作成する in-flight マーカーが残ったまま（= result.json 未書き込み = finalize 未到達）
# セッションが停止しようとしたとき、停止をブロックして finalize の実行を指示する。
# 記事生成（LLM ステップ）後に end_turn で打ち切られると決定論的な後続処理（投稿・PR・
# result.json）が丸ごと飛ぶ構造弱点への L2 ガード。
#
# 誤爆防止:
# - セッション自己識別: setup が記録したセッション ID（session-id ファイル）と一致する
#   セッションのみブロック対象。並行する開発セッションは構造的に対象外（二重 finalize 防止）
# - マーカー作成から 2 時間超は非ブロック（クラッシュ残骸が通常セッションを妨げないため）
# - ブロックは 1 実行あたり最大 2 回（カウンタは setup でリセット、result.json 書き込みで削除）
#
# マーカー・カウンタ・session-id のライフサイクルは scripts/write_auto_publish_result.py を参照。
set -u

# stdin(JSON) はセッション照合のフォールバック用に保持する（判定の主軸はファイル状態）
STDIN_JSON=$(cat 2>/dev/null || true)

# 親リポジトリを git から導出する（cwd が worktree 内でも親リポの .git を指す）。git 外なら何もしない
COMMON_DIR=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
if [ -z "$COMMON_DIR" ]; then
  exit 0
fi
PARENT_REPO=$(dirname "$COMMON_DIR")
STATE_DIR="$PARENT_REPO/.tmp/auto-publish-diary"
MARKER="$STATE_DIR/in-flight"
RESULT="$STATE_DIR/result.json"
COUNTER="$STATE_DIR/stop-block-count"
SESSION_FILE="$STATE_DIR/session-id"

# in-flight マーカーが無い（自動投稿の実行中でない）/ result.json 済み（終端到達済み）なら通常停止
if [ ! -f "$MARKER" ]; then
  exit 0
fi
if [ -f "$RESULT" ]; then
  exit 0
fi

# セッション自己識別: setup が記録したセッション ID と一致するセッションのみブロック対象。
# 記録が無い・照合材料が無い場合は fail-open（ブロックしない）
if [ ! -f "$SESSION_FILE" ]; then
  exit 0
fi
RECORDED_SID=$(tr -d '[:space:]' < "$SESSION_FILE")
if [ -z "$RECORDED_SID" ]; then
  exit 0
fi
HOOK_SID="${CLAUDE_CODE_SESSION_ID:-}"
if [ "$HOOK_SID" != "$RECORDED_SID" ]; then
  # env に無い環境向けフォールバック: hook stdin JSON の session_id と照合する
  STDIN_SID=$(printf '%s' "$STDIN_JSON" \
    | grep -oE '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
  if [ "$STDIN_SID" != "$RECORDED_SID" ]; then
    exit 0
  fi
fi

# マーカーが古すぎる場合はブロックしない
NOW=$(date +%s)
MARKER_MTIME=$(stat -c %Y "$MARKER" 2>/dev/null) || {
  # fail-open（ガード無効化）で通常停止に倒すが、黙って無効化すると診断できないため痕跡を残す
  echo "auto-publish-stop-guard: stat failed for $MARKER (guard skipped)" >&2
  exit 0
}
MAX_AGE_SECONDS=7200
if [ $((NOW - MARKER_MTIME)) -gt "$MAX_AGE_SECONDS" ]; then
  exit 0
fi

# ブロック回数の上限（無限ループ防止）
COUNT=""
if [ -f "$COUNTER" ]; then
  COUNT=$(tr -cd '0-9' < "$COUNTER")
fi
COUNT=${COUNT:-0}
MAX_BLOCKS=2
if [ "$COUNT" -ge "$MAX_BLOCKS" ]; then
  exit 0
fi
echo $((COUNT + 1)) > "$COUNTER" 2>/dev/null || true

cat <<'JSON'
{"decision": "block", "reason": "/auto-publish-diary の finalize が未実行です（in-flight マーカーあり・result.json 不在）。.claude/skills/auto-publish-diary/SKILL.md のステップ 2〜3 に従い、worktree 内の生成記事の相対パスを特定し、親リポジトリを cwd にして `python \"$WORKTREE/scripts/auto_publish_diary.py\" finalize --worktree \"$WORKTREE\" --article-path <記事相対パス>` を実行してください。記事が未生成でも finalize を実行すれば failed_phase=write の result.json が書かれて正常に終端します。result.json の書き込みを確認してから終了してください。"}
JSON
exit 0
