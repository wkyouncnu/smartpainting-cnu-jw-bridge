"""프로토콜 단위 테스트 — ROS 없이 돈다:  python3 -m pytest src/sp_cnu_bridge/test -q"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sp_cnu_bridge.protocol import (Block, FrameError, build_frame, parse_frame,  # noqa: E402
                                    quat_to_yaw, mpos_fields, split_lines)
import pytest  # noqa: E402


def test_parse_spec_request():
    f = parse_frame("$JW,5,1,GET_CUR_MPOS,0\r\n")
    assert (f.src, f.seq, len(f.blocks)) == ("JW", 5, 1)
    assert f.blocks[0].cmd == "GET_CUR_MPOS" and f.blocks[0].data == []


def test_build_spec_response():
    # 사양서 2-4-5 예시 그대로
    assert build_frame("CN", 5, [Block("GET_CUR_MPOS", ["1251", "842", "0", "45"])]) \
        == "$CN,5,1,GET_CUR_MPOS,4,1251,842,0,45\r\n"


def test_multi_block_and_unknown_skip():
    f = parse_frame("$JW,9,3,FOO,2,1,2,GET_CUR_MPOS,0,GET_VERSION,1,100")
    assert [b.cmd for b in f.blocks] == ["FOO", "GET_CUR_MPOS", "GET_VERSION"]
    assert f.blocks[2].data == ["100"]


@pytest.mark.parametrize("bad", ["JW,1,1,X,0", "$JW,a,1,X,0", "$JW,1,1,X,2,5", "$JW,1,2,X,0"])
def test_bad_frames(bad):
    with pytest.raises(FrameError):
        parse_frame(bad)


@pytest.mark.parametrize("deg", [0, 45, 90, 179, -90, -179])
def test_quat_to_yaw(deg):
    h = math.radians(deg) / 2
    assert math.isclose(math.degrees(quat_to_yaw(0, 0, math.sin(h), math.cos(h))), deg, abs_tol=1e-9)


def test_mpos_fields_units():
    # 1.2514 m → 1251 mm,  yaw 45° → "45.00"
    assert mpos_fields(1.2514, 0.8418, 0.0, math.radians(45)) == ["1251", "842", "0", "45.00"]
    # 270° 는 -90° 로,  -0.00 은 0.00 으로
    assert mpos_fields(0, 0, 0, math.radians(270))[3] == "-90.00"
    assert mpos_fields(0, 0, 0, -1e-9)[3] == "0.00"


def test_split_lines_partial():
    lines, rest = split_lines(b"$JW,1,1,GET_VERSION,1,100\r\n$JW,2,1,GET_")
    assert lines == ["$JW,1,1,GET_VERSION,1,100"] and rest == b"$JW,2,1,GET_"
