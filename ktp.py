#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Measure key-to-photon latency from a slow-motion video of typing.

The key press is the onset of the key click in the audio track; the photon
is the first frame where the typed line changes after it. Both are placed on
the file's own timeline (decoded frame and audio timestamps).
"""

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 48000
SMOOTH = 48  # samples (1 ms of file time) for the onset envelope
MARGIN = 6  # crop border residual() leaves out
SHIFT = 4  # camera shake residual() aligns for
RELEASE = 0.5  # see find_clicks()


def fail(msg):
    sys.exit(f"error: {msg}")


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, **kw)
    if p.returncode:
        err = p.stderr if isinstance(p.stderr, str) else p.stderr.decode(errors="replace")
        fail(f"{cmd[0]} failed:\n{err.strip()[-2000:]}")
    return p


def video_size(video):
    """Width and height of decoded frames, after rotation."""
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height:stream_side_data=rotation", "-of", "json", video],
              text=True).stdout
    streams = json.loads(out).get("streams")
    if not streams:
        fail(f"{video} has no video stream")
    s = streams[0]
    w, h = s["width"], s["height"]
    rot = next((abs(int(d.get("rotation", 0))) for d in s.get("side_data_list", [])), 0)
    return (h, w) if rot in (90, 270) else (w, h)


def parse_crop(text, video):
    try:
        x, y, w, h = map(int, text.split(","))
    except ValueError:
        fail(f"--crop must be X,Y,W,H, got {text!r}")
    fw, fh = video_size(video)
    small = 2 * (MARGIN + SHIFT)
    if x < 0 or y < 0 or w <= small or h <= small or x + w > fw or y + h > fh:
        fail(f"crop {x},{y},{w},{h} must lie inside the {fw}x{fh} frame "
             f"and be over {small} px in each dimension")
    return x, y, w, h


class Audio:
    """|diff| of the mono track, and the map between sample index and time."""

    def __init__(self, video):
        p = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-copyts", "-i", video,
                 "-map", "0:a:0", "-af", "ashowinfo", "-ac", "1", "-ar", str(SR),
                 "-f", "f32le", "-"])
        info = re.findall(rb"\] n:\s*\d+ pts:\s*\S+ pts_time:(\S+) .*? rate:(\d+) nb_samples:(\d+)",
                          p.stderr)
        if not info:
            fail(f"{video}: no audio frames with timestamps")
        pts = np.array([float(t) for t, _, _ in info])
        dur = np.array([int(n) / int(r) for _, r, n in info])
        # Output samples are contiguous; each decoded frame starts at its own pts.
        self.start = np.concatenate([[0], np.cumsum(dur)[:-1]]) * SR
        self.pts = pts
        self.dur = dur
        drift = pts - (pts[0] + self.start / SR)
        if np.abs(drift).max() > 1e-3:
            print(f"warning: audio has gaps of up to {np.abs(drift).max() * 1000:.1f} ms; "
                  "timing follows its timestamps", file=sys.stderr)
        x = np.frombuffer(p.stdout, np.float32)
        self.hp = np.abs(np.diff(x))
        self.smooth = np.convolve(self.hp, np.ones(SMOOTH) / SMOOTH, "same")

    def time(self, n):
        k = np.clip(np.searchsorted(self.start, n, "right") - 1, 0, None)
        return self.pts[k] + (n - self.start[k]) / SR

    def sample(self, t):
        # A time in a gap between audio frames maps to the end of the frame
        # before it, not past it into the next frame's samples.
        k = np.clip(np.searchsorted(self.pts, t, "right") - 1, 0, None)
        return self.start[k] + np.minimum(t - self.pts[k], self.dur[k]) * SR


def read_video(video, crop):
    """Cropped gray frames and their timestamps, one per decoded frame."""
    x, y, w, h = crop
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-copyts", "-i", video,
             "-map", "0:v:0", "-vf", f"format=gray,crop={w}:{h}:{x}:{y}:exact=1,showinfo",
             "-fps_mode", "passthrough", "-f", "rawvideo", "-"])
    pts = re.findall(rb"\] n:\s*\d+ pts:\s*\S+ pts_time:(\S+)", p.stderr)
    frames = np.frombuffer(p.stdout, np.uint8)
    if len(frames) % (w * h):
        fail("decoded frames don't match the crop size")
    frames = frames.reshape(-1, h, w)
    if len(pts) != len(frames):
        fail(f"got {len(frames)} frames but {len(pts)} timestamps")
    return frames, np.array([float(t) for t in pts])


def frame_bins(audio, pts):
    """Per video frame: the loudest |diff| sample in its time span and its index."""
    dur = np.median(np.diff(pts)) if len(pts) > 1 else 1 / 30
    bounds = np.append(pts, pts[-1] + dur)
    s = np.clip(np.round(audio.sample(bounds)).astype(int), 0, len(audio.hp))
    env = np.zeros(len(pts))
    peak = np.zeros(len(pts), int)
    for i in range(len(pts)):
        if s[i + 1] > s[i]:
            j = int(np.argmax(audio.hp[s[i]:s[i + 1]]))
            env[i], peak[i] = audio.hp[s[i] + j], s[i] + j
    return env, peak


def find_clicks(env, lo, hi, ratio, merge, min_gap, local=61):
    """Clicks in frames lo..hi as (frame, loudness over the surrounding audio).

    Loudness is relative to a running median, so steady background noise
    doesn't hide quiet clicks. Sounds within min_gap frames of each other are
    one key stroke: the press is the first of them at least RELEASE times as
    loud as the loudest, since the release can be louder than the press but
    a finger brushing the key before it is much quieter.
    """
    pad = np.pad(env, local // 2, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(pad, local)
    rel = env / np.maximum(np.median(windows, axis=1), 1e-9)
    loud = [i for i in np.flatnonzero(rel > ratio) if lo <= i <= hi]
    groups = []
    for i in loud:
        if groups and i - groups[-1][-1] <= merge:
            groups[-1].append(i)
        else:
            groups.append([i])
    sounds = [g[int(np.argmax(rel[g]))] for g in groups]
    clicks = []
    while sounds:
        near = [s for s in sounds if s - sounds[0] < min_gap]
        top = max(rel[s] for s in near)
        press = next(s for s in near if rel[s] >= RELEASE * top)
        clicks.append((int(press), float(rel[press])))
        sounds = [s for s in sounds if s >= press + min_gap]
    return clicks


def click_onset(audio, anchor, frame_samples):
    """Sample where the sound containing the click's loudest sample starts.

    Walks back from that sample while the smoothed envelope stays above the
    threshold, bridging dips shorter than half a frame; a separate, earlier
    or later sound is never taken.
    """
    sm, fs = audio.smooth, int(frame_samples)
    before = sm[max(anchor - 30 * fs, 0):max(anchor - fs, 0)]
    noise = np.median(before) if len(before) else np.median(sm)
    peak = sm[max(anchor - SMOOTH, 0):anchor + SMOOTH + 1].max()
    thr = max(3 * noise, 0.2 * peak)
    lo = max(anchor - 3 * fs, 0)
    above = np.flatnonzero(sm[lo:anchor + 1] >= thr) + lo
    if not len(above) or anchor - above[-1] > fs // 2:
        return anchor
    gaps = np.flatnonzero(np.diff(above) > fs // 2)
    return int(above[gaps[-1] + 1] if len(gaps) else above[0])


def residual(frames, t, pixel_thr, m=MARGIN, r=SHIFT):
    """Changed-pixel count between frames t-1 and t, after aligning for camera shake."""
    cur = frames[t, m:-m, m:-m].astype(np.float32)
    h, w = frames.shape[1:]
    best = None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            prev = frames[t - 1, m + dy:h - m + dy, m + dx:w - m + dx].astype(np.float32)
            d = cur - prev
            s = np.abs(d).mean()
            if best is None or s < best[0]:
                best = (s, d)
    d = best[1]
    d -= np.median(d)  # global brightness steps (encoder, exposure)
    return int((np.abs(d) > pixel_thr).sum())


def text_frame(frames, onset, lo, hi, args):
    """First frame of the strongest change run after the click, or None."""
    first = max(math.ceil(onset + args.min_frames), lo, 1)
    last = min(math.floor(onset) + args.max_frames, hi)
    res = {t: residual(frames, t, args.pixel_threshold) for t in range(first, last + 1)}
    runs, run_ = [], []
    for t in range(first, last + 1):
        if res[t] >= args.threshold:
            run_.append(t)
        elif run_:
            runs.append(run_)
            run_ = []
    if run_:
        runs.append(run_)
    runs = [r for r in runs if max(res[t] for t in r) >= args.min_peak]
    if not runs:
        return None, res
    best = max(runs, key=lambda r: max(res[t] for t in r))
    peak = max(best, key=lambda t: res[t])
    floor = max(args.threshold, args.onset_fraction * res[peak])
    tf = peak
    while tf - 1 in res and res[tf - 1] >= floor:
        tf -= 1
    return tf, res


def write_png(img, path):
    h, w = img.shape
    run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
         "-s", f"{w}x{h}", "-i", "-", str(path)], input=img.tobytes())


def contact_sheet(frames, events, path, offsets=(-2, -1, 0, 1, 3)):
    """One row per event: frames around the detected change, 0 = detected frame."""
    h, w = frames.shape[1:]
    gap = 4
    rows = []
    for ev in events:
        tf = ev["text_frame"] if ev["text_frame"] is not None else round(ev["onset"]) + 8
        cells = []
        for o in offsets:
            t = min(max(tf + o, 0), len(frames) - 1)
            cell = frames[t].copy()
            if o == 0 and ev["text_frame"] is not None:
                cell[:3, :] = 255 - cell[:3, :]  # mark the detected frame
            cells.append(cell)
            cells.append(np.full((h, gap), 0, np.uint8))
        rows.append(np.hstack(cells))
        rows.append(np.full((gap, rows[-1].shape[1]), 0, np.uint8))
    write_png(np.vstack(rows), path)


def parse_pairs(items):
    out = {}
    for item in items or []:
        try:
            a, b = item.split("=")
            out[int(a)] = int(b)
        except ValueError:
            fail(f"--override takes CLICK=FRAME, got {item!r}")
    return out


def measure(args):
    crop = parse_crop(args.crop, args.video)
    audio = Audio(args.video)
    frames, pts = read_video(args.video, crop)
    n = len(frames)
    if n < 2:
        fail("the video has fewer than two frames")
    lo, hi = 1, n - 1
    if args.range:
        try:
            lo, hi = map(int, args.range.split(":"))
        except ValueError:
            fail(f"--range must be START:END, got {args.range!r}")
        if not 0 <= lo < hi:
            fail(f"bad --range {args.range}")
        if lo >= n:
            fail(f"--range starts after the last frame ({n - 1})")
        lo, hi = max(lo, 1), min(hi, n - 1)

    frame_dur = float(np.median(np.diff(pts)))
    frame_ms = frame_dur * 1000 / args.slowdown
    env, peaks = frame_bins(audio, pts)
    clicks = find_clicks(env, lo, hi, args.click_ratio, 3, args.min_gap)

    overrides = parse_pairs(args.override)
    skip = set(args.skip or [])
    ids = {c for c, _ in clicks}
    unknown = sorted((set(overrides) | skip) - ids)
    if unknown:
        fail(f"no click {', '.join(map(str, unknown))}; clicks found: "
             f"{' '.join(str(c) for c, _ in clicks) or 'none'}")

    events = []
    for c, loud in clicks:
        start = click_onset(audio, int(peaks[c]), frame_dur * SR)
        t_on = float(audio.time(start))
        onset = float(np.interp(t_on, pts, np.arange(n)))
        if c in overrides:
            tf, res = overrides[c], {}
            if not lo <= tf <= hi or pts[tf] <= t_on:
                fail(f"--override {c}={tf}: the frame must be in the range "
                     f"({lo}:{hi}) and after the click onset ({onset:.2f})")
        else:
            tf, res = text_frame(frames, onset, lo, hi, args)
        events.append({
            "click": int(c), "loudness": round(loud, 1),
            "onset": round(onset, 2), "onset_time": round(t_on, 6),
            "text_frame": tf, "text_time": float(pts[tf]) if tf is not None else None,
            "override": c in overrides, "skipped": c in skip,
            "latency_ms": round((pts[tf] - t_on) * 1000 / args.slowdown, 1)
            if tf is not None else None,
            "residuals": {str(k): v for k, v in res.items() if v}})

    used = [e["latency_ms"] for e in events if e["latency_ms"] is not None and not e["skipped"]]
    print(f"{'click':>6} {'loud':>6} {'onset':>9} {'text':>6} {'latency':>8}")
    for e in events:
        note = " (set by hand)" if e["override"] else ""
        note += " (skipped)" if e["skipped"] else ""
        if e["text_frame"] is None:
            note += " no text change"
        lat = f"{e['latency_ms']:6.1f}ms" if e["latency_ms"] is not None else "       -"
        tf = e["text_frame"] if e["text_frame"] is not None else "-"
        print(f"{e['click']:>6} {e['loudness']:>6} {e['onset']:>9} {tf:>6} {lat}{note}")
    if not events:
        print("no clicks found in the range")
    summary = None
    if used:
        a = np.array(used)
        summary = {"n": len(a), "mean": round(float(a.mean()), 1),
                   "median": round(float(np.median(a)), 1),
                   "sd": round(float(a.std(ddof=1)), 1) if len(a) > 1 else None,
                   "min": float(a.min()), "max": float(a.max())}
        print(f"\nn={summary['n']} mean={summary['mean']} median={summary['median']} "
              f"sd={summary['sd']} min={summary['min']} max={summary['max']} ms")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = args.label or Path(args.video).stem
    sheet = out / f"{name}-sheet.png"
    sheet.unlink(missing_ok=True)
    if events:
        contact_sheet(frames, events, sheet)
    settings = {k: v for k, v in vars(args).items() if k not in ("func", "cmd")}
    meta = {"video": Path(args.video).name, "label": name, "settings": settings,
            "crop": crop, "range": [lo, hi], "frames": n, "frame_ms": frame_ms,
            "summary": summary, "events": events}
    (out / f"{name}.json").write_text(json.dumps(meta, indent=2))
    if events:
        print(f"\ncontact sheet: {sheet}")
    print(f"results: {out / (name + '.json')}")


def frame(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{Path(args.video).stem}-frame{args.at}.png"
    if args.at < 0:
        fail("--at must be 0 or more")
    vf = f"select=eq(n\\,{args.at}),format=rgb24,drawgrid=w=100:h=100:t=1:c=red@0.6"
    if args.crop:
        x, y, w, h = parse_crop(args.crop, args.video)
        vf += f",drawbox=x={x}:y={y}:w={w}:h={h}:t=2:c=lime"
    path.unlink(missing_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", args.video, "-map", "0:v:0", "-vf", vf,
         "-fps_mode", "passthrough", "-frames:v", "1", str(path)])
    if not path.exists():
        fail(f"the video has no frame {args.at}")
    print(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("frame", help="save a frame with a 100 px grid, to pick the crop")
    f.add_argument("video")
    f.add_argument("--at", type=int, default=300,
                   help="frame number, counting decoded frames from 0")
    f.add_argument("--crop", help="X,Y,W,H to preview as a green box")
    f.add_argument("--out", default="out")
    f.set_defaults(func=frame)

    m = sub.add_parser("measure", help="measure click-to-text latency")
    m.add_argument("video")
    m.add_argument("--crop", required=True, help="X,Y,W,H around the typed line, with margin")
    m.add_argument("--range", help="START:END frames of the slow-motion part, inclusive")
    m.add_argument("--label", help="name for output files")
    m.add_argument("--out", default="out")
    m.add_argument("--slowdown", type=float, default=8, help="capture fps / file fps")
    m.add_argument("--click-ratio", type=float, default=2.5,
                   help="click loudness over the surrounding audio")
    m.add_argument("--pixel-threshold", type=float, default=40,
                   help="gray level change counting a pixel as changed")
    m.add_argument("--threshold", type=int, default=8,
                   help="changed pixels that count a frame as changing")
    m.add_argument("--onset-fraction", type=float, default=0.15,
                   help="a change starts at the first frame with this share of its peak")
    m.add_argument("--min-peak", type=int, default=30,
                   help="changed pixels the strongest frame of a change needs")
    m.add_argument("--min-gap", type=int, default=40,
                   help="frames within which sounds are one key stroke (press and release)")
    m.add_argument("--min-frames", type=float, default=1,
                   help="frames after the click onset before a change counts (1 = 4.2 ms at 240 fps)")
    m.add_argument("--max-frames", type=int, default=32,
                   help="latest text frame after the click")
    m.add_argument("--override", nargs="*", metavar="CLICK=FRAME",
                   help="set the text frame for a click by hand")
    m.add_argument("--skip", nargs="*", type=int, metavar="CLICK",
                   help="leave clicks out of the summary")
    m.set_defaults(func=measure)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
