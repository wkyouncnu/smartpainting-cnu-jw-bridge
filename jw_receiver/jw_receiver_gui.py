#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JW 수신 검증기 — 주원 통합제어기 쪽에서 "CNU 위치값이 제대로 도착하는가" 를 눈으로 확인하는 프로그램.

  * ROS 필요 없음. Python 3.8 이상 표준 라이브러리(tkinter, socket)만 쓴다.
  * Windows: run_receiver.bat 더블클릭  /  python jw_receiver_gui.py
  * Ubuntu : python3 jw_receiver_gui.py   (tkinter 없으면 sudo apt install python3-tk)
  * 창 없이: python jw_receiver_gui.py --nogui --duration 20

하는 일
  1) CNU 서버(TCP, 기본 127.0.0.1:5010)에 접속
  2) (선택) 사양서 기동 절차  GET_VERSION → GET_LOCALIZATION_STATUS(=2) → REQ_ORIGIN_INIT(=1)
  3) GET_CUR_MPOS 를 100 Hz 로 요청하고 응답  $CN,<SEQ>,1,GET_CUR_MPOS,4,X,Y,Z,RZ  를 받는다
  4) 받은 X·Y·Z[mm], ψ(RZ)[deg] 를 크게 표시 + XY 궤적 + 헤딩 화살표
  5) 응답마다 아래 항목을 자동 판정 → 전부 통과하면 "합격"

     ① 프레임 형식   $CN 으로 시작, N=1, CMD=GET_CUR_MPOS, F=4, CR LF 로 끝남
     ② SEQ 일치      응답 SEQ == 요청 SEQ
     ③ 값 해석       X·Y·Z·RZ 가 숫자
     ④ 헤딩 범위     -180 ≤ RZ < 180
     ⑤ 응답 지연     < 100 ms (사양서 2-7: 100 ms 경고 / 300 ms 무효)
     ⑥ 수신 주기     요청 주기의 90 % 이상
     ⑦ 통신 두절     1000 ms 이상 무응답이 없었음
