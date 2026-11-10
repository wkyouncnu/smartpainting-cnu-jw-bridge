#!/usr/bin/env python3
"""README 다이어그램(SVG) 생성기 — 토픽 이름·주기를 바꾸면 여기만 고치고 다시 돌린다.

    python3 docs/img/src/make_diagrams.py        # → docs/img/diagram_*.svg

외부 라이브러리 없음. 생성된 SVG 는 GitHub README 와 PDF 양쪽에 그대로 쓰인다.
SVG 가 바뀌면 pdf_sync 가 "그림이 PDF 보다 새롭다" 를 보고 PDF 를 다시 뽑는다.
"""
import os

OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
FONT = "'Malgun Gothic','Noto Sans CJK KR','Noto Sans KR','Apple SD Gothic Neo',sans-serif"
MONO = "Consolas,'DejaVu Sans Mono',monospace"

# 색 — 영역별
C = dict(
    win="#e0f2fe", win_s="#0284c7",       # Windows
    wsl="#f1f5f9", wsl_s="#64748b",       # WSL Ubuntu
    gz="#fef3c7", gz_s="#d97706",         # Gazebo
    node="#dcfce7", node_s="#16a34a",     # 우리 ROS 노드
    jw="#fce7f3", jw_s="#db2777",         # 주원
    topic="#ffffff", topic_s="#334155",
    real="#ede9fe", real_s="#7c3aed",     # 실기 ZeroKey
    ink="#0f172a", sub="#475569", arrow="#334155", tcp="#db2777",
)


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.e = w, h, []

    def rect(self, x, y, w, h, fill, stroke, r=10, dash=None, sw=1.6):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.e.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
                      f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=13, weight="normal", color=None, anchor="middle", mono=False, italic=False):
        fam = MONO if mono else FONT
        st = ' font-style="italic"' if italic else ""
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.e.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
                      f'font-weight="{weight}" fill="{color or C["ink"]}" text-anchor="{anchor}"{st}>{s}</text>')

    def lines(self, x, y, rows, size=12, gap=None, **kw):
        gap = gap or size * 1.35
        for i, r in enumerate(rows):
            self.text(x, y + i * gap, r, size=size, **kw)

    def arrow(self, x1, y1, x2, y2, color=None, label=None, lx=None, ly=None, dash=None,
              both=False, sw=2, lsize=11.5, lcolor=None, anchor="middle"):
        color = color or C["arrow"]
        mid = self._marker(color)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        ms = f' marker-start="url(#{mid}s)"' if both else ""
        self.e.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                      f'stroke-width="{sw}"{d} marker-end="url(#{mid})"{ms}/>')
        if label:
            for i, l in enumerate(label if isinstance(label, list) else [label]):
                self.text(lx if lx is not None else (x1 + x2) / 2,
                          (ly if ly is not None else (y1 + y2) / 2 - 6) + i * (lsize * 1.3),
                          l, size=lsize, color=lcolor or color, anchor=anchor)

    _markers = {}

    def _marker(self, color):
        mid = "m" + color.strip("#")
        if mid not in self._markers:
            self._markers[mid] = (
                f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                f'<path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
                f'<marker id="{mid}s" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
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


# =============================================================================
# 1. 전체 구성 — PC 한 대 안에서 무엇이 어디서 도는가
# =============================================================================
def overview():
    s = Svg(1100, 470)
    s.text(550, 32, "전체 구성 — Windows PC 한 대에서 Gazebo · 브리지 · JW 모의 클라이언트가 함께 돈다",
           size=17, weight="bold")
    # Windows
    s.rect(20, 55, 1060, 395, C["win"], C["win_s"], r=14)
    s.text(40, 80, "Windows 11  (호스트 PC)", size=14, weight="bold", color=C["win_s"], anchor="start")
    # WSL
    s.rect(40, 95, 760, 340, C["wsl"], C["wsl_s"], r=12)
    s.text(60, 120, "WSL2 · Ubuntu 24.04 · ROS 2 Jazzy  (ROS_DOMAIN_ID=0)", size=13.5,
           weight="bold", color=C["wsl_s"], anchor="start")
    # Gazebo
    s.rect(60, 140, 185, 150, C["gz"], C["gz_s"])
    s.text(152, 168, "Gazebo Harmonic", size=14, weight="bold")
    s.lines(152, 192, ["블록 월드 + 크롤러 로봇", "물리 1 kHz (max_step 1 ms)",
                       "OdometryPublisher 50 Hz*", "+ ros_gz_bridge"], size=11.5, color=C["sub"])
    # zerokey_sim
    s.rect(345, 150, 165, 120, C["node"], C["node_s"])
    s.text(427, 178, "zerokey_sim", size=14, weight="bold", mono=True)
    s.lines(427, 202, ["ZeroKey 센서 모사", "참값 → ZeroKey 토픽", "50 Hz (벽시계)"], size=11.5, color=C["sub"])
    # mpos_server
    s.rect(580, 140, 200, 150, C["node"], C["node_s"])
    s.text(680, 168, "mpos_server", size=14, weight="bold", mono=True)
    s.lines(680, 192, ["쿼터니언 → 헤딩(RZ)", "m → mm 변환", "TCP 서버 :5010",
                       "요청 올 때마다 응답"], size=11.5, color=C["sub"])
    s.arrow(245, 228, 343, 228, label=["/ground_truth", "Odometry"], ly=200, lsize=11)
    s.arrow(510, 228, 578, 228, label=["/zerokey/*", "3 토픽"], ly=200, lsize=11)
    # 디버그 도구
    s.rect(60, 320, 720, 95, "#ffffff", C["wsl_s"], dash="5 4")
    s.text(80, 343, "확인 도구 (선택)", size=12.5, weight="bold", color=C["sub"], anchor="start")
    s.lines(80, 366, ["rqt_graph : 노드·토픽 연결 그림", "ros2 topic hz /zerokey/position : 주기 확인"],
            size=11.5, color=C["sub"], anchor="start", gap=22)
    s.lines(420, 366, ["ros2 topic echo /cnu_bridge/last_tx : 보낸 TCP 프레임", "ros2 run sp_cnu_bridge verify : 입력·참값과 오차 비교"],
            size=11.5, color=C["sub"], anchor="start", gap=22)
    # JW
    s.rect(850, 140, 210, 150, C["jw"], C["jw_s"])
    s.text(955, 166, "JW 쪽 (받는 쪽)", size=14, weight="bold")
    s.lines(955, 188, ["jw_receiver_gui.py  (검증 GUI)", "jw_mock_client  (콘솔)"], size=11, mono=True, color=C["sub"])
    s.lines(955, 236, ["GET_CUR_MPOS 100 Hz 요청", "실제 운용: 주원 통합제어기"], size=11.5, color=C["sub"])
    s.arrow(782, 215, 848, 215, color=C["tcp"], both=True, label=["TCP", "5010"], ly=180, lsize=11)
    s.text(955, 320, "localhost 포워딩으로", size=11.5, color=C["sub"])
    s.text(955, 338, "127.0.0.1:5010 에 바로 접속", size=11.5, color=C["sub"])
    s.text(1065, 440, "* sim time 기준. 이 로봇 모델은 실시간의 15~30 % 로 돌아 벽시계로는 더 느리다",
           size=10.5, color=C["sub"], anchor="end", italic=True)
    s.save("diagram_overview.svg")


# =============================================================================
# 2. 토픽·메시지·주기 상세
# =============================================================================
def topics():
    s = Svg(1100, 640)
    s.text(550, 32, "ROS 2 토픽 흐름 — 이름 · 메시지 타입 · 주기 · QoS", size=17, weight="bold")

    def node(x, y, w, h, name, rows, fill, stroke):
        s.rect(x, y, w, h, fill, stroke)
        s.text(x + w / 2, y + 26, name, size=14, weight="bold", mono=True)
        s.lines(x + w / 2, y + 48, rows, size=11, color=C["sub"])

    def topic(x, y, w, name, typ, rate, h=62):
        s.rect(x, y, w, h, C["topic"], C["topic_s"], r=31)
        s.text(x + w / 2, y + 22, name, size=12.5, weight="bold", mono=True)
        s.text(x + w / 2, y + 39, typ, size=10.5, mono=True, color=C["sub"])
        s.text(x + w / 2, y + 55, rate, size=10.5, color=C["node_s"], weight="bold")

    node(30, 230, 170, 110, "Gazebo", ["gz-sim + ros_gz_bridge", "(sp_gazebo)"], C["gz"], C["gz_s"])
    topic(240, 254, 190, "/ground_truth", "nav_msgs/Odometry", "50 Hz (sim time)")
    node(470, 230, 160, 110, "zerokey_sim", ["sp_cnu_bridge", "rate_hz = 50"], C["node"], C["node_s"])
    s.arrow(200, 285, 238, 285)
    s.arrow(430, 285, 468, 285)

    # 3 zerokey topics
    ys = [90, 255, 420]
    zk = [("/zerokey/position", "geometry_msgs/PointStamped", "50 Hz · [m]  → X, Y, Z"),
          ("/zerokey/orientation", "geometry_msgs/QuaternionStamped", "50 Hz · 쿼터니언 → RZ"),
          ("/zerokey/vel", "geometry_msgs/TwistStamped", "50 Hz · [m/s] (지금은 미사용)")]
    for (n, t, r), y in zip(zk, ys):
        topic(670, y, 250, n, t, r)
        s.arrow(630, 285, 668, y + 31)
    s.text(795, 80, "QoS: Reliable · Volatile · KeepLast(10)  =  실기 Simulink 와 동일", size=11,
           color=C["real_s"], weight="bold")

    node(950, 200, 130, 170, "mpos_server", ["sp_cnu_bridge", "TCP :5010", "", "구독: position", "     orientation"],
         C["node"], C["node_s"])
    s.arrow(920, ys[0] + 31, 948, 240)
    s.arrow(920, ys[1] + 31, 948, 285)
    s.arrow(920, ys[2] + 31, 1015, 372, dash="4 4", color="#94a3b8")
    s.text(985, 470, "(vel 은 구독 안 함)", size=10.5, color="#94a3b8")

    # debug outputs
    dbg = [("/cnu_bridge/mpos", "geometry_msgs/PoseStamped", "10 Hz · 디버그/RViz"),
           ("/cnu_bridge/heading_deg", "std_msgs/Float64", "10 Hz · 헤딩 [deg]"),
           ("/cnu_bridge/last_tx", "std_msgs/String", "요청마다 · 보낸 TCP 프레임")]
    for i, (n, t, r) in enumerate(dbg):
        x = 400 + i * 230
        topic(x, 540, 215, n, t, r)
    s.arrow(1015, 370, 1015, 520, color=C["node_s"])
    s.e.append(f'<line x1="507" y1="520" x2="1015" y2="520" stroke="{C["node_s"]}" stroke-width="2"/>')
    for i in range(3):
        x = 400 + i * 230 + 107
        s.arrow(x, 520, x, 538, color=C["node_s"])
    s.text(30, 560, "mpos_server 가 내는 확인용 토픽", size=12, weight="bold", color=C["node_s"], anchor="start")
    s.text(30, 580, "(JW 로 가는 값과 같은 값을", size=11, color=C["sub"], anchor="start")
    s.text(30, 597, " ROS 안에서도 볼 수 있게)", size=11, color=C["sub"], anchor="start")

    # real zerokey box
    s.rect(240, 75, 380, 125, C["real"], C["real_s"], dash="6 4")
    s.text(430, 100, "실기 연결 시 (나중에)", size=13, weight="bold", color=C["real_s"])
    s.lines(430, 124, ["ZeroKey 드라이버가 같은 3 토픽을 낸다", "→ zerokey_sim 만 끄면 된다",
                       "use_zerokey_sim:=false"], size=11.5, color=C["real_s"])
    s.arrow(620, 140, 668, 121, color=C["real_s"], dash="6 4")
    s.save("diagram_topics.svg")


# =============================================================================
# 3. TCP 시퀀스 (사양서 2-5 축약 + 이 구현의 응답값)
# =============================================================================
def sequence():
    rows = [
        ("c", "TCP connect (1 s 간격 재시도, 최대 120 s)", None),
        ("r", "accept", None),
        ("c", "$JW,1,1,GET_VERSION,1,100", "버전 1.00"),
        ("r", "$CN,1,1,GET_VERSION,1,100", None),
        ("c", "$JW,2,1,GET_LOCALIZATION_STATUS,0", "2 가 나올 때까지 1 s 마다"),
        ("r", "$CN,2,1,GET_LOCALIZATION_STATUS,2,2,0", "2 = 위치 추정 가능"),
        ("c", "$JW,3,1,REQ_ORIGIN_INIT,0", "1 이 나올 때까지"),
        ("r", "$CN,3,1,REQ_ORIGIN_INIT,2,1,0", "1 = 반영 완료"),
        ("sep", "정상 운용 — 아래 한 쌍을 100 Hz (10 ms) 로 반복", None),
        ("c", "$JW,4,1,GET_CUR_MPOS,0", "위치·자세 요청"),
        ("r", "$CN,4,1,GET_CUR_MPOS,4,-2680,-878,520,0.00", "X Y Z [mm], RZ [deg]"),
        ("c", "$JW,5,1,GET_CUR_MPOS,0", None),
        ("r", "$CN,5,1,GET_CUR_MPOS,4,-2675,-878,520,0.12", None),
        ("dots", "…", None),
    ]
    h = 120 + 34 * len(rows) + 70
    s = Svg(1100, h)
    s.text(550, 32, "TCP 시퀀스 — JW(클라이언트)가 묻고, CN(우리, 서버)이 답한다", size=17, weight="bold")
    xl, xr = 230, 870
    s.rect(xl - 120, 52, 240, 46, C["jw"], C["jw_s"])
    s.text(xl, 81, "JW 통합제어기 (Client)", size=13.5, weight="bold")
    s.rect(xr - 120, 52, 240, 46, C["node"], C["node_s"])
    s.text(xr, 81, "CN mpos_server (Server :5010)", size=13.5, weight="bold")
    y_end = h - 50
    for x in (xl, xr):
        s.e.append(f'<line x1="{x}" y1="98" x2="{x}" y2="{y_end}" stroke="#94a3b8" stroke-width="2" stroke-dasharray="6 5"/>')
    y = 130
    for kind, msg, note in rows:
        if kind == "sep":
            s.rect(60, y - 18, 980, 28, "#fef9c3", "#ca8a04", r=6)
            s.text(550, y + 1, msg, size=12.5, weight="bold", color="#854d0e")
        elif kind == "dots":
            s.text(550, y, "⋮", size=18, color=C["sub"])
        else:
            if kind == "c":
                s.arrow(xl, y, xr - 2, y, color=C["jw_s"], label=msg, ly=y - 7, lsize=12)
            else:
                s.arrow(xr, y, xl + 2, y, color=C["node_s"], label=msg, ly=y - 7, lsize=12)
            s.e[-1] = s.e[-1].replace(f'font-family="{FONT}"', f'font-family="{MONO}"')
            if note:
                s.text(xr + 20 if kind == "r" else xr + 20, y + 4, note, size=11, color=C["sub"], anchor="start")
        y += 34
    s.text(550, h - 22, "응답의 SEQ 는 요청의 SEQ 를 그대로 쓴다 · 응답 지연 100 ms 경고 / 300 ms 값 무효 / 1000 ms 두절 → 재접속",
           size=11.5, color=C["sub"])
    s.save("diagram_sequence.svg")


# =============================================================================
# 4. GET_CUR_MPOS 프레임 해부
# =============================================================================
def frame():
    s = Svg(1100, 330)
    s.text(550, 32, "GET_CUR_MPOS 응답 프레임 한 줄 해부", size=17, weight="bold")
    fields = [("$CN", "보낸 쪽", "CN=충남대"), ("5", "SEQ", "요청과 같음"),
              ("1", "N", "블록 수"), ("GET_CUR_MPOS", "CMD", "명령 코드"),
              ("4", "F", "데이터 4개"), ("1251", "X", "mm"), ("842", "Y", "mm"),
              ("0", "Z", "mm"), ("45.00", "RZ", "헤딩 deg"), ("\\r\\n", "끝", "CR LF")]
    widths = [76, 62, 52, 170, 44, 80, 70, 50, 80, 60]
    gap = 22
    total = sum(widths) + gap * (len(widths) - 1)
    x = (1100 - total) / 2
    for (v, name, desc), w in zip(fields, widths):
        data = name in ("X", "Y", "Z", "RZ")
        fill = "#dcfce7" if data else "#f1f5f9"
        st = C["node_s"] if data else C["wsl_s"]
        s.rect(x, 70, w, 44, fill, st, r=6)
        s.text(x + w / 2, 98, v, size=15, weight="bold", mono=True)
        s.text(x + w / 2, 138, name, size=12.5, weight="bold", color=st)
        s.text(x + w / 2, 156, desc, size=10.5, color=C["sub"])
        if v != "\\r\\n":
            s.text(x + w + gap / 2, 99, ",", size=18, weight="bold", color=C["sub"]) if (v, name) != ("4", "F") or True else None
        x += w + gap
    s.rect(60, 190, 980, 115, "#f8fafc", "#cbd5e1", r=8)
    s.lines(80, 215, [
        "X, Y, Z  ← /zerokey/position (PointStamped) 의 point.x · y · z  [m]  × 1000  → 정수 mm  (pos_scale, pos_decimals)",
        "RZ       ← /zerokey/orientation (QuaternionStamped) 에서  ψ = atan2( 2(w·z + x·y),  1 − 2(y² + z²) )  → deg, 소수 2자리",
        "           범위 [−180, 180),  +X 축 기준 반시계 + (ENU).  Simulink 모델의 식과 같다.",
        "요청은  $JW,5,1,GET_CUR_MPOS,0\\r\\n  — 데이터 없음(F=0). 우리가 먼저 보내지 않는다.",
    ], size=12, anchor="start", mono=True, gap=24)
    s.save("diagram_frame.svg")


# =============================================================================
# 5. 검증 3단계 — 무엇을 어디서 확인하는가
# =============================================================================
def verify_levels():
    s = Svg(1100, 400)
    s.text(550, 32, "검증 3단계 — 보내는 쪽(CNU)과 받는 쪽(JW) 모두 스스로 확인할 수 있다", size=17, weight="bold")
    cols = [
        ("① 단위 테스트", "보내는 쪽 · ROS 불필요", "#e0e7ff", "#4f46e5",
         ["python3 -m pytest src/sp_cnu_bridge/test", "",
          "· 사양서 예시 프레임과 글자 하나까지 같은가", "· 여러 블록 / 모르는 명령 건너뛰기",
          "· 쿼터니언 → 헤딩 (0, ±90, ±179°)", "· m → mm 반올림, -0.00 처리"],
         "성공: 15 passed"),
        ("② ROS 종단 검증", "보내는 쪽 · ROS 사용", C["node"], C["node_s"],
         ["ros2 run sp_cnu_bridge verify", "",
          "· TCP 로 받은 X·Y·Z·RZ  vs  /zerokey 입력", "· (참고) Gazebo 참값 대비 오차 [mm], [deg]",
          "· 응답률 · 지연 측정", "· 4칸 그래프 PNG 저장"],
         "성공: 일치율 ≥ 99 % (≤1 mm, ≤0.1°), 응답률 ≥ 99 %"),
        ("③ JW 수신 검증기", "받는 쪽 · ROS 불필요 (Windows)", C["jw"], C["jw_s"],
         ["run_receiver.bat  (더블클릭)", "",
          "· X·Y·Z·ψ 큰 숫자 + XY 궤적 + 헤딩 화살표", "· 프레임 형식 / SEQ / 숫자 / 범위",
          "· 지연 < 100 ms, 주기 ≥ 90 %, 두절 없음", "· 7 항목 자동 판정 → 합격/불합격"],
         "성공: 화면에 '✔ 합격 — 정상 수신'"),
    ]
    for i, (title, sub, fill, st, rows, ok) in enumerate(cols):
        x = 30 + i * 355
        s.rect(x, 60, 330, 310, fill, st, r=12)
        s.text(x + 165, 92, title, size=16, weight="bold", color=st)
        s.text(x + 165, 114, sub, size=12, color=C["sub"])
        s.text(x + 165, 150, rows[0], size=11.5, mono=True, weight="bold")
        s.lines(x + 20, 185, rows[2:], size=12, anchor="start", gap=26)
        s.rect(x + 15, 310, 300, 42, "#ffffff", st, r=8)
        s.text(x + 165, 336, ok, size=11.5, weight="bold", color=st)
    s.save("diagram_verify.svg")


if __name__ == "__main__":
    overview()
    topics()
    sequence()
    frame()
    verify_levels()
