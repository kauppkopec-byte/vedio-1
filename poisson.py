"""生成「人生如泊松分布」视频。

画面：深色背景、衬线标题、金色高亮与数据图表（参考数据可视化短片的风格），
由 poisson/scene.html 在无头 Chromium 中逐帧绘制；配乐与「叮」声由本脚本合成，
每一声都对齐画面里一次随机事件的出现。

用法: python3 poisson.py  ->  output/poisson.mp4
依赖: numpy, ffmpeg, Node.js + Playwright（Chromium）；字体首次运行时从 Google Fonts 下载
"""
import json
import os
import re
import subprocess
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE_DIR = os.path.join(HERE, "poisson")
FONT_DIR = os.path.join(SCENE_DIR, "fonts")
BUILD = os.path.join(SCENE_DIR, "build")
OUT = os.path.join(HERE, "output", "poisson.mp4")

SR = 44100
WORKERS = max(1, min(4, os.cpu_count() or 1))

FONTS = {
    "NotoSerifSC-700.ttf": "Noto+Serif+SC:wght@700",
    "NotoSerifSC-900.ttf": "Noto+Serif+SC:wght@900",
    "NotoSansSC-400.ttf": "Noto+Sans+SC:wght@400",
    "JetBrainsMono-400.ttf": "JetBrains+Mono:wght@400",
    "JetBrainsMono-500.ttf": "JetBrains+Mono:wght@500",
}

rng = np.random.default_rng(3)


# ---------- 字体 ----------

def ensure_fonts():
    os.makedirs(FONT_DIR, exist_ok=True)
    for name, family in FONTS.items():
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            continue
        css = subprocess.run(["curl", "-sSf", f"https://fonts.googleapis.com/css2?family={family}"],
                             check=True, capture_output=True, text=True).stdout
        url = re.search(r"url\((https://[^)]+\.ttf)\)", css).group(1)
        subprocess.run(["curl", "-sSf", "-o", path, url], check=True)
        print("font:", name)


# ---------- 配乐 ----------

PENTA = [77, 79, 81, 84, 86, 89, 91, 93, 96]  # F 大调五声音阶，F5 起


def mtof(m):
    return 440 * 2 ** ((m - 69) / 12)


def bell(freq, gain):
    """柔和的钟声：几组非整数倍泛音，各自衰减。"""
    t = np.arange(int(3.5 * SR)) / SR
    sig = np.zeros_like(t)
    for ratio, amp, decay in ((1, 1.0, 2.2), (2.0, 0.32, 1.4), (2.76, 0.18, 0.9), (4.07, 0.08, 0.5), (5.4, 0.04, 0.35)):
        sig += amp * np.exp(-t / decay) * np.sin(2 * np.pi * freq * ratio * t)
    return gain * np.minimum(1, t / 0.004) * sig


def tick(gain):
    t = np.arange(int(0.08 * SR)) / SR
    tone = np.sin(2 * np.pi * 1900 * t) * np.exp(-t / 0.012)
    noise = rng.normal(0, 1, len(t)) * np.exp(-t / 0.004)
    return gain * (0.6 * tone + 0.15 * noise)


def swell(dur, gain):
    t = np.arange(int(dur * SR)) / SR
    noise = np.convolve(rng.normal(0, 1, len(t)), np.ones(60) / 60, mode="same")
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return gain * env * (2.5 * noise + 0.35 * np.sin(2 * np.pi * 87.3 * t))


def low(gain):
    t = np.arange(int(3.0 * SR)) / SR
    sig = np.sin(2 * np.pi * 43.65 * t) + 0.5 * np.sin(2 * np.pi * 87.3 * t)
    return gain * np.minimum(1, t / 0.01) * np.exp(-t / 1.2) * sig


def pad_note(freq, dur, amp):
    t = np.arange(int(dur * SR)) / SR
    env = np.minimum(1, t / 2.5) * np.clip((dur - t) / 3.0, 0, 1)
    sig = np.zeros_like(t)
    for det in (-0.0018, 0.0018):
        for h in (1, 2, 3, 4):
            sig += np.sin(2 * np.pi * freq * h * (1 + det) * t + h) / h ** 2
    return amp * env * sig / 2


