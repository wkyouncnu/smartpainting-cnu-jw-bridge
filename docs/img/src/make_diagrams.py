#!/usr/bin/env python3
"""README 다이어그램(SVG) 생성기.

    python3 docs/img/src/make_diagrams.py        # → docs/img/diagram_*.svg

- 외부 라이브러리 없음
- 그림 제목은 넣지 않음 (README 의 "그림 N." 캡션으로 표기)
- 보고서 양식: 흰 바탕, 직각 상자, 회색 계열 + 남색 강조 1색
"""
import os

OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
FONT = "'Malgun Gothic','Noto Sans CJK KR','Noto Sans KR','Apple SD Gothic Neo',sans-serif"
MONO = "Consolas,'DejaVu Sans Mono',monospace"

C = dict(
    ink="#1a1a1a",      # 본문 글자
    sub="#4d4d4d",      # 보조 글자
    line="#333333",     # 선·화살표
    edge="#7a7a7a",     # 상자 테두리
    grp="#f4f4f4",      # 영역(그룹) 바탕
    grp2="#fafafa",
    box="#ffffff",      # 일반 상자
    acc="#1f3a5f",      # 강조(개발 노드·TCP)
    acc_f="#e9eef5",    # 강조 상자 바탕
    mute="#9a9a9a",     # 미사용·선택
)


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.e = w, h, []

    def rect(self, x, y, w, h, fill=None, stroke=None, r=0, dash=None, sw=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
                      f'fill="{fill or C["box"]}" stroke="{stroke or C["edge"]}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=12, weight="normal", color=None, anchor="middle", mono=False):
        fam = MONO if mono else FONT
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.e.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
                      f'font-weight="{weight}" fill="{color or C["ink"]}" text-anchor="{anchor}">{s}</text>')

    def lines(self, x, y, rows, size=11, gap=None, **kw):
        gap = gap or size * 1.4
        for i, r in enumerate(rows):
            self.text(x, y + i * gap, r, size=size, **kw)

    def arrow(self, x1, y1, x2, y2, color=None, label=None, lx=None, ly=None, dash=None,
              both=False, sw=1.2, lsize=10.5, mono=True):
        color = color or C["line"]
        mid = self._marker(color)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        ms = f' marker-start="url(#{mid}s)"' if both else ""
        self.e.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                      f'stroke-width="{sw}"{d} marker-end="url(#{mid})"{ms}/>')
        if label:
            for i, l in enumerate(label if isinstance(label, list) else [label]):
                self.text(lx if lx is not None else (x1 + x2) / 2,
                          (ly if ly is not None else (y1 + y2) / 2 - 6) + i * (lsize * 1.35),
                          l, size=lsize, color=C["sub"], mono=mono)

    def hline(self, x1, y1, x2, y2, color=None, dash=None, sw=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color or C["line"]}" stroke-width="{sw}"{d}/>')

    _markers = {}

    def _marker(self, color):
        mid = "m" + color.strip("#")
        if mid not in self._markers:
            self._markers[mid] = (
                f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
                f'<path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
                f'<marker id="{mid}s" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
                f'<path d="M10,0 L0,5 L10,10 z" fill="{color}"/></marker>')
        return mid

    def save(self, name):
        defs = "".join(self._markers.values())
        body = "\n".join(self.e)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
               f'width="{self.w}" height="{self.h}">\n<defs>{defs}</defs>\n'
               f'<rect width="100%" height="100%" fill="#ffffff"/>\n{body}\n</svg>\n')
        p = os.path.join(OUT, name)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        print("  [OK]", os.path.relpath(p))
        Svg._markers = {}


def node(s, x, y, w, h, name, rows, dev=False, mono_name=True):
    """처리 블록. dev=True 이면 본 과제 개발 노드(남색 강조)."""
    s.rect(x, y, w, h, C["acc_f"] if dev else C["box"], C["acc"] if dev else C["edge"],
           sw=1.4 if dev else 1.0)
    s.text(x + w / 2, y + 24, name, size=13, weight="bold", mono=mono_name, color=C["acc"] if dev else C["ink"])
    s.lines(x + w / 2, y + 45, rows, size=10.5, color=C["sub"])


