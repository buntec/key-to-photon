"""Tests on synthetic clips: a click in the audio, a box appearing in the video.

Run: uv run --with numpy --with pytest pytest
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import ktp

KTP = str(Path(__file__).with_name("ktp.py"))
FPS = 30


def make_clip(path, *, frames=90, change=36, click=1.0, audio_offset=0.0,
              gap=0, silent=False):
    """96x64 gray clip; a white box appears at decoded frame `change`.

    The click is at `click` seconds on the file's timeline. With `gap`, frames
    from 30 on are shifted later by that many frame periods.
    """
    dur = frames / FPS + gap / FPS
    t = click - audio_offset
    noise = "0.002*(random(0)-0.5)"
    expr = noise if silent else f"{noise}+0.5*sin(2*PI*1500*t)*between(t\\,{t}\\,{t + 0.012})"
    vf = f"drawbox=x=40:y=20:w=16:h=24:color=white:t=fill:enable='gte(n\\,{change})'"
    if gap:
        vf += f",setpts='(N+{gap}*gte(N\\,30))/({FPS}*TB)'"
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", f"color=c=gray:s=96x64:r={FPS}"]
    if audio_offset:
        cmd += ["-itsoffset", str(audio_offset)]
    cmd += ["-f", "lavfi", "-i", f"aevalsrc={expr}:s=48000:d={dur - audio_offset}",
            "-vf", vf, "-frames:v", str(frames), "-fps_mode", "passthrough",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "1", "-crf", "1",
            "-c:a", "pcm_s16le", str(path)]
    subprocess.run(cmd, check=True)
    return path


def measure(clip, tmp_path, *extra, check=True):
    p = subprocess.run([sys.executable, KTP, "measure", str(clip), "--crop", "0,0,96,64",
                        "--out", str(tmp_path), "--label", "t", *extra],
                       capture_output=True, text=True)
    if check:
        assert p.returncode == 0, p.stderr
        return json.loads((tmp_path / "t.json").read_text())
    return p


def fake_audio(hp):
    a = ktp.Audio.__new__(ktp.Audio)
    a.hp = np.asarray(hp, float)
    a.smooth = np.convolve(a.hp, np.ones(ktp.SMOOTH) / ktp.SMOOTH, "same")
    a.start, a.pts, a.dur = np.array([0.0]), np.array([0.0]), np.array([np.inf])
    return a


# End to end


def test_latency(tmp_path):
    clip = make_clip(tmp_path / "c.mov")
    out = measure(clip, tmp_path)
    [ev] = out["events"]
    assert ev["text_frame"] == 36
    # (36/30 - 1.0) s of file time, slowed 8x
    assert ev["latency_ms"] == pytest.approx(25.0, abs=0.3)
    assert out["settings"]["click_ratio"] == 2.5
    assert ev["override"] is False


def test_audio_starting_late(tmp_path):
    clip = make_clip(tmp_path / "c.mov", audio_offset=0.2)
    [ev] = measure(clip, tmp_path)["events"]
    assert ev["latency_ms"] == pytest.approx(25.0, abs=0.3)


def test_timestamp_gap(tmp_path):
    # Frame 42 is shown at (42 + 15) / 30 = 1.9 s.
    clip = make_clip(tmp_path / "c.mov", gap=15, change=42, click=1.8)
    [ev] = measure(clip, tmp_path)["events"]
    assert ev["text_frame"] == 42
    assert ev["latency_ms"] == pytest.approx(12.5, abs=0.3)


def test_frame_numbers_match_measure(tmp_path):
    clip = make_clip(tmp_path / "c.mov", gap=15, change=42, click=1.8)
    shots = []
    for at in (41, 42):
        subprocess.run([sys.executable, KTP, "frame", str(clip), "--at", str(at),
                        "--out", str(tmp_path)], check=True, capture_output=True)
        shots.append(tmp_path / f"c-frame{at}.png")
    frames, _ = ktp.read_video(str(clip), (0, 0, 96, 64))
    box = (slice(30, 40), slice(45, 52))
    assert frames[41][box].mean() < 200 < frames[42][box].mean()
    assert all(s.exists() for s in shots)


def test_no_clicks(tmp_path):
    clip = make_clip(tmp_path / "c.mov", silent=True)
    out = measure(clip, tmp_path)
    assert out["events"] == [] and out["summary"] is None


def test_click_outside_range(tmp_path):
    clip = make_clip(tmp_path / "c.mov")
    out = measure(clip, tmp_path, "--range", "40:89")
    assert out["events"] == []


def test_text_search_stops_at_range_end(tmp_path):
    clip = make_clip(tmp_path / "c.mov")
    [ev] = measure(clip, tmp_path, "--range", "1:35")["events"]
    assert ev["text_frame"] is None


def test_override(tmp_path):
    clip = make_clip(tmp_path / "c.mov")
    [ev] = measure(clip, tmp_path, "--override", "30=37")["events"]
    assert ev["text_frame"] == 37 and ev["override"] is True


@pytest.mark.parametrize("args", [
    ["--override", "30=999"],  # no such frame
    ["--override", "30=20"],  # before the click
    ["--override", "31=36"],  # no such click
    ["--skip", "31"],
    ["--crop", "90,0,20,20"],  # outside the frame
    ["--range", "500:600"],
])
def test_bad_arguments(tmp_path, args):
    clip = make_clip(tmp_path / "c.mov")
    p = measure(clip, tmp_path, *args, check=False)
    assert p.returncode != 0 and "error:" in p.stderr


def test_frame_beyond_end(tmp_path):
    clip = make_clip(tmp_path / "c.mov")
    p = subprocess.run([sys.executable, KTP, "frame", str(clip), "--at", "900",
                        "--out", str(tmp_path)], capture_output=True, text=True)
    assert p.returncode != 0 and not (tmp_path / "c-frame900.png").exists()


def test_odd_crop_is_exact(tmp_path):
    clip = str(make_clip(tmp_path / "c.mov"))
    full, _ = ktp.read_video(clip, (0, 0, 96, 64))
    part, _ = ktp.read_video(clip, (15, 15, 49, 49))
    assert part.shape[1:] == (49, 49)
    assert np.array_equal(part, full[:, 15:64, 15:64])


# Units


def test_bins_at_fractional_rate():
    n = 3000
    pts = np.arange(n) * 1001 / 30000
    hp = np.zeros(int((pts[-1] + 0.1) * ktp.SR))
    hp[int((pts[2900] + 0.5 * 1001 / 30000) * ktp.SR)] = 1
    env, _ = ktp.frame_bins(fake_audio(hp), pts)
    assert int(np.argmax(env)) == 2900


def test_audio_gap_does_not_repeat_samples():
    # Two 1 s audio frames with a 2 s timestamp gap between them, and a click
    # 0.5 s into the second. Only the video frame at its time should hear it.
    a = fake_audio(np.zeros(2 * ktp.SR))
    a.hp[int(1.5 * ktp.SR)] = 1.0
    a.start = np.array([0.0, ktp.SR])
    a.pts = np.array([0.0, 3.0])
    a.dur = np.array([1.0, 1.0])
    t = np.linspace(0, 4, 401)
    assert np.all(np.diff(a.sample(t)) >= 0)
    env, _ = ktp.frame_bins(a, np.arange(0, 4, 1 / FPS))
    assert np.flatnonzero(env).tolist() == [int(3.5 * FPS)]


def test_onset_ignores_a_later_sound():
    fs = 1600  # samples per frame at 30 fps
    hp = np.full(40 * fs, 1e-4)
    hp[30 * fs:30 * fs + 100] = 1.0  # short, loud: the click
    hp[32 * fs:32 * fs + 1500] = 0.5  # longer and quieter, two frames later
    a = fake_audio(hp)
    onset = ktp.click_onset(a, 30 * fs + 50, fs)
    assert abs(onset - 30 * fs) < ktp.SMOOTH


def test_onset_bridges_short_dips():
    fs = 1600
    hp = np.full(40 * fs, 1e-4)
    hp[30 * fs:30 * fs + 300] = 0.3  # start of the sound
    hp[30 * fs + 500:30 * fs + 900] = 1.0  # its loudest part, after a dip
    onset = ktp.click_onset(fake_audio(hp), 30 * fs + 700, fs)
    assert abs(onset - 30 * fs) < ktp.SMOOTH


def clicks(env, lo=0, hi=None):
    env = np.asarray(env, float)
    return [c for c, _ in ktp.find_clicks(env, lo, hi or len(env) - 1, 2.5, 3, 40)]


def test_louder_release_is_not_the_press():
    env = np.ones(300)
    env[100], env[115] = 10, 12
    assert clicks(env) == [100]


def test_quiet_sound_before_the_press_is_not_the_press():
    env = np.ones(300)
    env[70], env[100], env[118] = 3, 14, 4
    assert clicks(env) == [100]


def test_range_applies_before_grouping():
    env = np.ones(300)
    env[30], env[36] = 20, 10
    assert clicks(env, lo=34, hi=90) == [36]
