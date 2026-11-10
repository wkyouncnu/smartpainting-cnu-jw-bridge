#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# pdf_sync.sh — README.md(또는 그 그림·조판 도구)가 PDF 보다 새로우면 PDF 를 다시 뽑는다.
#
#   bash tools/docs/pdf_sync.sh            # 검사 후 필요하면 갱신
#   bash tools/docs/pdf_sync.sh --check    # 검사만. 갱신이 필요하면 종료코드 1
#   bash tools/docs/pdf_sync.sh --force    # 무조건 다시 뽑기
#
#   대상 목록: tools/docs/pdf_targets.txt  (한 줄에 "원본.md  출력.pdf")
#
#   다시 뽑는 조건 (하나라도 해당하면):
#     (1) PDF 가 없다            (2) MD 가 PDF 보다 새롭다
#     (3) MD 가 싣는 그림 ![](...) / <img src> 중 하나가 PDF 보다 새롭다
#     (4) 조판 도구(템플릿·md2pdf·marked)가 PDF 보다 새롭다
#   (3)(4) 를 보는 이유: 그림만 바꾸면 MD 는 그대로라 PDF 가 조용히 옛 그림을 품는다.
#
#   ⚠ git clone 직후에는 모든 파일의 수정 시각이 clone 시각이라 비교가 무의미하다.
#     그래서 git 저장소 안이면 '마지막 커밋 시각' 이 아니라 파일 시각을 그대로 보되,
#     GitHub Actions 에서는 --force 로 돌린다 (워크플로 참조).
#
#   이 스크립트를 부르는 곳 (= 연동):
#     · .githooks/pre-commit          커밋할 때 (git config core.hooksPath .githooks)
#     · .github/workflows/pdf.yml     GitHub 에 push 될 때 / 웹에서 README 를 고쳤을 때
#     · .claude/settings.json Stop 훅 Claude Code 세션이 끝날 때
# ---------------------------------------------------------------------------
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MODE="${1:-}"
TOOLS="pdf-template.html md2pdf.sh marked.min.js"

why_stale() {
  local md="$1" pdf="$2" t f p dir
  [ -f "$pdf" ] || { echo "PDF 없음"; return; }
  [ "$md" -nt "$pdf" ] && { echo "MD 수정됨"; return; }
  for t in $TOOLS; do
    [ "$HERE/$t" -nt "$pdf" ] && { echo "조판도구 $t"; return; }
  done
  dir="$(dirname "$md")"
  for p in $(sed -n 's/.*!\[[^]]*\](\([^) ]*\).*/\1/p; s/.*<img[^>]*src="\([^"]*\)".*/\1/p' "$md" \
             | sed 's/[#?].*$//' | sort -u); do
    case "$p" in http*|data:*|'') continue ;; esac
    f="$dir/$p"
    [ -f "$f" ] && [ "$f" -nt "$pdf" ] && { echo "그림 $(basename "$p")"; return; }
  done
  echo ""
}

n=0; fail=0
while read -r md pdf; do
  case "$md" in ''|\#*) continue ;; esac
  [ -f "$ROOT/$md" ] || { echo "pdf_sync: $md 없음 — 건너뜀"; continue; }
  if [ "$MODE" = "--force" ]; then r="강제"; else r="$(why_stale "$ROOT/$md" "$ROOT/$pdf")"; fi
  [ -z "$r" ] && continue
  n=$((n+1))
  echo "pdf_sync: $pdf 갱신 필요 ($r)"
  [ "$MODE" = "--check" ] && continue
  (cd "$ROOT" && bash "$HERE/md2pdf.sh" "$md" -o "$pdf") || fail=$((fail+1))
done < "$HERE/pdf_targets.txt"

[ "$n" -eq 0 ] && echo "pdf_sync: PDF 최신 상태"
[ "$MODE" = "--check" ] && [ "$n" -gt 0 ] && exit 1
[ "$fail" -gt 0 ] && exit 1
exit 0
