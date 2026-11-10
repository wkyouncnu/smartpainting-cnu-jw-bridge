#!/usr/bin/env bash
# =============================================================================
#  install.sh — 한 번에 설치 (Ubuntu 24.04 / WSL2)
#
#    cd ~/ws/smartpainting-sim-handover
#    bash install.sh
#
#  하는 일 (순서대로, 단계마다 [n/7] 로 표시):
#    1. 환경 확인    — Ubuntu 24.04 인지, 인터넷이 되는지
#    2. 로케일       — UTF-8
#    3. ROS2 저장소  — ros2-apt-source 패키지 설치
#    4. 패키지 설치  — ROS2 Jazzy + Gazebo Harmonic + 브리지 등 (약 3~4 GB, 10~30분)
#    5. rosdep       — 의존성 데이터베이스
#    6. 빌드         — colcon build
#    7. ~/.bashrc    — 터미널을 열 때마다 자동으로 source
#
#  여러 번 실행해도 안전하다 (이미 된 단계는 금방 지나간다).
#  실패하면 어느 단계에서 왜 멈췄는지 찍고, 전체 기록은 ~/sp_install.log 에 남는다.
#  해결 방법: README.md 의 "문제 해결" 절.
#
#  옵션
#    --system-only   1~5단계만 (패키지 설치)
#    --build-only    6~7단계만 (이미 ROS 가 깔려 있을 때)
# =============================================================================
set -Eeuo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$HOME/sp_install.log"
ROS_DISTRO_WANT=jazzy
DO_SYSTEM=1; DO_BUILD=1
case "${1:-}" in
  --system-only) DO_BUILD=0 ;;
  --build-only)  DO_SYSTEM=0 ;;
  "" ) ;;
  *) echo "알 수 없는 옵션: $1  (쓸 수 있는 것: --system-only / --build-only)"; exit 2 ;;
esac

# ---------- 출력 도우미 ----------
G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; B=$'\e[1m'; N=$'\e[0m'
STEP="시작 전"
step() { STEP="$1"; echo; echo "${B}==== $1 ====${N}"; echo "==== $1 ====" >> "$LOG"; }
ok()   { echo "  ${G}[OK]${N} $*"; }
warn() { echo "  ${Y}[주의]${N} $*"; }
run()  { echo "  \$ $*" >> "$LOG"; "$@" >> "$LOG" 2>&1; }

on_error() {
  local code=$?
  echo
  echo "${R}${B}[실패] 단계: ${STEP}  (종료 코드 ${code})${N}"
  echo "${R}마지막 기록 15줄 (~/sp_install.log):${N}"
  tail -n 15 "$LOG" | sed 's/^/    /'
  echo
  echo "  해결 방법 → README.md 의 '문제 해결' 절에서 이 단계 이름을 찾으세요."
  echo "  고친 뒤 ${B}bash install.sh${N} 를 다시 실행하면 이어서 진행됩니다."
  exit "$code"
}
trap on_error ERR

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

echo "${B}스마트페인팅 시뮬레이션 + CNU↔JW 위치 브리지 설치${N}"
echo "  저장소: $REPO"
echo "  기록  : $LOG"
: > "$LOG"