# =============================================================================
# 그림 1. 시스템 구성
# =============================================================================
def overview():
    s = Svg(1100, 420)
    s.rect(15, 15, 1070, 390, C["grp2"], C["edge"])
    s.text(30, 36, "Windows 10/11 호스트 PC", size=12, weight="bold", anchor="start")
    s.rect(30, 50, 770, 340, C["grp"], C["edge"], dash="4 3")
    s.text(45, 71, "WSL2 · Ubuntu 24.04 · ROS 2 Jazzy", size=12, weight="bold", anchor="start")

    node(s, 50, 95, 190, 140, "Gazebo Harmonic",
         ["선박 블록 월드 + 크롤러 로봇", "물리 스텝 1 ms", "OdometryPublisher 50 Hz¹", "ros_gz_bridge"], mono_name=False)
    node(s, 330, 105, 170, 120, "zerokey_sim", ["ZeroKey 센서 모사", "참값 → ZeroKey 토픽", "50 Hz (wall clock)"], dev=True)
    node(s, 590, 95, 190, 140, "mpos_server", ["쿼터니언 → 헤딩(RZ)", "m → mm 변환", "TCP 서버 :5010", "요청 시 응답"], dev=True)
    s.arrow(240, 165, 328, 165, label=["/ground_truth", "Odometry"], ly=140)
    s.arrow(500, 165, 588, 165, label=["/zerokey/*", "3 topics"], ly=140)

    s.rect(50, 265, 730, 105, C["box"], C["edge"], dash="4 3")
    s.text(65, 287, "확인 도구 (선택)", size=11.5, weight="bold", anchor="start")
    s.lines(65, 310, ["rqt_graph — 노드·토픽 연결", "ros2 topic hz /zerokey/position — 주기"],
            size=10.5, color=C["sub"], anchor="start", gap=22)
    s.lines(410, 310, ["ros2 topic echo /cnu_bridge/last_tx — 송신 프레임", "ros2 run sp_cnu_bridge verify — 종단 검증"],
            size=10.5, color=C["sub"], anchor="start", gap=22)

    node(s, 860, 95, 205, 140, "JW 측 (TCP Client)",
         ["jw_receiver_gui — 수신 검증", "jw_mock_client — 콘솔", "GET_CUR_MPOS 100 Hz", "실운용: 주원 통합제어기"], mono_name=False)
    s.arrow(782, 165, 858, 165, color=C["acc"], both=True, label=["TCP", ":5010"], ly=140)
    s.lines(962, 270, ["localhost 포워딩", "127.0.0.1:5010 접속"], size=10.5, color=C["sub"])
    s.text(1070, 398, "¹ sim time 기준. 실시간 비율 10–30 % 이므로 wall clock 기준으로는 더 느림",
           size=9.5, color=C["sub"], anchor="end")
    s.save("diagram_overview.svg")


# =============================================================================
# 그림 2. ROS 2 토픽 흐름
# =============================================================================
def topics():
    s = Svg(1100, 600)

    def topic(x, y, w, name, typ, rate, h=58, mute=False):
        s.rect(x, y, w, h, C["box"], C["mute"] if mute else C["edge"], dash="4 3" if mute else None)
        s.text(x + w / 2, y + 20, name, size=11.5, weight="bold", mono=True, color=C["sub"] if mute else C["ink"])
        s.text(x + w / 2, y + 36, typ, size=9.5, mono=True, color=C["sub"])
        s.text(x + w / 2, y + 51, rate, size=9.5, color=C["sub"])

    node(s, 30, 205, 170, 100, "Gazebo", ["gz-sim + ros_gz_bridge", "(sp_gazebo)"], mono_name=False)
    topic(235, 226, 190, "/ground_truth", "nav_msgs/Odometry", "50 Hz (sim time)")
    node(s, 460, 205, 160, 100, "zerokey_sim", ["sp_cnu_bridge", "rate_hz = 50"], dev=True)
    s.arrow(200, 255, 233, 255)
    s.arrow(425, 255, 458, 255)

    ys = [70, 226, 382]
    zk = [("/zerokey/position", "geometry_msgs/PointStamped", "50 Hz · [m] → X, Y, Z", False),
          ("/zerokey/orientation", "geometry_msgs/QuaternionStamped", "50 Hz · 쿼터니언 → RZ", False),
          ("/zerokey/vel", "geometry_msgs/TwistStamped", "50 Hz · [m/s] · 미사용", True)]
    for (n, t, r, m), y in zip(zk, ys):
        topic(660, y, 250, n, t, r, mute=m)
        s.arrow(620, 255, 658, y + 29)
    s.text(785, 55, "QoS: Reliable · Volatile · KeepLast(10) (실기 Simulink 와 동일)", size=10, color=C["sub"])

    node(s, 945, 180, 135, 150, "mpos_server", ["sp_cnu_bridge", "TCP :5010", "", "구독: position,", "orientation"], dev=True)
    s.arrow(910, ys[0] + 29, 943, 215)
    s.arrow(910, ys[1] + 29, 943, 255)

    dbg = [("/cnu_bridge/mpos", "geometry_msgs/PoseStamped", "10 Hz · 확인용"),
           ("/cnu_bridge/heading_deg", "std_msgs/Float64", "10 Hz · 헤딩 [deg]"),
           ("/cnu_bridge/last_tx", "std_msgs/String", "요청마다 · 송신 프레임")]
    for i, (n, t, r) in enumerate(dbg):
        topic(400 + i * 230, 515, 215, n, t, r)
    s.hline(1012, 330, 1012, 495, color=C["acc"])
    s.hline(507, 495, 1012, 495, color=C["acc"])
    for i in range(3):
        x = 400 + i * 230 + 107
        s.arrow(x, 495, x, 513, color=C["acc"])
    s.lines(30, 530, ["mpos_server 확인용 출력", "(JW 송신값과 동일한 값을 ROS 에서 확인)"],
            size=10.5, color=C["sub"], anchor="start", gap=18)

    s.rect(235, 60, 385, 110, C["box"], C["mute"], dash="4 3")
    s.text(427, 84, "실기 연결 시", size=11.5, weight="bold")
    s.lines(427, 106, ["ZeroKey 드라이버가 동일 토픽 발행", "zerokey_sim 비활성", "use_zerokey_sim:=false"],
            size=10.5, color=C["sub"])
    s.arrow(620, 115, 658, 100, color=C["mute"], dash="4 3")
    s.save("diagram_topics.svg")