def reverb(x, seconds=3.4):
    """指数衰减噪声做冲激响应，FFT 卷积得到左右两路混响。"""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    X = np.fft.rfft(x, size)
    out = []
    for seed in (11, 12):
        ir = np.random.default_rng(seed).normal(0, 1, n) * np.exp(-t * 6.9 / seconds)
        ir = np.convolve(ir, np.ones(12) / 12, mode="same")
        ir /= np.sqrt(np.sum(ir ** 2))
        out.append(np.fft.irfft(X * np.fft.rfft(ir, size), size)[: len(x)])
    return np.stack(out, axis=1)


def make_audio(info, path):
    dur = info["duration"]
    n = int((dur + 1) * SR)
    dry = np.zeros((n, 2))

    def add(sig, at, pan=0.0):
        s = int(at * SR)
        e = min(n, s + len(sig))
        if e <= s:
            return
        dry[s:e, 0] += sig[: e - s] * np.sqrt(0.5 * (1 - pan))
        dry[s:e, 1] += sig[: e - s] * np.sqrt(0.5 * (1 + pan))

    # 铺底和弦：Dm9 - B♭maj7 - Fmaj7 - Csus2 循环，结尾落到 B♭ - C - F
    finale = info["sceneStarts"][-1]
    loop = [[50, 57, 60, 64, 65], [46, 53, 57, 62, 65], [41, 53, 57, 60, 64], [48, 55, 60, 62, 67]]
    chords, at, i = [], 0.0, 0
    while at < finale - 1:
        chords.append((at, loop[i % 4]))
        at += 8.0
        i += 1
    chords += [(finale, [46, 53, 58, 62, 65]), (finale + 6.4, [48, 55, 60, 64, 67]),
               (finale + 12.8, [41, 53, 57, 60, 65, 67])]
    for j, (at, notes) in enumerate(chords):
        end = chords[j + 1][0] if j + 1 < len(chords) else dur
        for m in notes:
            add(pad_note(mtof(m), end - at + 3.0, 0.032), at)
        add(pad_note(mtof(notes[0] - 12), end - at + 3.0, 0.05), at)

    for c in info["cues"]:
        pan = rng.uniform(-0.4, 0.4)
        if c["kind"] == "chime":
            m = PENTA[c.get("note", 0) % len(PENTA)] + 12 * c.get("oct", 0)
            add(bell(mtof(m), 0.16 * c.get("gain", 0.5)), c["t"], pan)
        elif c["kind"] == "tick":
            add(tick(0.12 * c.get("gain", 0.3)), c["t"], pan)
        elif c["kind"] == "swell":
            add(swell(c.get("dur", 2.5), 0.08 * c.get("gain", 0.5)), max(0, c["t"] - 0.8))
        elif c["kind"] == "low":
            add(low(0.18 * c.get("gain", 0.8)), c["t"])

    out = dry + 0.42 * reverb(dry.mean(axis=1))
    out = out[: int(dur * SR)]
    times = np.arange(len(out)) / SR
    out *= (np.minimum(1, times / 1.0) * np.clip((dur - times) / 2.5, 0, 1))[:, None]
    out *= 0.89 / (np.max(np.abs(out)) + 1e-9)
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------- 主程序 ----------

def node(*args):
    subprocess.run(["node", os.path.join(SCENE_DIR, "render.cjs"), *args], check=True)


def main():
    ensure_fonts()
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    node("info", BUILD)
    with open(os.path.join(BUILD, "cues.json")) as f:
        info = json.load(f)
    wav = os.path.join(BUILD, "audio.wav")
    make_audio(info, wav)
    print("audio done")

    node("video", BUILD, str(WORKERS))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", os.path.join(BUILD, "segments.txt"),
                    "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", OUT], check=True)
    print("done:", OUT)


if __name__ == "__main__":
    main()
