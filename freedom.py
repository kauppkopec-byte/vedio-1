"""生成主题为「必须花的钱」的 33 秒短视频。

观点：决定你自由的，不是你赚多少，而是你必须花多少。

风格：一页账本。米白纸面、墨色宋体，红色只留给"剩下的钱"和
"这笔钱买到的时间"。不用比喻，只让两个人的账自己说话：
  一  A 月入三万，B 月入八千，开销一块块落进各自的容器
  二  两人各存一年
  三  这笔钱能让人停下来多久：A 26 天，B 12 个月
  四  结论

用法: python3 freedom.py  ->  output/freedom.mp4
依赖: numpy, Pillow, ffmpeg
字体: fonts/ 下的思源宋体（Noto Serif SC，SIL OFL 1.1）
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30
DURATION = 33.0
N_FRAMES = int(FPS * DURATION)
SR = 44100

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_PATHS = {400: os.path.join(ROOT, "fonts", "NotoSerifSC-400.woff2"),
              700: os.path.join(ROOT, "fonts", "NotoSerifSC-700.woff2")}
OUT_DIR = os.path.join(ROOT, "output")

PAPER = (241, 236, 226)
INK = (30, 28, 25)
SOFT_INK = (78, 73, 66)
GRAY = (138, 131, 120)
FAINT = (212, 205, 193)
RED = (176, 50, 38)
SHADES = [(44, 41, 37), (84, 79, 72), (118, 112, 103)]


# ---------- 工具函数 ----------

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


def appear(t, t0, dur=0.5):
    return smooth((t - t0) / dur)


def window(t, t0, t1, fin=0.5, fout=0.6):
    """t0 淡入、t1 开始淡出的透明度。"""
    return smooth((t - t0) / fin) * (1 - smooth((t - t1) / fout))


# ---------- 纸面 ----------

def make_paper():
    r = np.random.default_rng(3)
    img = np.empty((H, W, 3), np.float32)
    img[:] = PAPER
    img += r.normal(0, 2.6, (H, W, 1))
    blot = r.normal(128, 50, (H // 24, W // 24)).clip(0, 255).astype(np.uint8)
    blot = Image.fromarray(blot).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(40))
    img += (np.asarray(blot, np.float32)[..., None] - 128) / 128 * 5
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
    img -= (v * 9)[..., None]
    # 账本横格与红色页边线
    for y in range(126, H - 40, 62):
        img[y] -= 7
    for x in (128, 134):
        img[:, x] = img[:, x] * 0.7 + np.array(RED, np.float32) * 0.3
    return Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")


# ---------- 文字 ----------

_FONTS, _TEXTS = {}, {}


def font(size, weight):
    key = (size, weight)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(FONT_PATHS[weight], size)
    return _FONTS[key]


def text_width(s, size, weight=400, spacing=0):
    f = font(size, weight)
    return sum(f.getlength(ch) for ch in s) + spacing * (len(s) - 1)


def text_img(s, size, weight, color, spacing):
    key = (s, size, weight, color, spacing)
    if key not in _TEXTS:
        f = font(size, weight)
        asc, desc = f.getmetrics()
        im = Image.new("RGBA", (int(text_width(s, size, weight, spacing)) + 8, asc + desc), color + (0,))
        d = ImageDraw.Draw(im)
        x = 2
        for ch in s:
            d.text((x, asc), ch, font=f, fill=color + (255,), anchor="ls")
            x += f.getlength(ch) + spacing
        _TEXTS[key] = (im, asc)
    return _TEXTS[key]


def paste(canvas, im, x, y, alpha=1.0, reveal=1.0):
    """把 RGBA 图贴到画布上，alpha 为整体透明度，reveal 为从左到右的书写进度。"""
    if alpha <= 0.003 or reveal <= 0:
        return
    arr = np.array(im)
    a = arr[..., 3].astype(np.float32) * alpha
    if reveal < 1:
        soft = 60.0
        m = np.clip((reveal * (arr.shape[1] + soft) - np.arange(arr.shape[1])) / soft, 0, 1)
        a *= m[None, :]
    arr[..., 3] = a.astype(np.uint8)
    x, y = int(round(x)), int(round(y))
    if x < 0 or y < 0:
        arr = arr[max(0, -y):, max(0, -x):]
        x, y = max(0, x), max(0, y)
    canvas.alpha_composite(Image.fromarray(arr), (x, y))


def text(canvas, s, x, y, size, weight=400, color=INK, alpha=1.0, anchor="l",
         spacing=0, reveal=1.0, rise=0.0):
    """(x, y) 为基线位置；anchor 取 l / m / r。"""
    im, asc = text_img(s, size, weight, color, spacing)
    if anchor == "m":
        x -= im.width / 2
    elif anchor == "r":
        x -= im.width
    paste(canvas, im, x, y - asc + rise, alpha, reveal)


def label(canvas, s, x, y, size, t, t0, weight=400, color=INK, anchor="l", dur=0.5, alpha=1.0):
    """淡入并轻微上浮的文字。"""
    p = appear(t, t0, dur)
    text(canvas, s, x, y, size, weight, color, p * alpha, anchor, rise=(1 - p) * 12)


# ---------- 抗锯齿小图形 ----------

def make_dot(r, color):
    k = 4
    im = Image.new("RGBA", (2 * r * k + 4 * k, 2 * r * k + 4 * k), color + (0,))
    ImageDraw.Draw(im).ellipse([2 * k, 2 * k, 2 * k + 2 * r * k, 2 * k + 2 * r * k], fill=color + (255,))
    return im.resize((im.width // k, im.height // k), Image.LANCZOS)


def make_hatch():
    k = 2
    im = Image.new("RGBA", (400 * k, 400 * k), RED + (0,))
    d = ImageDraw.Draw(im)
    for i in range(-400 * k, 800 * k, 13 * k):
        d.line([(i, 400 * k), (i + 400 * k, 0)], fill=RED + (150,), width=2 * k)
    return im.resize((400, 400), Image.LANCZOS)


DOT_RED = make_dot(9, RED)
DOT_END = make_dot(7, RED)
HATCH = make_hatch()


def dot(canvas, img, x, y, alpha=1.0):
    paste(canvas, img, x - img.width / 2, y - img.height / 2, alpha)


# ---------- 第一、二段：两个人的一个月 ----------

BASE_Y = 930
SCALE = 0.0225  # 每元对应的像素高度
BAR_W = 250
DROP_T, FALL, STEP = 0.45, 0.45, 0.62

BARS = [
    dict(name="A", x=470, income=30000, t_label=0.6, t_outline=1.0, t_blocks=2.2,
         blocks=[("房贷", 12000), ("车贷", 4000), ("孩子的课", 3500),
                 ("物业水电", 1500), ("保险", 1500), ("吃穿日用", 5500)]),
    dict(name="B", x=1240, income=8000, t_label=7.4, t_outline=7.8, t_blocks=8.7,
         blocks=[("房租", 1800), ("吃穿日用", 1700), ("交通通讯", 500)]),
]
for b in BARS:
    b["top"] = BASE_Y - b["income"] * SCALE
    b["spent"] = sum(a for _, a in b["blocks"])
    b["left"] = b["income"] - b["spent"]
    b["t_left"] = b["t_blocks"] + (len(b["blocks"]) - 1) * STEP + FALL + 0.45
    # 右侧标注的纵向位置：从下往上排，避免挤在一起
    ys, cum = [], 0
    for _, amt in b["blocks"]:
        yc = BASE_Y - (cum + amt / 2) * SCALE
        if ys and yc > ys[-1] - 40:
            yc = ys[-1] - 40
        ys.append(yc)
        cum += amt
    b["label_ys"] = ys
    b["left_y"] = min(BASE_Y - (b["spent"] + b["left"] / 2) * SCALE, ys[-1] - 52)

T_YEAR = 12.2       # 「各自存一年」
T_COUNT = 12.9      # 一年存款计数
T_PART1_OUT = 15.8  # 第一段淡出


def polyline_partial(pts, p):
    lens = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    target = sum(lens) * clamp(p)
    out = [pts[0]]
    for (a, b), ln in zip(zip(pts, pts[1:]), lens):
        if target >= ln:
            out.append(b)
            target -= ln
        else:
            k = target / ln if ln else 0
            out.append((lerp(a[0], b[0], k), lerp(a[1], b[1], k)))
            break
    return out


def draw_bar(L, t, b):
    d = ImageDraw.Draw(L)
    x, top = b["x"], b["top"]
    dim = 1 - 0.72 * smooth((t - T_COUNT + 0.3) / 0.8)  # 第二段：开销退到背景
    lx = x + BAR_W + 48

    label(L, b["name"], x - 4, top - 44, 64, t, b["t_label"], 700)
    label(L, f"月入 {b['income']:,}", x + 56, top - 44, 34, t, b["t_label"] + 0.15, 400, SOFT_INK)

    # 敞口的容器：左壁、底、右壁
    po = smooth((t - b["t_outline"]) / 0.9)
    if po > 0:
        pts = [(x - 4, top), (x - 4, BASE_Y + 3), (x + BAR_W + 3, BASE_Y + 3), (x + BAR_W + 3, top)]
        d.line(polyline_partial(pts, po), fill=INK + (255,), width=3, joint="curve")

    cum = 0
    for i, (name, amt) in enumerate(b["blocks"]):
        y1 = BASE_Y - cum * SCALE
        y0 = BASE_Y - (cum + amt) * SCALE
        cum += amt
        t0 = b["t_blocks"] + i * STEP
        if t < t0:
            continue
        p = clamp((t - t0) / FALL)
        drop = y0 - (top - 150 - (y1 - y0))
        off = -(1 - p * p) * drop
        if p >= 1:
            off = -math.sin(math.pi * clamp((t - t0 - FALL) / 0.18)) * 5
        a = int(255 * smooth(p / 0.3))
        shade = SHADES[i % len(SHADES)]
        # 方块从容器口落入，不越过上方的标题
        ry0, ry1 = max(y0 + off + 1, top), y1 + off - 1
        if ry1 > ry0:
            d.rectangle([x + 2, ry0, x + BAR_W - 2, ry1], fill=shade + (a,))

        ly = b["label_ys"][i]
        la = appear(t, t0 + FALL, 0.3) * lerp(1, 0.55, 1 - dim)
        if la > 0:
            yc = (y0 + y1) / 2
            c = SOFT_INK + (int(140 * la),)
            d.line([(x + BAR_W + 10, yc), (x + BAR_W + 26, yc), (lx - 12, ly)], fill=c, width=1)
            text(L, name, lx, ly + 9, 26, 400, SOFT_INK, la)
            text(L, f"{amt:,}", lx + 230, ly + 9, 26, 400, SOFT_INK, la, "r")

    # 剩下的钱：红笔斜线
    pl = appear(t, b["t_left"], 0.5)
    if pl > 0:
        y0 = BASE_Y - b["income"] * SCALE
        y1 = BASE_Y - b["spent"] * SCALE
        h = int(y1 - y0)
        paste(L, HATCH.crop((0, 0, BAR_W - 4, h)), x + 2, y0, pl)
        d.rectangle([x + 2, y0, x + BAR_W - 2, y1 - 1], outline=RED + (int(255 * pl),), width=3)
        yc = (y0 + y1) / 2
        d.line([(x + BAR_W + 10, yc), (x + BAR_W + 26, yc), (lx - 12, b["left_y"])],
               fill=RED + (int(200 * pl),), width=2)
        label(L, f"剩 {b['left']:,}", lx, b["left_y"] + 11, 32, t, b["t_left"] + 0.1, 700, RED)

    # 第二段：一年存下多少
    pc = clamp((t - T_COUNT) / 1.4)
    if pc > 0:
        n = int(round(b["left"] * 12 * ease_out(pc) / 100) * 100)
        label(L, "一年存下", x, BASE_Y + 62, 26, t, T_COUNT, 400, SOFT_INK)
        text(L, f"{n:,}", x + text_width("一年存下", 26) + 16, BASE_Y + 64, 40, 700, RED,
             appear(t, T_COUNT, 0.4))

    # 让 dim 作用到方块上：在第二段给整根柱子罩一层纸色
    if dim < 1:
        veil = Image.new("RGBA", (BAR_W - 2, int(b["spent"] * SCALE) + 2), PAPER + (int(255 * (1 - dim) * 0.9),))
        L.alpha_composite(veil, (x + 1, int(BASE_Y - b["spent"] * SCALE)))


def part1(L, t):
    for b in BARS:
        draw_bar(L, t, b)
    text(L, "各自存一年", W / 2, 96, 46, 400, INK, 1.0, "m", spacing=8,
         reveal=smooth((t - T_YEAR) / 0.9))


# ---------- 第三段：这笔钱能让人停下来多久 ----------

T_PART3 = 16.5
T_LINES = 18.4
SEC_PER_MONTH = 0.5
X0, X1 = 560, 1700
PX_MONTH = (X1 - X0) / 12
ROWS = [
    dict(name="A", y=440, spend=28000, saved=24000),
    dict(name="B", y=680, spend=4000, saved=48000),
]
for r in ROWS:
    r["months"] = r["saved"] / r["spend"]
    r["t_end"] = T_LINES + r["months"] * SEC_PER_MONTH
T_RATIO = ROWS[1]["t_end"] + 0.7
T_PART3_OUT = 26.6


def part3(L, t):
    d = ImageDraw.Draw(L)
    text(L, "这笔钱，能让人停下来多久？", W / 2, 180, 52, 400, INK, 1.0, "m", spacing=6,
         reveal=smooth((t - T_PART3) / 1.2))

    # 坐标：月份网格
    pg = smooth((t - T_PART3 - 0.8) / 0.9)
    if pg > 0:
        for m in range(13):
            gx = X0 + m * PX_MONTH
            a = int(255 * pg * smooth((pg * 15 - m) / 2))
            if a <= 0:
                continue
            d.line([(gx, 380), (gx, 750)], fill=FAINT + (a,), width=1)
            text(L, str(m), gx, 800, 24, 400, GRAY, a / 255, "m")
        text(L, "个月", X1 + 34, 800, 24, 400, GRAY, pg)

    for i, r in enumerate(ROWS):
        y = r["y"]
        t0 = T_PART3 + 0.6 + i * 0.2
        label(L, r["name"], 186, y + 10, 60, t, t0, 700)
        label(L, f"每月要花 {r['spend']:,}", 260, y + 4, 26, t, t0 + 0.15, 400, SOFT_INK)
        # 虚线：一整年
        pt = smooth((t - t0 - 0.4) / 1.0)
        if pt > 0:
            for xx in np.arange(X0, X0 + (X1 - X0) * pt, 14):
                d.line([(xx, y), (xx + 6, y)], fill=FAINT + (255,), width=2)

        if t < T_LINES:
            continue
        m = min(r["months"], (t - T_LINES) / SEC_PER_MONTH)
        hx = X0 + m * PX_MONTH
        d.line([(X0, y), (hx, y)], fill=RED + (255,), width=10)
        dot(L, DOT_END, X0, y)
        dot(L, DOT_RED, hx, y)

        done = t >= r["t_end"]
        if r["months"] < 1:
            days = int(round(m * 30))
            text(L, f"{days} 天", hx, y - 34, 44 if done else 36, 700, RED, 1.0, "m")
        elif not done:
            if m >= 1:
                text(L, f"{int(m)} 个月", hx, y - 34, 36, 700, RED, 1.0, "m")
        else:
            text(L, f"{int(round(r['months']))} 个月", hx, y - 34, 44, 700, RED, 1.0, "m")
        if done:
            label(L, f"{r['saved']:,} ÷ {r['spend']:,}", X0, y + 50, 26, t, r["t_end"] + 0.2, 400, GRAY)

    text(L, "A 赚的钱，是 B 的近四倍。", W / 2, 950, 34, 400, SOFT_INK, 1.0, "m", spacing=4,
         reveal=smooth((t - T_RATIO) / 1.0))


# ---------- 第四段：结论 ----------

T_END = [27.4, 28.4, 29.5]
T_UNDERLINE = 30.4
END_LINES = ["决定你自由的，", "不是你赚多少，", "而是你必须花多少。"]
END_SIZE, END_SP = 68, 10
T_FADE = 32.2


def part4(L, t):
    x = (W - text_width(END_LINES[2], END_SIZE, 700, END_SP)) / 2
    for i, (s, t0) in enumerate(zip(END_LINES, T_END)):
        y = 400 + i * 128
        weight = 700 if i == 2 else 400
        text(L, s, x, y, END_SIZE, weight, INK, 1.0, spacing=END_SP, reveal=smooth((t - t0) / 1.0))
    pu = ease_out((t - T_UNDERLINE) / 0.5)
    if pu > 0:
        ux0 = x + 2 + text_width("而是你", END_SIZE, 700, END_SP) + END_SP
        uw = text_width("必须花", END_SIZE, 700, END_SP)
        uy = 400 + 2 * 128 + 24
        ImageDraw.Draw(L).rectangle([ux0, uy, ux0 + uw * pu, uy + 6], fill=RED + (255,))


# ---------- 渲染一帧 ----------

PAPER_IMG = make_paper()


def layer(fn, t, alpha):
    if alpha <= 0:
        return None
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fn(L, t)
    if alpha < 1:
        a = np.array(L)
        a[..., 3] = (a[..., 3].astype(np.float32) * alpha).astype(np.uint8)
        L = Image.fromarray(a)
    return L


def render(i):
    t = i / FPS
    img = PAPER_IMG.copy()
    head = 1 - smooth((t - T_PART3_OUT) / 0.6)
    text(img, "两个人的账本", 176, 74, 26, 400, GRAY, head * appear(t, 0.2, 0.8), spacing=6)
    for fn, a in ((part1, 1 - smooth((t - T_PART1_OUT) / 0.6)),
                  (part3, 1 - smooth((t - T_PART3_OUT) / 0.6) if t >= T_PART3 else 0),
                  (part4, 1 - smooth((t - T_FADE) / 0.8) if t >= T_END[0] else 0)):
        L = layer(fn, t, a)
        if L is not None:
            img.alpha_composite(L)
    return np.asarray(img.convert("RGB"))


# ---------- 声音 ----------

def make_audio(path):
    n = int(DURATION * SR)
    buf = np.zeros(n + 4 * SR)
    r = np.random.default_rng(11)

    def add(sig, at, gain=1.0):
        s = int(at * SR)
        buf[s:s + len(sig)] += sig[: len(buf) - s] * gain

    def env_t(dur):
        return np.arange(int(dur * SR)) / SR

    def thud(pitch=1.0):
        tt = env_t(0.45)
        f = (52 + 80 * np.exp(-tt * 28)) * pitch
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 11)
        click = np.convolve(r.normal(0, 1, len(tt)), np.ones(12) / 12, "same") * np.exp(-tt * 140)
        return body * 0.9 + click * 0.6

    def tick(freq):
        tt = env_t(0.07)
        return (np.sin(2 * np.pi * freq * tt) * 0.6 + r.normal(0, 0.5, len(tt))) * np.exp(-tt * 95)

    def scratch(dur):
        tt = env_t(dur)
        s = np.diff(r.normal(0, 1, len(tt) + 1))
        s = np.convolve(s, np.ones(4) / 4, "same")
        return s * np.minimum(1, tt / 0.08) * np.minimum(1, (dur - tt) / 0.15) * (0.6 + 0.4 * np.sin(tt * 37))

    def piano(midi, dur=4.0):
        tt = env_t(dur)
        f = 440 * 2 ** ((midi - 69) / 12)
        s = sum(np.sin(2 * np.pi * f * h * tt) * np.exp(-tt * (1.1 + h * 0.7)) / h ** 1.3 for h in range(1, 7))
        return s * np.minimum(1, tt / 0.006)

    # 底噪般的低音铺垫，结论之前收住
    tt = np.arange(n) / SR
    drone = sum(np.sin(2 * np.pi * f * tt) * a for f, a in ((55, 0.5), (110, 0.35), (164.8, 0.18)))
    drone *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.11 * tt)
    drone *= np.clip(tt / 3, 0, 1) * (1 - np.clip((tt - T_PART3_OUT) / 1.2, 0, 1))
    buf[:n] += drone * 0.05

    for b in BARS:
        add(scratch(0.9), b["t_outline"], 0.05)
        for i in range(len(b["blocks"])):
            add(thud(1.0 + 0.04 * i), b["t_blocks"] + i * STEP + FALL, 0.55)
        add(piano(76, 2.0), b["t_left"], 0.10)  # 「剩下」：一声轻的高音
    # 一年存款计数：细碎的拨珠声
    k = T_COUNT
    while k < T_COUNT + 1.4:
        add(tick(3100), k, 0.07)
        k += 1 / 22
    # 时间轴：钟表滴答，A 先停
    m = 0
    while T_LINES + m * SEC_PER_MONTH <= ROWS[1]["t_end"] + 1e-6:
        add(tick(1900 if m % 2 else 2300), T_LINES + m * SEC_PER_MONTH, 0.22)
        m += 1
    add(thud(0.7), ROWS[0]["t_end"], 0.7)
    add(piano(45, 3.0), ROWS[0]["t_end"], 0.16)
    add(piano(57, 3.0), ROWS[1]["t_end"], 0.12)
    # 结论：一个舒展的和弦
    for j, mm in enumerate((41, 53, 57, 60, 67)):
        add(piano(mm, 4.5), T_END[2] + j * 0.035, 0.16)
    add(piano(72, 3.0), T_UNDERLINE, 0.07)

    buf = buf[:n]
    buf *= np.minimum(1, tt / 0.3) * np.minimum(1, (DURATION - tt) / 1.0)
    buf /= np.max(np.abs(buf)) + 1e-9
    buf *= 0.85
    pcm = (buf * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.stack([pcm, pcm], axis=1).tobytes())


# ---------- 主程序 ----------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    wav = os.path.join(OUT_DIR, "_freedom.wav")
    make_audio(wav)
    out = os.path.join(OUT_DIR, "freedom.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(N_FRAMES):
        proc.stdin.write(render(i).tobytes())
        if i % 60 == 0:
            print(f"frame {i}/{N_FRAMES}")
    proc.stdin.close()
    proc.wait()
    os.remove(wav)
    print("done:", out)


if __name__ == "__main__":
    main()