# =============================================================================
# 그림 3. TCP 시퀀스
# =============================================================================
def sequence():
    rows = [
        ("c", "TCP connect (1 s 간격 재시도, 최대 120 s)", None),
        ("r", "accept", None),
        ("c", "$JW,1,1,GET_VERSION,1,100", "버전 1.00"),
        ("r", "$CN,1,1,GET_VERSION,1,100", None),
        ("c", "$JW,2,1,GET_LOCALIZATION_STATUS,0", "2 수신 시까지 1 s 주기"),
        ("r", "$CN,2,1,GET_LOCALIZATION_STATUS,2,2,0", "2 = 위치 추정 가능"),
        ("c", "$JW,3,1,REQ_ORIGIN_INIT,0", "1 수신 시까지"),
        ("r", "$CN,3,1,REQ_ORIGIN_INIT,2,1,0", "1 = 반영 완료"),
        ("sep", "정상 운용: 아래 요청·응답 100 Hz (10 ms) 반복", None),
        ("c", "$JW,4,1,GET_CUR_MPOS,0", "위치·자세 요청"),
        ("r", "$CN,4,1,GET_CUR_MPOS,4,-2680,-878,520,0.00", "X Y Z [mm], RZ [deg]"),
        ("c", "$JW,5,1,GET_CUR_MPOS,0", None),
        ("r", "$CN,5,1,GET_CUR_MPOS,4,-2675,-878,520,0.12", None),
        ("dots", "⋮", None),
    ]
    h = 80 + 32 * len(rows) + 50
    s = Svg(1100, h)
    xl, xr = 230, 830
    s.rect(xl - 120, 15, 240, 40)
    s.text(xl, 40, "JW 통합제어기 (Client)", size=12.5, weight="bold")
    s.rect(xr - 120, 15, 240, 40, C["acc_f"], C["acc"], sw=1.4)
    s.text(xr, 40, "CN mpos_server (Server :5010)", size=12.5, weight="bold", color=C["acc"])
    y_end = h - 40
    for x in (xl, xr):
        s.hline(x, 55, x, y_end, color=C["mute"], dash="5 4")
    y = 88
    for kind, msg, note in rows:
        if kind == "sep":
            s.rect(60, y - 17, 980, 26, C["grp"], C["edge"])
            s.text(550, y + 1, msg, size=11.5, weight="bold")
        elif kind == "dots":
            s.text(550, y, msg, size=16, color=C["sub"])
        else:
            if kind == "c":
                s.arrow(xl, y, xr - 2, y, label=msg, ly=y - 6, lsize=11)
            else:
                s.arrow(xr, y, xl + 2, y, color=C["acc"], label=msg, ly=y - 6, lsize=11)
            if note:
                s.text(xr + 20, y + 4, note, size=10.5, color=C["sub"], anchor="start")
        y += 32
    s.text(550, h - 15, "응답 SEQ = 요청 SEQ · 응답 지연 100 ms 경고 / 300 ms 값 무효 / 1000 ms 두절 → 재접속",
           size=10.5, color=C["sub"])
    s.save("diagram_sequence.svg")


