"""CNU ↔ JW 위치 공유 프로토콜 (TCP/ASCII) — ROS 에 의존하지 않는 순수 함수만 모았다.

프레임 형식 (사양서 2-2):

    $<SRC>,<SEQ>,<N>,<CMD>,<F>,D1,...,D_F[,<CMD>,<F>,...]<CR><LF>

    SRC  CN(충남대) / JW(주원)
    SEQ  0~65535 일련번호. 응답은 요청의 SEQ 를 그대로 돌려준다
    N    이 프레임의 명령 블록 개수
    CMD  명령 코드,  F  그 블록의 데이터 개수,  D  데이터

이 저장소가 다루는 핵심 명령 (사양서 2-4-5):

    요청  $JW,5,1,GET_CUR_MPOS,0\r\n
    응답  $CN,5,1,GET_CUR_MPOS,4,<X>,<Y>,<Z>,<RZ>\r\n
          X·Y·Z = 위치 [mm],  RZ = 헤딩(Yaw) [deg]
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

CRLF = "\r\n"
SEQ_MAX = 65535


@dataclass
class Block:
    cmd: str
    data: List[str] = field(default_factory=list)


@dataclass
class Frame:
    src: str
    seq: int
    blocks: List[Block]


class FrameError(ValueError):
    """프레임 형식이 깨졌을 때."""


def parse_frame(line: str) -> Frame:
    """한 줄(CR/LF 제외 또는 포함)을 Frame 으로 푼다.

    모르는 명령도 F 개수만큼 건너뛸 수 있으므로 블록 단위로 끊어 낸다.
    """
    s = line.strip()
    if not s.startswith("$"):
        raise FrameError(f"'$' 로 시작하지 않음: {line!r}")
    tok = [t.strip() for t in s[1:].split(",")]
    if len(tok) < 3:
        raise FrameError(f"필드 부족: {line!r}")
    src = tok[0]
    try:
        seq = int(tok[1])
        n = int(tok[2])
    except ValueError as e:
        raise FrameError(f"SEQ/N 이 정수가 아님: {line!r}") from e
    i = 3
    blocks: List[Block] = []
    for _ in range(n):
        if i + 1 >= len(tok):
            raise FrameError(f"블록 {len(blocks) + 1}/{n} 이 잘림: {line!r}")
        cmd = tok[i]
        try:
            f = int(tok[i + 1])
        except ValueError as e:
            raise FrameError(f"{cmd} 의 F 가 정수가 아님: {line!r}") from e
        data = tok[i + 2:i + 2 + f]
        if len(data) != f:
            raise FrameError(f"{cmd}: F={f} 인데 데이터 {len(data)} 개: {line!r}")
        blocks.append(Block(cmd, data))
        i += 2 + f
    return Frame(src, seq, blocks)


def build_frame(src: str, seq: int, blocks: List[Block]) -> str:
    """Frame → 송신 문자열 (CRLF 포함)."""
    parts = [f"${src}", str(seq % (SEQ_MAX + 1)), str(len(blocks))]
    for b in blocks:
        parts += [b.cmd, str(len(b.data))] + [str(d) for d in b.data]
    return ",".join(parts) + CRLF


# ---------------------------------------------------------------- 자세 변환
def quat_to_yaw(x: float, y: float, z: float, w: float) -> float:
    """쿼터니언 → Yaw [rad]  (ZYX 오일러의 Z 성분, ENU: +X 기준 반시계 +).

    Simulink(Tracked_UGV_ZeroKey_XsensIMU.slx)의 식과 같다:
        psi = atan2(2(wz + xy), 1 − 2(y² + z²))
    """
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def wrap_deg(a: float) -> float:
    """각도를 [-180, 180) 으로."""
    return (a + 180.0) % 360.0 - 180.0


def fmt_num(v: float, decimals: int) -> str:
    """소수 자릿수 고정. decimals=0 이면 정수 (반올림)."""
    if decimals <= 0:
        return str(int(round(v)))
    s = f"{v:.{decimals}f}"
    return s.lstrip("-") if float(s) == 0.0 else s   # "-0.00" → "0.00"


def mpos_fields(x_m: float, y_m: float, z_m: float, yaw_rad: float,
                pos_scale: float = 1000.0, pos_decimals: int = 0,
                yaw_decimals: int = 2) -> List[str]:
    """[m],[rad] → GET_CUR_MPOS 응답 데이터 4개 [X, Y, Z, RZ] (기본 mm 정수, deg 소수 2자리)."""
    return [fmt_num(x_m * pos_scale, pos_decimals),
            fmt_num(y_m * pos_scale, pos_decimals),
            fmt_num(z_m * pos_scale, pos_decimals),
            fmt_num(wrap_deg(math.degrees(yaw_rad)), yaw_decimals)]


def split_lines(buf: bytes) -> Tuple[List[str], bytes]:
    """수신 버퍼에서 완결된 줄(LF 기준)만 떼어 내고 나머지를 돌려준다."""
    lines = []
    while b"\n" in buf:
        raw, buf = buf.split(b"\n", 1)
        txt = raw.decode("ascii", errors="replace").strip()
        if txt:
            lines.append(txt)
    return lines, buf
