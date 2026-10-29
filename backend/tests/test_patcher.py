"""
Tests for pipeline patcher utilities (no GPU needed).
"""
import pytest
from app.pipelines.patcher import snap_frames, snap_to_multiple, fit_resolution


def test_snap_to_multiple():
    assert snap_to_multiple(1023, 16) == 1024
    assert snap_to_multiple(100, 16) == 96
    assert snap_to_multiple(0, 16) == 16
    assert snap_to_multiple(512, 16) == 512


def test_snap_frames_4n1():
    # 4n+1: 1, 5, 9, 13, 17, 21 …
    assert snap_frames(81, "4n+1") == 81   # already valid
    assert snap_frames(80, "4n+1") == 81
    assert snap_frames(17, "4n+1") == 17
    assert snap_frames(16, "4n+1") == 17
    assert snap_frames(5, "4n+1") == 5
    assert snap_frames(4, "4n+1") == 5


def test_snap_frames_8n1():
    # 8n+1: 1, 9, 17, 25 …
    assert snap_frames(81, "8n+1") == 81
    assert snap_frames(80, "8n+1") == 81
    assert snap_frames(9, "8n+1") == 9
    assert snap_frames(8, "8n+1") == 9


def test_snap_frames_unknown_rule():
    # Unknown rule: passthrough
    assert snap_frames(77, "unknown") == 77


def test_fit_resolution_square():
    w, h = fit_resolution(1920, 1080, 832 * 480, 16)
    # Should be 16-aligned
    assert w % 16 == 0
    assert h % 16 == 0
    # Area should be close to target
    assert 832 * 480 * 0.7 < w * h < 832 * 480 * 1.3


def test_fit_resolution_portrait():
    w, h = fit_resolution(768, 1024, 1024 * 1024, 16)
    assert w % 16 == 0
    assert h % 16 == 0
    assert h > w  # portrait preserved


def test_fit_resolution_exact_square():
    w, h = fit_resolution(1024, 1024, 1024 * 1024, 16)
    assert w == 1024
    assert h == 1024