# =============================================================================
# 그림 4. GET_CUR_MPOS 응답 프레임
# =============================================================================
def frame():
    s = Svg(1100, 270)
    fields = [("$CN", "송신측", "CN"), ("5", "SEQ", "요청과 동일"),
              ("1", "N", "블록 수"), ("GET_CUR_MPOS", "CMD", "명령"),
              ("4", "F", "데이터 수"), ("1251", "X", "mm"), ("842", "Y", "mm"),
              ("0", "Z", "mm"), ("45.00", "RZ", "deg"), ("\\r\\n", "종료", "CR LF")]
    widths = [76, 62, 52, 170, 44, 80, 70, 50, 80, 60]
    gap = 22
    total = sum(widths) + gap * (len(widths) - 1)
    x = (1100 - total) / 2
    for (v, name, desc), w in zip(fields, widths):
        data = name in ("X", "Y", "Z", "RZ")
        s.rect(x, 20, w, 40, C["acc_f"] if data else C["box"], C["acc"] if data else C["edge"],
               sw=1.4 if data else 1.0)
        s.text(x + w / 2, 46, v, size=14, weight="bold", mono=True, color=C["acc"] if data else C["ink"])
        s.text(x + w / 2, 82, name, size=11.5, weight="bold")
        s.text(x + w / 2, 99, desc, size=10, color=C["sub"])
        if v != "\\r\\n":
            s.text(x + w + gap / 2, 47, ",", size=16, weight="bold", color=C["sub"])
        x += w + gap
    s.rect(60, 125, 980, 125, C["grp2"], C["edge"])
    s.lines(80, 150, [
        "X, Y, Z : /zerokey/position.point.x·y·z [m] × 1000 → 반올림 → 정수 mm   (pos_scale, pos_decimals)",
        "RZ      : /zerokey/orientation → ψ = atan2(2(w·z + x·y), 1 − 2(y² + z²)) → deg, 소수 2자리",
        "          범위 [−180, 180), +X 축 기준 반시계 방향 + (ENU), Simulink 모델과 동일",
        "요청    : $JW,5,1,GET_CUR_MPOS,0\\r\\n (F = 0), CN 은 요청 시에만 응답",
    ], size=11, anchor="start", mono=True, gap=25)
    s.save("diagram_frame.svg")


# =============================================================================
# 그림 5. ESKF 위치추정 구성 (sp_localization)
# =============================================================================
def eskf():
    s = Svg(1100, 330)
    node(s, 20, 30, 170, 80, "/imu", ["sensor_msgs/Imu", "200 Hz · 각속도·가속도"])
    node(s, 20, 175, 170, 80, "/joint_states", ["구동륜 26개 회전량", "엔코더 4096 tick/rev"])
    node(s, 250, 175, 170, 80, "wheel_odom", ["회전량 → 속도", "50 Hz → /odom_enc"], dev=False)
    node(s, 480, 175, 170, 80, "slip_injector", ["반경 오차·slip 주입", "→ /odom_slip"])
    s.arrow(190, 215, 248, 215)
    s.arrow(420, 215, 478, 215)

    s.rect(710, 20, 240, 250, C["acc_f"], C["acc"], sw=1.4)
    s.text(830, 44, "eskf_node", size=13, weight="bold", mono=True, color=C["acc"])
    s.lines(830, 64, ["상태 9차원", "[x, y, ψ, vx, vy, bax, bay, bg, k]"], size=10.5, color=C["sub"])
    s.rect(725, 100, 210, 50, C["box"], C["edge"])
    s.lines(830, 120, ["예측 (IMU 200 Hz)", "적분, P = F P Fᵀ + Q"], size=10.5)
    s.rect(725, 160, 210, 62, C["box"], C["edge"])
    s.lines(830, 179, ["보정 (엔코더 50 Hz)", "전진속도 · NHC · 각속도", "정지 시 ZUPT"], size=10.5)
    s.text(830, 250, "오차상태 주입 → 리셋", size=10.5, color=C["sub"])
    s.arrow(190, 70, 723, 125)
    s.arrow(650, 215, 723, 191)

    s.arrow(950, 145, 990, 145)
    s.rect(990, 115, 100, 60)
    s.lines(1040, 140, ["/odom_eskf", "Odometry"], size=10.5, mono=True)
    s.lines(1040, 205, ["zerokey_sim", "source_topic", "선택 입력"], size=10, color=C["sub"])
    s.text(550, 315, "k: 엔코더 스케일 오차 (v_enc = (1 + k)·v_true) · IMU orientation 미사용 · /ground_truth 는 평가 전용",
           size=10, color=C["sub"])
    s.save("diagram_eskf.svg")


if __name__ == "__main__":
    overview()
    topics()
    sequence()
    frame()
    eskf()
    old = os.path.join(OUT, "diagram_verify.svg")
    if os.path.exists(old):
        os.remove(old)