"""
from __future__ import print_function

import argparse
import collections
import csv
import math
import os
import socket
import sys
import threading
import time

CRLF = "\r\n"
VERSION = "1.0"


# =============================================================================
#  통신 + 판정 (GUI 와 무관 — --nogui 에서도 같은 코드)
# =============================================================================
class Checks(object):
    NAMES = [
        ("frame", "① 프레임 형식 ($CN, N=1, GET_CUR_MPOS, F=4, CRLF)"),
        ("seq", "② SEQ 일치 (응답 SEQ = 요청 SEQ)"),
        ("num", "③ 값 해석 (X·Y·Z·RZ 숫자)"),
        ("yaw", "④ 헤딩 범위 (-180 ≤ RZ < 180)"),
        ("lat", "⑤ 응답 지연 < 100 ms"),
        ("rate", "⑥ 수신 주기 ≥ 요청의 90 %"),
        ("drop", "⑦ 통신 두절(1 s 무응답) 없음"),
    ]

    def __init__(self):
        self.ok = collections.Counter()
        self.bad = collections.Counter()
        self.last_bad = {}

    def mark(self, key, good, why=""):
        if good:
            self.ok[key] += 1
        else:
            self.bad[key] += 1
            self.last_bad[key] = why

    def passed(self, key):
        return self.bad[key] == 0 and (self.ok[key] > 0)


class Receiver(object):
    def __init__(self, host, port, rate, handshake=True, csv_path=""):
        self.host, self.port, self.rate = host, port, rate
        self.handshake = handshake
        self.csv_path = csv_path
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.reset()

    def reset(self):
        self.checks = Checks()
        self.state = "대기"
        self.last = None            # dict(seq, X, Y, Z, RZ, lat)
        self.track = collections.deque(maxlen=4000)   # (X, Y)
        self.raw = collections.deque(maxlen=12)
        self.log = collections.deque(maxlen=200)
        self.n_req = 0
        self.n_rx = 0
        self.lat = collections.deque(maxlen=500)
        self.t_start = None
        self.rx_times = collections.deque(maxlen=300)
        self.version = "-"
        self.loc_status = "-"

    # ------------------------------------------------------------------
    def say(self, s):
        line = time.strftime("%H:%M:%S ") + s
        with self.lock:
            self.log.append(line)
        print(line)

    def start(self):
        if self.running:
            return
        self.reset()
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.running = False

    # ------------------------------------------------------------------
    def _send_recv(self, sock, f, seq, cmd, data=(), timeout=1.0):
        tx = ",".join(["$JW", str(seq), "1", cmd, str(len(data))] + [str(d) for d in data]) + CRLF
        t0 = time.perf_counter()
        sock.settimeout(timeout)
        sock.sendall(tx.encode("ascii"))
        raw = f.readline()          # bytes, CRLF 포함
        lat = (time.perf_counter() - t0) * 1000.0
        if not raw:
            raise ConnectionError("서버가 연결을 닫음")
        return tx.strip(), raw.decode("ascii", "replace"), lat

    def _run(self):
        seq = 0
        csv_f = None
        writer = None
        if self.csv_path:
            csv_f = open(self.csv_path, "w", newline="", encoding="utf-8")
            writer = csv.writer(csv_f)
            writer.writerow(["t_s", "seq", "X_mm", "Y_mm", "Z_mm", "RZ_deg", "latency_ms", "raw"])
        while self.running:
            self.state = "접속 시도"
            try:
                sock = socket.create_connection((self.host, self.port), timeout=1.0)
            except OSError as e:
                self.say("접속 실패 (%s) — 1 s 뒤 재시도" % e.__class__.__name__)
                time.sleep(1.0)
                continue
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            f = sock.makefile("rb")
            seq = 0                         # 사양서 2-8: 접속 성립 시 SEQ 0
            self.say("접속 %s:%d" % (self.host, self.port))
            try:
                if self.handshake:
                    self.state = "기동 절차"
                    seq += 1
                    _, r, _ = self._send_recv(sock, f, seq, "GET_VERSION", [100], timeout=3.0)
                    t = r.strip().split(",")
                    self.version = "%.2f" % (int(t[5]) / 100.0) if len(t) > 5 else "?"
                    self.say("GET_VERSION → CN 버전 %s" % self.version)
                    while self.running:
                        seq += 1
                        _, r, _ = self._send_recv(sock, f, seq, "GET_LOCALIZATION_STATUS")
                        t = r.strip().split(",")
                        self.loc_status = t[5] if len(t) > 5 else "?"
                        self.say("GET_LOCALIZATION_STATUS → %s" % self.loc_status)
                        if self.loc_status == "2":
                            break
                        time.sleep(1.0)
                    while self.running:
                        seq += 1
                        _, r, _ = self._send_recv(sock, f, seq, "REQ_ORIGIN_INIT")
                        t = r.strip().split(",")
                        st = t[5] if len(t) > 5 else "?"
                        self.say("REQ_ORIGIN_INIT → %s" % st)
                        if st == "1":
                            break
                        time.sleep(1.0)
                self.state = "수신 중"
                self.t_start = time.perf_counter()
                period = 1.0 / self.rate
                nxt = time.perf_counter()
                t_last_ok = time.perf_counter()
                while self.running:
                    seq = (seq + 1) % 65536
                    try:
                        tx, raw, lat = self._send_recv(sock, f, seq, "GET_CUR_MPOS", timeout=1.0)
                    except socket.timeout:
                        if time.perf_counter() - t_last_ok >= 1.0:
                            self.checks.mark("drop", False, "1 s 무응답")
                            self.say("통신 두절 (1000 ms) → 재접속")
                            break
                        continue
                    now = time.perf_counter()
                    t_last_ok = now
                    self.n_req += 1
                    rec = self._judge(raw, seq, lat)
                    with self.lock:
                        self.raw.append(("S: " + tx, "R: " + raw.strip()))
                        self.lat.append(lat)
                        self.rx_times.append(now)
                        if rec:
                            self.n_rx += 1
                            self.last = rec
                            self.track.append((rec["X"], rec["Y"]))
                    if writer and rec:
                        writer.writerow(["%.4f" % (now - self.t_start), seq, rec["X"], rec["Y"], rec["Z"],
                                         rec["RZ"], "%.3f" % lat, raw.strip()])
                    nxt += period
                    sl = nxt - time.perf_counter()
                    if sl > 0:
                        time.sleep(sl)
                    else:
                        nxt = time.perf_counter()
            except (ConnectionError, OSError) as e:
                self.say("연결 끊김: %s — 1 s 뒤 재접속" % e)
                self.checks.mark("drop", False, str(e))
                time.sleep(1.0)
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
        self.state = "정지"
        if csv_f:
            csv_f.close()
            self.say("CSV 저장: %s" % self.csv_path)

    def _judge(self, raw, seq, lat):
        c = self.checks
        ends_crlf = raw.endswith("\r\n")
        t = raw.strip().split(",")
        frame_ok = (ends_crlf and len(t) == 9 and t[0] == "$CN" and t[2] == "1"
                    and t[3] == "GET_CUR_MPOS" and t[4] == "4")
        c.mark("frame", frame_ok, raw.strip() if not frame_ok else "")
        if not frame_ok:
            return None
        c.mark("seq", t[1] == str(seq), "요청 %d / 응답 %s" % (seq, t[1]))
        try:
            X, Y, Z, RZ = [float(v) for v in t[5:9]]
            c.mark("num", True)
        except ValueError:
            c.mark("num", False, ",".join(t[5:9]))
            return None
        c.mark("yaw", -180.0 <= RZ < 180.0, "RZ=%s" % t[8])
        c.mark("lat", lat < 100.0, "%.1f ms" % lat)
        c.ok["drop"] += 0
        return {"seq": int(t[1]), "X": X, "Y": Y, "Z": Z, "RZ": RZ, "lat": lat,
                "sX": t[5], "sY": t[6], "sZ": t[7], "sRZ": t[8]}

    # ------------------------------------------------------------------
    def rx_hz(self):
        with self.lock:
            ts = list(self.rx_times)
        if len(ts) < 2:
            return 0.0
        return (len(ts) - 1) / max(ts[-1] - ts[0], 1e-9)

    def evaluate(self):
        """판정 결과 [(key, 이름, 통과여부, 설명)] 과 종합 여부."""
        c = self.checks
        hz = self.rx_hz()
        enough = self.n_rx >= 50
        if enough:
            c.bad["rate"] = 0 if hz >= 0.9 * self.rate else 1
            c.ok["rate"] = 1
            c.last_bad["rate"] = "%.1f Hz < %.1f Hz" % (hz, 0.9 * self.rate)
            c.ok["drop"] = max(c.ok["drop"], 1)
        out = []
        for key, name in Checks.NAMES:
            if not enough:
                out.append((key, name, None, "수신 대기 중"))
                continue
            p = c.bad[key] == 0
            if key == "rate":
                desc = "%.1f Hz" % hz
            elif key == "lat":
                with self.lock:
                    l = list(self.lat)
                desc = "평균 %.2f / 최대 %.2f ms" % (sum(l) / len(l), max(l)) if l else "-"
            else:
                desc = "%d 건 통과" % c.ok[key] if p else "%d 건 실패 (%s)" % (c.bad[key], c.last_bad.get(key, ""))
            if key == "drop":
                desc = "없음" if p else "%d 회" % c.bad[key]
            out.append((key, name, p, desc))
        overall = enough and all(p for _, _, p, _ in out)
        return out, overall


# =============================================================================
#  GUI (tkinter)
# =============================================================================
def run_gui(args):
    import tkinter as tk
    from tkinter import ttk, filedialog

    rx = Receiver(args.host, args.port, args.rate, not args.no_handshake, args.csv)

    root = tk.Tk()
    root.title("JW 수신 검증기 v%s — CNU GET_CUR_MPOS (X, Y, Z, ψ)" % VERSION)
    root.geometry("1180x760")
    root.configure(bg="#f8fafc")
    FONT = ("Malgun Gothic", 10)
    BIG = ("Consolas", 30, "bold")
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # ---- 상단: 접속 설정 ----
    top = tk.Frame(root, bg="#e2e8f0", padx=8, pady=6)
    top.pack(fill="x")
    v_host = tk.StringVar(value=args.host)
    v_port = tk.StringVar(value=str(args.port))
    v_rate = tk.StringVar(value=str(int(args.rate)))
    v_hs = tk.BooleanVar(value=not args.no_handshake)
    for lbl, var, w in (("서버 IP", v_host, 14), ("포트", v_port, 6), ("요청 주기 Hz", v_rate, 5)):
        tk.Label(top, text=lbl, bg="#e2e8f0", font=FONT).pack(side="left", padx=(6, 2))
        tk.Entry(top, textvariable=var, width=w, font=FONT).pack(side="left")
    tk.Checkbutton(top, text="기동 절차 수행 (VERSION→STATUS→ORIGIN)", variable=v_hs, bg="#e2e8f0",
                   font=FONT).pack(side="left", padx=10)
    v_state = tk.StringVar(value="대기")

    def on_start():
        rx.host, rx.port, rx.rate = v_host.get().strip(), int(v_port.get()), float(v_rate.get())
        rx.handshake = v_hs.get()
        rx.start()

    def on_stop():
        rx.stop()

    def on_csv():
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile="jw_rx_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
        if p:
            with rx.lock:
                tr = list(rx.track)
            with open(p, "w", newline="", encoding="utf-8") as fp:
                w = csv.writer(fp)
                w.writerow(["X_mm", "Y_mm"])
                w.writerows(tr)

    tk.Button(top, text="▶ 연결/수신 시작", command=on_start, bg="#16a34a", fg="white",
              font=("Malgun Gothic", 10, "bold"), padx=10).pack(side="left", padx=4)
    tk.Button(top, text="■ 정지", command=on_stop, bg="#dc2626", fg="white",
              font=("Malgun Gothic", 10, "bold"), padx=10).pack(side="left", padx=4)
    tk.Button(top, text="궤적 CSV 저장", command=on_csv, font=FONT).pack(side="left", padx=4)
    tk.Label(top, textvariable=v_state, bg="#e2e8f0", font=("Malgun Gothic", 10, "bold"),
             fg="#1d4ed8").pack(side="right", padx=8)

    body = tk.Frame(root, bg="#f8fafc")
    body.pack(fill="both", expand=True, padx=8, pady=6)
    left = tk.Frame(body, bg="#f8fafc")
    left.pack(side="left", fill="both", expand=True)
    right = tk.Frame(body, bg="#f8fafc", width=470)
    right.pack(side="right", fill="y")

    # ---- 큰 숫자 4개 ----
    vals = tk.Frame(left, bg="#f8fafc")
    vals.pack(fill="x")
    v_num = {}
    for i, (k, lbl, unit, col) in enumerate((("X", "X", "mm", "#0f172a"), ("Y", "Y", "mm", "#0f172a"),
                                             ("Z", "Z", "mm", "#0f172a"), ("RZ", "ψ (RZ, 헤딩)", "deg", "#b91c1c"))):
        fr = tk.Frame(vals, bg="white", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=4)
        fr.grid(row=0, column=i, sticky="nsew", padx=3)
        vals.grid_columnconfigure(i, weight=1)
        tk.Label(fr, text="%s [%s]" % (lbl, unit), bg="white", font=FONT, fg="#475569").pack(anchor="w")
        v_num[k] = tk.StringVar(value="-")
        tk.Label(fr, textvariable=v_num[k], bg="white", font=BIG, fg=col).pack(anchor="e")
    v_meta = tk.StringVar(value="")
    tk.Label(left, textvariable=v_meta, bg="#f8fafc", font=("Consolas", 10), fg="#334155",
             anchor="w").pack(fill="x", pady=(4, 2))

    # ---- XY 궤적 캔버스 ----
    cv = tk.Canvas(left, bg="white", highlightbackground="#cbd5e1", highlightthickness=1)
    cv.pack(fill="both", expand=True, pady=4)

    # ---- 원문 ----
    tk.Label(left, text="최근 송수신 원문 (S: 보낸 요청 / R: 받은 응답)", bg="#f8fafc", font=FONT,
             anchor="w").pack(fill="x")
    raw_box = tk.Text(left, height=6, font=("Consolas", 9), bg="#0f172a", fg="#e2e8f0")
    raw_box.pack(fill="x")

    # ---- 오른쪽: 판정 ----
    tk.Label(right, text="수신 검증 (응답마다 자동 판정)", bg="#f8fafc",
             font=("Malgun Gothic", 12, "bold")).pack(anchor="w", padx=6)
    chk_rows = {}
    for key, name in Checks.NAMES:
        fr = tk.Frame(right, bg="white", highlightbackground="#e2e8f0", highlightthickness=1)
        fr.pack(fill="x", padx=6, pady=2)
        icon = tk.Label(fr, text="…", width=3, bg="white", font=("Malgun Gothic", 13, "bold"))
        icon.pack(side="left")
        txt = tk.Frame(fr, bg="white")
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=name, bg="white", font=FONT, anchor="w").pack(fill="x")
        d = tk.StringVar(value="수신 대기 중")
        tk.Label(txt, textvariable=d, bg="white", font=("Malgun Gothic", 9), fg="#64748b", anchor="w").pack(fill="x")
        chk_rows[key] = (icon, d)
    verdict = tk.Label(right, text="판정 대기", font=("Malgun Gothic", 22, "bold"), bg="#e2e8f0",
                       fg="#475569", pady=10)
    verdict.pack(fill="x", padx=6, pady=10)
    tk.Label(right, text="진행 기록", bg="#f8fafc", font=FONT, anchor="w").pack(fill="x", padx=6)
    log_box = tk.Text(right, height=12, font=("Consolas", 9), bg="white")
    log_box.pack(fill="both", expand=True, padx=6)

    def draw_track():
        cv.delete("all")
        W, H = cv.winfo_width(), cv.winfo_height()
        with rx.lock:
            tr = list(rx.track)
            last = rx.last
        cv.create_text(10, 10, anchor="nw", text="XY 궤적 (받은 값, mm)  ● 현재 위치  → 헤딩 ψ",
                       font=FONT, fill="#334155")
        if not tr:
            return
        xs, ys = [p[0] for p in tr], [p[1] for p in tr]
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys), 400.0) * 1.25
        sc = min(W - 40, H - 50) / span

        def P(x, y):
            return W / 2 + (x - cx) * sc, H / 2 + 12 - (y - cy) * sc

        # 격자 (100 mm 또는 500 mm)
        step = 100.0 if span < 1500 else 500.0
        gx = math.floor((cx - span / 2) / step) * step
        while gx < cx + span / 2:
            a, _ = P(gx, 0)
            cv.create_line(a, 30, a, H, fill="#f1f5f9")
            gx += step
        gy = math.floor((cy - span / 2) / step) * step
        while gy < cy + span / 2:
            _, b = P(0, gy)
            cv.create_line(0, b, W, b, fill="#f1f5f9")
            gy += step
        cv.create_text(W - 10, H - 10, anchor="se", text="격자 %d mm" % step, font=("Malgun Gothic", 8),
                       fill="#94a3b8")
        pts = []
        for x, y in tr[::max(1, len(tr) // 1500)]:
            pts += list(P(x, y))
        if len(pts) >= 4:
            cv.create_line(*pts, fill="#2563eb", width=2)
        if last:
            px, py = P(last["X"], last["Y"])
            cv.create_oval(px - 6, py - 6, px + 6, py + 6, fill="#dc2626", outline="")
            L = 45
            a = math.radians(last["RZ"])
            cv.create_line(px, py, px + L * math.cos(a), py - L * math.sin(a), fill="#dc2626", width=3,
                           arrow="last", arrowshape=(12, 14, 5))

    def tick():
        v_state.set("상태: " + rx.state)
        with rx.lock:
            last = rx.last
            raws = list(rx.raw)[-6:]
            logs = list(rx.log)[-14:]
        if last:
            v_num["X"].set(last["sX"])
            v_num["Y"].set(last["sY"])
            v_num["Z"].set(last["sZ"])
            v_num["RZ"].set(last["sRZ"])
            el = time.perf_counter() - rx.t_start if rx.t_start else 0
            v_meta.set("SEQ %5d   수신 %7d 건   수신 주기 %6.1f Hz   지연 %6.2f ms   경과 %6.1f s   CN 버전 %s" %
                       (last["seq"], rx.n_rx, rx.rx_hz(), last["lat"], el, rx.version))
        raw_box.delete("1.0", "end")
        for s, r in raws:
            raw_box.insert("end", s + "\n" + r + "\n")
        log_box.delete("1.0", "end")
        log_box.insert("end", "\n".join(logs))
        res, overall = rx.evaluate()
        for key, name, p, desc in res:
            icon, d = chk_rows[key]
            d.set(desc)
            if p is None:
                icon.config(text="…", fg="#94a3b8")
            elif p:
                icon.config(text="✔", fg="#16a34a")
            else:
                icon.config(text="✘", fg="#dc2626")
        if rx.n_rx < 50:
            verdict.config(text="판정 대기", bg="#e2e8f0", fg="#475569")
        elif overall:
            verdict.config(text="✔ 합격 — 정상 수신", bg="#dcfce7", fg="#15803d")
        else:
            verdict.config(text="✘ 불합격 항목 있음", bg="#fee2e2", fg="#b91c1c")
        draw_track()
        root.after(150, tick)

    def grab_window_win32(path):
        """다른 창이 위에 겹쳐 있어도 이 창 내용만 찍는다 (Win32 PrintWindow)."""
        import ctypes
        from ctypes import wintypes
        from PIL import Image
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        hwnd = int(root.wm_frame(), 16)
        r = wintypes.RECT()
        u.GetClientRect(hwnd, ctypes.byref(r))
        w, h = r.right, r.bottom
        hdc = u.GetDC(hwnd)
        mdc = g.CreateCompatibleDC(hdc)
        bmp = g.CreateCompatibleBitmap(hdc, w, h)
        g.SelectObject(mdc, bmp)
        u.PrintWindow(hwnd, mdc, 3)          # PW_CLIENTONLY | PW_RENDERFULLCONTENT

        class BMI(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                        ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
                        ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32),
                        ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                        ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]
        bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
        Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(path)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(hwnd, hdc)

    def snapshot_and_quit():
        try:
            root.update()
            if sys.platform == "win32":
                grab_window_win32(args.snapshot)
            else:
                from PIL import ImageGrab
                x, y = root.winfo_rootx(), root.winfo_rooty()
                w, h = root.winfo_width(), root.winfo_height()
                ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(args.snapshot)
            print("스냅샷 저장:", args.snapshot)
        except Exception as e:   # PIL 없음 등
            print("스냅샷 실패:", e)
        rx.stop()
        root.after(300, root.destroy)

    root.protocol("WM_DELETE_WINDOW", lambda: (rx.stop(), root.after(200, root.destroy)))
    root.after(150, tick)
    if args.autostart or args.snapshot:
        root.after(300, on_start)
    if args.snapshot:
        root.after(int(args.duration * 1000), snapshot_and_quit)
    root.mainloop()


# =============================================================================
#  창 없이 (CI / 원격 / tkinter 없는 PC)
# =============================================================================
def run_cli(args):
    rx = Receiver(args.host, args.port, args.rate, not args.no_handshake, args.csv)
    rx.start()
    t0 = time.time()
    try:
        while time.time() - t0 < args.duration:
            time.sleep(1.0)
            if rx.last:
                l = rx.last
                print("  X %8s  Y %8s  Z %6s  ψ %8s  | %6.1f Hz  지연 %.2f ms" %
                      (l["sX"], l["sY"], l["sZ"], l["sRZ"], rx.rx_hz(), l["lat"]))
    except KeyboardInterrupt:
        pass
    res, overall = rx.evaluate()
    rx.stop()
    print("\n" + "=" * 64)
    print(" JW 수신 검증 결과  (수신 %d 건)" % rx.n_rx)
    print("=" * 64)
    for key, name, p, desc in res:
        print(" %s %-40s %s" % ("✔" if p else ("…" if p is None else "✘"), name, desc))
    print("=" * 64)
    print(" 최종: " + ("✔ 합격 — 정상 수신" if overall else "✘ 불합격"))
    time.sleep(0.3)
    return 0 if overall else 1


def main():
    ap = argparse.ArgumentParser(description="JW 수신 검증기 (CNU GET_CUR_MPOS)")
    ap.add_argument("--host", default="127.0.0.1", help="CNU 서버 IP (WSL 이면 127.0.0.1)")
    ap.add_argument("--port", type=int, default=5010)
    ap.add_argument("--rate", type=float, default=100.0, help="GET_CUR_MPOS 요청 주기 [Hz]")
    ap.add_argument("--no-handshake", action="store_true", help="기동 절차 생략, 바로 GET_CUR_MPOS")
    ap.add_argument("--csv", default="", help="받은 값을 전부 CSV 로 저장")
    ap.add_argument("--nogui", action="store_true", help="창 없이 콘솔로")
    ap.add_argument("--duration", type=float, default=20.0, help="--nogui / --snapshot 측정 시간 [s]")
    ap.add_argument("--autostart", action="store_true", help="창을 열자마자 접속")
    ap.add_argument("--snapshot", default="", help="duration 뒤 창을 PNG 로 저장하고 종료 (문서용)")
    args = ap.parse_args()
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if args.nogui:
        sys.exit(run_cli(args))
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter 가 없습니다 → --nogui 로 실행하거나  sudo apt install python3-tk")
        sys.exit(run_cli(args))
    run_gui(args)


if __name__ == "__main__":
    main()