if [ "$DO_SYSTEM" -eq 1 ]; then
  # ---------------------------------------------------------------- 1
  step "[1/7] 환경 확인"
  . /etc/os-release
  if [ "${VERSION_CODENAME:-}" != "noble" ]; then
    echo "  ${R}Ubuntu 24.04 (noble) 이 아닙니다: ${PRETTY_NAME:-?}${N}"
    echo "  ROS2 Jazzy 는 Ubuntu 24.04 에서만 apt 로 설치됩니다."
    echo "  PowerShell 에서:  wsl --install -d Ubuntu-24.04"
    false
  fi
  ok "$PRETTY_NAME"
  if grep -qi microsoft /proc/version; then ok "WSL 에서 실행 중"; else ok "일반 Ubuntu"; fi
  if ! curl -sSfI --max-time 10 http://packages.ros.org >/dev/null 2>&1; then
    echo "  ${R}packages.ros.org 에 접속할 수 없습니다 (인터넷 / 프록시 / DNS 확인)${N}"
    false
  fi
  ok "인터넷 연결"
  [ -n "$SUDO" ] && { echo "  관리자 암호를 물으면 Ubuntu 사용자 암호를 입력하세요 (화면에 안 보이는 게 정상)."; $SUDO -v; }

  # ---------------------------------------------------------------- 2
  step "[2/7] 로케일 (UTF-8)"
  run $SUDO apt-get update
  run $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y locales curl software-properties-common
  run $SUDO locale-gen en_US en_US.UTF-8
  run $SUDO update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
  ok "en_US.UTF-8"

  # ---------------------------------------------------------------- 3
  step "[3/7] ROS2 apt 저장소"
  run $SUDO add-apt-repository -y universe
  if dpkg -s ros2-apt-source >/dev/null 2>&1; then
    ok "이미 설치됨"
  else
    VER=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
          | grep -F '"tag_name"' | awk -F'"' '{print $4}')
    [ -n "$VER" ] || { echo "  GitHub API 응답 없음 (잠시 뒤 재시도)"; false; }
    run curl -fsSL -o /tmp/ros2-apt-source.deb \
      "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${VER}/ros2-apt-source_${VER}.noble_all.deb"
    run $SUDO dpkg -i /tmp/ros2-apt-source.deb
    ok "ros2-apt-source ${VER}"
  fi
  run $SUDO apt-get update

  # ---------------------------------------------------------------- 4
  step "[4/7] 패키지 설치 (10~30분, 진행 상황은 다른 창에서 tail -f ~/sp_install.log)"
  PKGS="ros-jazzy-desktop ros-jazzy-ros-gz ros-jazzy-robot-localization
        ros-jazzy-teleop-twist-keyboard ros-jazzy-rqt-graph ros-jazzy-rqt-topic
        python3-colcon-common-extensions python3-rosdep python3-yaml
        python3-numpy python3-matplotlib git netcat-openbsd"
  run $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y $PKGS
  ok "ROS2 Jazzy + Gazebo Harmonic"

  # ---------------------------------------------------------------- 5
  step "[5/7] rosdep"
  [ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || run $SUDO rosdep init
  if [ -n "$SUDO" ]; then run rosdep update; else warn "root 로 실행 중 — rosdep update 는 건너뜀 (일반 사용자로 한 번: rosdep update)"; fi
  ok "rosdep"
fi

if [ "$DO_BUILD" -eq 1 ]; then
  # ---------------------------------------------------------------- 6
  step "[6/7] 빌드 (colcon build)"
  [ -f "/opt/ros/$ROS_DISTRO_WANT/setup.bash" ] || { echo "  /opt/ros/$ROS_DISTRO_WANT 없음 — 먼저 bash install.sh --system-only"; false; }
  case "$REPO" in
    /mnt/*) warn "저장소가 Windows 드라이브($REPO)에 있습니다. 빌드가 매우 느리고 권한 문제가 납니다."
            warn "~/ws 에 clone 하는 것을 권장합니다 (README 3단계)." ;;
  esac
  set +u; source "/opt/ros/$ROS_DISTRO_WANT/setup.bash"; set -u
  cd "$REPO"
  run colcon build --symlink-install
  ok "빌드 완료: $(ls install | grep -c '^sp_') 개 패키지 (sp_*)"

  # ---------------------------------------------------------------- 7
  step "[7/7] ~/.bashrc 자동 source"
  MARK="# >>> smartpainting-sim >>>"
  if grep -qF "$MARK" "$HOME/.bashrc"; then
    ok "이미 등록됨"
  else
    cat >> "$HOME/.bashrc" <<EOF

$MARK
source /opt/ros/$ROS_DISTRO_WANT/setup.bash
[ -f "$REPO/install/setup.bash" ] && source "$REPO/install/setup.bash"
export ROS_DOMAIN_ID=\${ROS_DOMAIN_ID:-0}
# <<< smartpainting-sim <<<
EOF
    ok "등록 — 새 터미널부터 적용"
  fi

  echo
  echo "${B}설치 확인${N}"
  set +u; source "$REPO/install/setup.bash"; set -u
  ros2 pkg list 2>/dev/null | grep -q '^sp_cnu_bridge$' && ok "sp_cnu_bridge 패키지 보임" || { echo "  sp_cnu_bridge 가 안 보입니다"; false; }
  gz sim --versions >/dev/null 2>&1 && ok "Gazebo $(gz sim --versions | head -1)" || warn "gz sim 버전 확인 실패"
fi

echo
echo "${G}${B}설치 끝.${N}  이 터미널을 닫고 새로 연 뒤 README 의 '실행' 절을 따라 하세요."
echo "  가장 빠른 확인:  ${B}ros2 launch sp_cnu_bridge bridge_demo.launch.py${N}"
