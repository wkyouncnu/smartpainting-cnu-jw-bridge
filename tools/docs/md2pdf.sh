#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# md2pdf.sh — Markdown 을 A4 PDF 로 (GitHub README 와 같은 원본, 같은 그림)
#
#   bash tools/docs/md2pdf.sh README.md                # → README.pdf (같은 폴더)
#   bash tools/docs/md2pdf.sh README.md -o out.pdf
#
#   MD → 임시 HTML (원본과 같은 폴더라 그림 상대경로 유지)
#      → Chrome/Chromium/Edge 헤드리스 --print-to-pdf → 임시 HTML 삭제
#
#   어디서 도는가: Windows Git Bash (Chrome/Edge), Ubuntu/WSL (google-chrome 또는
#   chromium), GitHub Actions (ubuntu-latest 에 Chrome 이 깔려 있다).
#   인터넷 불필요 — marked.min.js 를 함께 넣어 두었다.
#   (원형: 캡스톤디자인 강의 볼트의 _tools/md2pdf.sh)
# ---------------------------------------------------------------------------
set -u

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPL="$TOOLS/pdf-template.html"
MARKED="$TOOLS/marked.min.js"

find_chrome() {
  [ -n "${CHROME:-}" ] && [ -x "$CHROME" ] && { echo "$CHROME"; return; }
  for c in "/c/Program Files/Google/Chrome/Application/chrome.exe" \
           "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
           "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
           "/c/Program Files/Microsoft/Edge/Application/msedge.exe"; do
    [ -f "$c" ] && { echo "$c"; return; }
  done
  for c in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge; do
    command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return; }
  done
}

CHROME_BIN="$(find_chrome)"
[ -z "$CHROME_BIN" ] && { echo "오류: Chrome / Chromium / Edge 를 찾을 수 없습니다 (CHROME=경로 로 지정 가능)"; exit 1; }
[ -f "$TPL" ]    || { echo "오류: $TPL 없음"; exit 1; }
[ -f "$MARKED" ] || { echo "오류: $MARKED 없음"; exit 1; }
[ $# -eq 0 ]     && { echo "사용법: bash tools/docs/md2pdf.sh <파일.md> [-o 출력.pdf]"; exit 1; }

md="$1"; shift
pdf=""
[ "${1:-}" = "-o" ] && pdf="$2"
[ -f "$md" ] || { echo "오류: $md 없음"; exit 1; }

dir="$(cd "$(dirname "$md")" && pwd)"
base="$(basename "$md" .md)"
[ -z "$pdf" ] && pdf="$dir/$base.pdf"
case "$pdf" in /*|?:*) ;; *) pdf="$(pwd)/$pdf" ;; esac
tmp="$dir/.md2pdf_$$.html"
trap 'rm -f "$tmp"' EXIT INT TERM

n_md=$(grep -n '<!--MDCONTENT-->' "$TPL" | head -1 | cut -d: -f1)
n_js=$(grep -n '<!--MARKEDJS-->'  "$TPL" | head -1 | cut -d: -f1)
{
  sed -n "1,$((n_md-1))p" "$TPL"
  sed 's|</script|<\/script|g' "$md"
  sed -n "$((n_md+1)),$((n_js-1))p" "$TPL"
  cat "$MARKED"
  sed -n "$((n_js+1)),\$p" "$TPL"
} > "$tmp"

# Windows 의 chrome.exe 는 POSIX 경로를 모른다 → cygpath 로 변환
if command -v cygpath >/dev/null 2>&1; then
  out_arg="$(cygpath -w "$pdf")"; url="file:///$(cygpath -m "$tmp")"
else
  out_arg="$pdf"; url="file://$tmp"
fi

before=0; [ -f "$pdf" ] && before=$(stat -c%Y "$pdf")
for attempt in 1 2 3; do
  "$CHROME_BIN" --headless --disable-gpu --no-sandbox --hide-scrollbars \
      --no-pdf-header-footer --run-all-compositor-stages-before-draw \
      --virtual-time-budget=15000 --allow-file-access-from-files \
      --print-to-pdf="$out_arg" "$url" >/dev/null 2>&1
  after=0; [ -f "$pdf" ] && after=$(stat -c%Y "$pdf")
  # 같은 초 안에 다시 뽑을 수도 있으므로 >= 가 아니라 크기·시각 둘 다 본다
  if [ -s "$pdf" ] && { [ "$after" -gt "$before" ] || [ "$before" -eq 0 ]; }; then
    printf "  [OK] %s  %s KB\n" "${pdf#$(pwd)/}" "$(( $(stat -c%s "$pdf") / 1024 ))"
    exit 0
  fi
  [ $attempt -lt 3 ] && sleep 2
done
echo "  [실패] $pdf — 갱신되지 않음 (PDF 뷰어가 파일을 열고 있으면 닫고 다시 실행)"
exit 1
