"""生成主题为「坚持」的 10 秒短视频。

画面：夜色中一个小人沿山脊一步步向上攀登，途中遭遇风雨，
最终在日出时登顶。全部画面与配乐均由代码程序化生成。

用法: python3 generate.py  ->  output/persistence.mp4
依赖: numpy, Pillow, ffmpeg
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30
DURATION = 10.0
N_FRAMES = int(FPS * DURATION)
SR = 44100

FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

rng = np.random.default_rng(7)


# ---------- 工具函数 ----------

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def fade(t, start, end, fin=0.5, fout=0.5):
    """在 [start, end] 区间内淡入淡出的透明度。"""
    if t < start or t > end:
        return 0.0
    return smooth((t - start) / fin) * smooth((end - t) / fout) if fout else smooth((t - start) / fin)


def keyframes(t, frames):
    """frames: [(time, color), ...]，按时间插值颜色。"""
    if t <= frames[0][0]:
        return frames[0][1]
    for (t0, c0), (t1, c1) in zip(frames, frames[1:]):
        if t <= t1:
            return lerp_color(c0, c1, smooth((t - t0) / (t1 - t0)))
    return frames[-1][1]


# ---------- 场景元素 ----------

SKY_TOP = [(0, (8, 12, 32)), (4.5, (14, 20, 44)), (7.0, (20, 26, 52)),
           (8.2, (52, 70, 130)), (10, (84, 128, 190))]
SKY_BOT = [(0, (24, 36, 72)), (4.5, (30, 40, 70)), (7.0, (60, 50, 80)),
           (8.2, (240, 150, 100)), (10, (255, 214, 160))]

YS = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]


def sky(t):
    top = np.array(keyframes(t, SKY_TOP), dtype=np.float32)
    bot = np.array(keyframes(t, SKY_BOT), dtype=np.float32)
    grad = top * (1 - YS) + bot * YS
    return np.broadcast_to(grad, (H, W, 3)).astype(np.uint8)


def ridge(xs, base, amp, seed, peak_x=None, peak_y=None):
    r = np.random.default_rng(seed)
    y = np.full_like(xs, base, dtype=np.float64)
    for k in range(1, 6):
        y += amp / k * np.sin(xs / W * math.pi * (k + r.random() * 2) + r.random() * 6)
    if peak_x is not None:
        # 主峰：从左下方逐渐抬升到峰顶，再向右回落
        d = (xs - peak_x) / W
        shape = np.where(d < 0, 1 - (np.abs(d) / 0.62) ** 1.1, 1 - (np.abs(d) / 0.42) ** 1.3)
        shape = np.clip(shape, 0, 1)
        y = lerp(980, peak_y, shape) + (y - base) * 0.25 * (1 - shape)
    return y


XS = np.arange(W + 1, dtype=np.float64)
FAR = ridge(XS, 620, 60, 1)
MID = ridge(XS, 760, 45, 2)
PEAK_X, PEAK_Y = 1190.0, 360.0
MAIN = ridge(XS, 900, 30, 3, PEAK_X, PEAK_Y)


def main_y(x):
    return float(np.interp(x, XS, MAIN))


STARS = [(rng.uniform(0, W), rng.uniform(0, H * 0.6), rng.uniform(0.6, 2.2), rng.uniform(0, 6.28))
         for _ in range(180)]
RAIN = [(rng.uniform(-200, W + 200), rng.uniform(0, H), rng.uniform(900, 1500), rng.uniform(25, 55))
        for _ in range(420)]


def climber_pos(t):
    """小人沿主山脊攀登，最后停在峰顶。"""
    p = smooth(t / 8.6) * 0.85 + clamp(t / 8.6) * 0.15
    x = lerp(160, PEAK_X, clamp(p))
    return x, main_y(x)


def draw_climber(d, x, y, t, color):
    walking = t < 8.6
    phase = t * 2 * math.pi * 1.6
    swing = math.sin(phase) * 0.45 if walking else 0.0
    bob = abs(math.sin(phase)) * 3 if walking else 0.0
    s = 1.0
    hip = (x, y - 34 * s - bob)
    neck = (x + (4 if walking else 0), y - 66 * s - bob)
    head = (neck[0] + (2 if walking else 0), neck[1] - 13 * s)
    lw = 7
    # 腿
    for sgn in (1, -1):
        a = sgn * swing
        foot = (hip[0] + math.sin(a) * 36 * s, hip[1] + math.cos(a) * 34 * s)
        d.line([hip, foot], fill=color, width=lw)
    d.line([hip, neck], fill=color, width=lw + 1)
    if walking:
        for sgn in (1, -1):
            a = -sgn * swing * 0.8 + 0.2
            hand = (neck[0] + math.sin(a) * 26, neck[1] + 6 + math.cos(a) * 26)
            d.line([(neck[0], neck[1] + 6), hand], fill=color, width=lw - 1)
    else:
        # 登顶：张开双臂
        raise_t = smooth((t - 8.6) / 0.6)
        for sgn in (1, -1):
            ang = lerp(0.3, 2.3, raise_t)
            hand = (neck[0] + sgn * math.sin(ang) * 30, neck[1] + 6 + math.cos(ang) * 30)
            d.line([(neck[0], neck[1] + 6), hand], fill=color, width=lw - 1)
    d.ellipse([head[0] - 11, head[1] - 11, head[0] + 11, head[1] + 11], fill=color)
    # 小旗：登顶后插上
    if t > 8.8:
        k = smooth((t - 8.8) / 0.4)
        fx = x + 46
        fy = main_y(fx)
        top = fy - 90 * k
        d.line([(fx, fy), (fx, top)], fill=color, width=4)
        wave_ = math.sin(t * 9) * 4
        d.polygon([(fx, top), (fx + 42 * k, top + 12 + wave_), (fx, top + 26 * k)], fill=(214, 64, 52))


# ---------- 文字 ----------

FONTS = {}


def font(size):
    if size not in FONTS:
        FONTS[size] = ImageFont.truetype(FONT_PATH, size)
    return FONTS[size]


CAPTIONS = [
    # (开始, 结束, 文本, 字号, x(None=居中), y, 字间距)
    (0.4, 2.9, "一步", 84, None, 190, 24),
    (2.7, 5.0, "又一步", 84, None, 190, 24),
    (4.9, 7.5, "风雨 也不停下", 72, None, 190, 16),
    (7.8, 10.0, "坚持", 200, 200, 230, 50),
    (8.5, 10.0, "终会看见光", 60, 212, 480, 22),
]


def draw_text_layer(t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for start, end, text, size, x0, y, spacing in CAPTIONS:
        fout = 0.5 if end < DURATION else 0
        a = fade(t, start, end, 0.6, fout)
        if a <= 0:
            continue
        f = font(size)
        widths = [d.textlength(ch, font=f) for ch in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = (W - total) / 2 if x0 is None else x0
        rise = (1 - smooth((t - start) / 0.8)) * 24
        for ch, w in zip(text, widths):
            d.text((x, y + rise), ch, font=f, fill=(255, 248, 235, int(255 * a)))
            x += w + spacing
    glow = layer.filter(ImageFilter.GaussianBlur(14))
    return glow, layer


# ---------- 渲染一帧 ----------

def render(i):
    t = i / FPS
    img = Image.fromarray(sky(t)).convert("RGBA")
    d = ImageDraw.Draw(img)

    # 星星：天亮后渐隐
    star_a = 1 - smooth((t - 6.8) / 1.6)
    if star_a > 0:
        for sx, sy, r, ph in STARS:
            tw = 0.55 + 0.45 * math.sin(t * 3 + ph)
            v = int(255 * star_a * tw)
            d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 255, 240, v))

    # 太阳：从主峰背后升起
    if t > 6.6:
        k = smooth((t - 6.6) / 3.2)
        sx, sy = PEAK_X + 40, lerp(620, 250, k)
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        for rr, al in ((340, 40), (220, 70), (140, 120)):
            g.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], fill=(255, 200, 120, int(al * k)))
        glow = glow.filter(ImageFilter.GaussianBlur(60))
        img.alpha_composite(glow)
        d = ImageDraw.Draw(img)
        d.ellipse([sx - 85, sy - 85, sx + 85, sy + 85], fill=(255, 236, 190, int(255 * smooth(k * 3))))

    # 山峦（三层，越近越暗）
    light = smooth((t - 6.8) / 3.0)
    far_c = lerp_color((34, 44, 78), (150, 120, 140), light)
    mid_c = lerp_color((22, 28, 54), (96, 70, 96), light)
    main_c = lerp_color((10, 12, 26), (40, 28, 44), light)
    for ys, c in ((FAR, far_c), (MID, mid_c), (MAIN, main_c)):
        pts = [(0, H)] + [(x, ys[x]) for x in range(0, W + 1, 8)] + [(W, H)]
        d.polygon(pts, fill=c)

    # 已走过的足迹：一串微光
    cx, cy = climber_pos(t)
    for px in np.arange(180, cx - 30, 46):
        py = main_y(px)
        d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(255, 210, 140, 150))

    draw_climber(d, cx, cy, t, (6, 6, 12) if light > 0.3 else (230, 225, 210))

    # 风雨
    rain_a = fade(t, 4.6, 7.4, 0.6, 0.8)
    if rain_a > 0:
        rain = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        rd = ImageDraw.Draw(rain)
        for rx, ry, speed, ln in RAIN:
            y = (ry + speed * t) % (H + 100) - 50
            x = rx - (speed * t * 0.25) % (W + 400) + 200
            x = (x + 200) % (W + 400) - 200
            rd.line([(x, y), (x - ln * 0.3, y + ln)], fill=(190, 205, 235, int(130 * rain_a)), width=2)
        # 雨中整体压暗，偶有闪电
        flash = 0.0
        if 5.55 < t < 5.75:
            flash = 1 - abs(t - 5.62) / 0.13
        overlay = (220, 225, 255, int(90 * clamp(flash))) if flash > 0 else (10, 14, 30, int(70 * rain_a))
        img.alpha_composite(Image.new("RGBA", (W, H), overlay))
        img.alpha_composite(rain)

    glow, text = draw_text_layer(t)
    img.alpha_composite(glow)
    img.alpha_composite(text)

    # 暗角 + 片头片尾淡入淡出
    img = Image.alpha_composite(img, VIGNETTE)
    out = np.asarray(img.convert("RGB"), dtype=np.float32)
    k = smooth(t / 0.6) * smooth((DURATION - t) / 0.5)
    return (out * k).astype(np.uint8)


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    a = np.clip((r - 0.7) / 0.7, 0, 1) ** 1.5 * 170
    v = np.zeros((H, W, 4), dtype=np.uint8)
    v[..., 3] = a.astype(np.uint8)
    return Image.fromarray(v, "RGBA")


VIGNETTE = make_vignette()


# ---------- 配乐 ----------

def note(freq, dur, amp=0.2, attack=0.4, release=0.8):
    tt = np.arange(int(dur * SR)) / SR
    env = np.minimum(1, tt / attack) * np.minimum(1, (dur - tt) / release).clip(0)
    sig = sum(np.sin(2 * np.pi * freq * h * tt) / h ** 1.6 for h in (1, 2, 3, 4))
    return amp * env * sig


def mtof(m):
    return 440 * 2 ** ((m - 69) / 12)


def make_audio(path):
    n = int(DURATION * SR)
    buf = np.zeros(n + SR)

    def add(sig, at):
        s = int(at * SR)
        buf[s:s + len(sig)] += sig[: len(buf) - s]

    # 和弦进行 Am - F - C - G - C（逐渐明亮）
    chords = [(0.0, [57, 60, 64]), (2.5, [53, 57, 60]), (5.0, [48, 55, 64]),
              (7.0, [55, 59, 62]), (8.0, [48, 55, 60, 64, 72])]
    for i, (at, ch) in enumerate(chords):
        end = chords[i + 1][0] if i + 1 < len(chords) else DURATION
        for m in ch:
            add(note(mtof(m), end - at + 0.6, 0.06, 0.5, 0.9), at)
        add(note(mtof(ch[0] - 12), end - at + 0.6, 0.08, 0.3, 0.9), at)

    # 脚步：随攀登节奏的轻柔鼓点
    step = 1 / 1.6 / 2
    tt = np.arange(int(0.25 * SR)) / SR
    thump = 0.35 * np.sin(2 * np.pi * (70 - 80 * tt) * tt) * np.exp(-tt * 22)
    k = 0.6
    while k < 8.6:
        add(thump * (0.5 + 0.5 * k / 8.6), k)
        k += step

    # 钢琴旋律（登顶）
    melody = [(8.0, 72), (8.35, 76), (8.7, 79), (9.05, 84)]
    for at, m in melody:
        add(note(mtof(m), 1.4, 0.12, 0.01, 1.2), at)

    # 雨声
    noise = rng.normal(0, 1, n)
    noise = np.convolve(noise, np.ones(6) / 6, mode="same")
    times = np.arange(n) / SR
    rain_env = np.array([fade(x, 4.6, 7.4, 0.6, 0.8) for x in times[::441]])
    rain_env = np.interp(times, times[::441], rain_env)
    buf[:n] += noise * rain_env * 0.08

    buf = buf[:n]
    fade_env = np.minimum(1, times / 0.5) * np.minimum(1, (DURATION - times) / 0.8)
    buf *= fade_env
    buf /= np.max(np.abs(buf)) + 1e-9
    buf *= 0.8
    pcm = (buf * 32767).astype(np.int16)
    stereo = np.stack([pcm, pcm], axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


# ---------- 主程序 ----------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    wav = os.path.join(OUT_DIR, "_audio.wav")
    make_audio(wav)
    out = os.path.join(OUT_DIR, "persistence.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(N_FRAMES):
        proc.stdin.write(render(i).tobytes())
        if i % 30 == 0:
            print(f"frame {i}/{N_FRAMES}")
    proc.stdin.close()
    proc.wait()
    os.remove(wav)
    print("done:", out)


if __name__ == "__main__":
    main()
