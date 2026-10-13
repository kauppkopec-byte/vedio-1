"""人生经营物语 ～金钱的艺术～

开罗游戏风格的像素短片。把一篇关于钱的文章拆成七章，用一个"人生经营"
小游戏演出来。整局游戏只盯一个数值：能停下来多久 = 存款 ÷ 每月必须花的钱。

  第一章  钱买的到底是什么        说「不」的权利
  第二章  决定自由的，是必须花的钱
  第三章  涨薪的陷阱              笼子跟着变大
  第四章  别出局                  复利只奖励留在场上的人
  第五章  「够」是比出来的
  第六章  看不见的时间            通勤的汇率
  第七章  底气是攒出来的

画面在 480x270 的像素画布上绘制，最近邻放大 4 倍输出 1920x1080；
配乐与音效全部由程序合成（方波、三角波、噪声）。

用法: python3 life_story.py  ->  output/life_story.mp4
依赖: numpy, Pillow, ffmpeg
字体: fonts/fusion-pixel.ttf（缝合像素字体，SIL OFL 1.1）
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, SCALE = 480, 270, 4
FPS = 30
SR = 44100
CPS = 11.0  # 对话框打字速度（字/秒）

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT = ImageFont.truetype(os.path.join(ROOT, "fonts", "fusion-pixel.ttf"), 12)
OUT_DIR = os.path.join(ROOT, "output")

# ---------- 调色板 ----------

OUT = (34, 26, 44)
WHITE = (250, 250, 244)
SHADOW = (22, 26, 60)
YELLOW = (255, 226, 80)
RED = (232, 72, 64)
GREEN = (128, 220, 96)
DIM = (150, 156, 190)
SKIN = (252, 214, 170)
SKIN_D = (226, 172, 130)
BLUSH = (246, 150, 146)

STYLES = {
    "blue": ((76, 132, 236), (36, 70, 176), WHITE),
    "gold": ((252, 200, 76), (224, 128, 40), (255, 248, 222)),
    "red": ((236, 96, 84), (170, 40, 50), WHITE),
    "dark": ((44, 54, 98), (24, 28, 58), (196, 208, 240)),
    "green": ((96, 196, 104), (40, 132, 72), WHITE),
}

LIN = dict(hair=(52, 46, 70), shirt=(72, 128, 228), pants=(58, 58, 92))
CHEN = dict(hair=(150, 90, 48), shirt=(96, 188, 100), pants=(76, 66, 58))
BOSS = dict(hair=(184, 184, 192), shirt=(56, 56, 74), pants=(42, 42, 56), kind="boss")
FRIEND = dict(hair=(244, 144, 48), shirt=(250, 212, 64), pants=(84, 76, 128), kind="shades")
COWORKERS = [dict(hair=(200, 80, 72), shirt=(236, 236, 236)), dict(hair=(60, 60, 60), shirt=(232, 150, 80)),
             dict(hair=(236, 196, 96), shirt=(160, 110, 210)), dict(hair=(90, 60, 40), shirt=(110, 190, 210)),
             dict(hair=(40, 40, 50), shirt=(220, 110, 140))]


# ---------- 工具 ----------

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


def lerp_c(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def draw(img):
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return d


def money(v):
    return f"{int(round(v)):,}"


def outlined(im, color=OUT):
    a = np.array(im)
    m = a[..., 3] > 0
    dil = m.copy()
    dil[1:] |= m[:-1]
    dil[:-1] |= m[1:]
    dil[:, 1:] |= m[:, :-1]
    dil[:, :-1] |= m[:, 1:]
    a[dil & ~m] = color + (255,)
    return Image.fromarray(a)


def put(img, spr, x, y):
    img.paste(spr, (int(round(x)), int(round(y))), spr)


def put_feet(img, spr, fx, fy):
    put(img, spr, fx - spr.width // 2, fy - spr.height + 1)


def overlay(img, color, alpha):
    if alpha > 0:
        img.alpha_composite(Image.new("RGBA", img.size, color + (int(255 * clamp(alpha)),)))


# ---------- 文字与窗口 ----------

def tw(s):
    return int(FONT.getlength(s))


def txt(d, x, y, s, color=WHITE, shadow=SHADOW, anchor="l"):
    if anchor == "m":
        x -= tw(s) // 2
    elif anchor == "r":
        x -= tw(s)
    x, y = int(x), int(y)
    if shadow:
        d.text((x + 1, y + 1), s, font=FONT, fill=shadow)
    d.text((x, y), s, font=FONT, fill=color)


def otxt(d, x, y, s, color=WHITE, outline=OUT, anchor="l"):
    if anchor == "m":
        x -= tw(s) // 2
    elif anchor == "r":
        x -= tw(s)
    x, y = int(x), int(y)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        d.text((x + dx, y + dy), s, font=FONT, fill=outline)
    d.text((x, y), s, font=FONT, fill=color)


_BIG = {}


def big_text(s, scale, color=WHITE, outline=OUT, grad=None):
    key = (s, scale, color, outline, grad)
    if key not in _BIG:
        im = Image.new("RGBA", (tw(s) + 2, 14), (0, 0, 0, 0))
        dd = draw(im)
        dd.text((1, 0), s, font=FONT, fill=color + (255,))
        if grad:
            a = np.array(im)
            for y in range(a.shape[0]):
                c = lerp_c(grad[0], grad[1], y / 13)
                a[y, :, :3] = c
            im = Image.fromarray(a)
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        pad = Image.new("RGBA", (im.width + 4, im.height + 4), (0, 0, 0, 0))
        pad.paste(im, (2, 2))
        im = outlined(outlined(pad, outline), outline)
        _BIG[key] = im
    return _BIG[key]


def put_big(img, s, scale, cx, y, **kw):
    im = big_text(s, scale, **kw)
    put(img, im, cx - im.width // 2, y)


def window(d, x, y, w, h, style="blue"):
    top, bot, border = STYLES[style]
    x, y, w, h = int(x), int(y), int(w), int(h)
    d.rectangle([x + 1, y, x + w - 2, y + h - 1], fill=OUT)
    d.rectangle([x, y + 1, x + w - 1, y + h - 2], fill=OUT)
    d.rectangle([x + 2, y + 1, x + w - 3, y + h - 2], fill=border)
    d.rectangle([x + 1, y + 2, x + w - 2, y + h - 3], fill=border)
    for yy in range(y + 2, y + h - 2):
        d.line([(x + 2, yy), (x + w - 3, yy)], fill=lerp_c(top, bot, (yy - y - 2) / max(1, h - 5)))
    d.line([(x + 3, y + 2), (x + w - 4, y + 2)], fill=lerp_c(top, WHITE, 0.4))


def wrap(s, maxw):
    lines, cur = [], ""
    for ch in s:
        if tw(cur + ch) > maxw and cur:
            lines.append(cur)
            cur = ""
        cur += ch
    if cur:
        lines.append(cur)
    return lines


def cursor_tri(d, x, y, color=YELLOW):
    for i in range(4):
        d.line([(x + i, y + i), (x + i, y + 8 - i)], fill=color)


# ---------- 像素小人 ----------

_SPR = {}


def chibi(hair, shirt, pants=(60, 60, 90), kind="normal", facing="down", frame=0):
    key = (hair, shirt, pants, kind, facing, frame)
    if key in _SPR:
        return _SPR[key]
    im = Image.new("RGBA", (14, 18), (0, 0, 0, 0))
    px = im.load()

    def p(x, y, c):
        if 0 <= x < 12 and 0 <= y < 16:
            px[x + 1, y + 1] = c + (255,)

    def row(a, b, y, c):
        for x in range(a, b + 1):
            p(x, y, c)

    for y, (a, b) in {1: (3, 8), 2: (2, 9), 3: (1, 10), 4: (1, 10), 5: (1, 10), 6: (1, 10),
                      7: (1, 10), 8: (2, 9), 9: (3, 8)}.items():
        row(a, b, y, SKIN)
    if kind == "boss":
        for y in (3, 4, 5):
            p(1, y, hair)
            p(10, y, hair)
        p(4, 2, WHITE)
    else:
        for y, (a, b) in {0: (3, 8), 1: (2, 9), 2: (1, 10), 3: (1, 10)}.items():
            row(a, b, y, hair)
        for y in (4, 5):
            p(1, y, hair)
            p(10, y, hair)
        if kind == "shades":
            p(2, -1 + 1, hair)
            p(5, 0, hair)
            p(8, 0, hair)
    if facing == "up":
        for y in range(4, 9):
            row(1 if y < 8 else 2, 10 if y < 8 else 9, y, hair if kind != "boss" else SKIN)
    else:
        if kind != "boss":
            p(2, 4, hair)
            p(9, 4, hair)
        ex = {"down": (3, 8), "left": (2, 6), "right": (5, 9)}[facing]
        if kind == "shades":
            row(2, 9, 5, OUT)
            p(ex[0], 5, (120, 120, 140))
        else:
            for x in ex:
                p(x, 5, OUT)
                p(x, 6, OUT)
        if kind == "boss":
            row(4, 7, 7, hair)
        else:
            p(ex[0] - 1, 7, BLUSH)
            p(ex[1] + 1, 7, BLUSH)
    for y in range(10, 14):
        row(2, 9, y, shirt)
    if kind == "boss":
        p(4, 10, WHITE)
        p(7, 10, WHITE)
        for y in (10, 11, 12):
            p(5, y, RED)
            p(6, y, RED)
    for y in (10, 11, 12):
        p(1, y, shirt)
        p(10, y, shirt)
    p(1, 13, SKIN)
    p(10, 13, SKIN)
    shoe = (40, 34, 40)
    legs = {0: ((3, 4, 2), (7, 8, 2)), 1: ((3, 4, 1), (7, 8, 2)), 2: ((3, 4, 2), (7, 8, 1))}[frame]
    for a, b, n in legs:
        for k in range(n):
            row(a, b, 14 + k, pants if k < n - 1 or n == 1 else shoe)
    spr = outlined(im)
    _SPR[key] = spr
    return spr


def person(c, facing="down", frame=0):
    return chibi(c["hair"], c["shirt"], c.get("pants", (60, 60, 90)), c.get("kind", "normal"), facing, frame)


def walk_frame(t, moving):
    return [1, 0, 2, 0][int(t * 8) % 4] if moving else 0


def path(lt, t0, dur, p0, p1):
    """返回 (x, y, 是否在走, 朝向)。"""
    k = clamp((lt - t0) / dur) if dur > 0 else 1
    x, y = lerp(p0[0], p1[0], k), lerp(p0[1], p1[1], k)
    moving = 0 < (lt - t0) < dur
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    facing = ("right" if dx > 0 else "left") if abs(dx) >= abs(dy) else ("down" if dy > 0 else "up")
    return x, y, moving, facing


def sweat(d, fx, fy):
    x, y = int(fx + 6), int(fy - 15)
    d.point([(x + 1, y), (x, y + 1), (x + 2, y + 1)], fill=OUT)
    d.rectangle([x, y + 2, x + 2, y + 3], fill=(130, 190, 255))
    d.point([(x + 1, y + 1)], fill=(130, 190, 255))
    d.line([(x - 1, y + 2), (x - 1, y + 3)], fill=OUT)
    d.line([(x + 3, y + 2), (x + 3, y + 3)], fill=OUT)
    d.line([(x, y + 4), (x + 2, y + 4)], fill=OUT)


def bubble(d, fx, fy, mark="!"):
    x, y = int(fx + 3), int(fy - 30)
    d.rectangle([x, y, x + 10, y + 11], fill=OUT)
    d.rectangle([x + 1, y + 1, x + 9, y + 10], fill=WHITE)
    d.polygon([(x + 2, y + 11), (x + 5, y + 11), (x + 2, y + 14)], fill=OUT)
    d.line([(x + 3, y + 11), (x + 4, y + 11)], fill=WHITE)
    if mark == "!":
        d.rectangle([x + 5, y + 2, x + 5, y + 6], fill=RED)
        d.point([(x + 5, y + 8)], fill=RED)
    elif mark == "?":
        d.line([(x + 4, y + 2), (x + 6, y + 2)], fill=(60, 90, 200))
        d.point([(x + 7, y + 3), (x + 6, y + 4), (x + 5, y + 5), (x + 5, y + 6), (x + 5, y + 8)], fill=(60, 90, 200))
    elif mark == "heart":
        put(d._image, ICONS["heart"], x + 2, y + 3)
    elif mark == "...":
        d.point([(x + 3, y + 6), (x + 5, y + 6), (x + 7, y + 6)], fill=OUT)


# ---------- 图标 ----------

def pixmap(rows, colors):
    im = Image.new("RGBA", (len(rows[0]) + 2, len(rows) + 2), (0, 0, 0, 0))
    px = im.load()
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in colors:
                px[x + 1, y + 1] = colors[ch] + (255,)
    return outlined(im)


def make_icons():
    ic = {}
    ic["heart"] = pixmap([".RR.RR.", "RWRRRRR", "RRRRRRR", ".RRRRR.", "..RRR..", "...R..."],
                         {"R": (236, 64, 88), "W": WHITE})
    ic["heart_empty"] = pixmap([".GG.GG.", "GGGGGGG", "GGGGGGG", ".GGGGG.", "..GGG..", "...G..."],
                               {"G": (110, 104, 130)})
    ic["coin"] = pixmap(["..YYYY..", ".YWYYYY.", "YWYYDYYY", "YYYYDYYY", "YYYYDYYY", "YYYYDYYY", ".YYYYYY.", "..YYYY.."],
                        {"Y": (250, 210, 56), "W": (255, 250, 210), "D": (204, 140, 30)})
    ic["star"] = pixmap(["....Y....", "...YYY...", "YYYYWYYYY", ".YYYYYYY.", "..YYYYY..", ".YYY.YYY.", ".YY...YY."],
                        {"Y": (255, 214, 60), "W": WHITE})
    ic["house"] = pixmap(["......RR......", "....RRRRRR....", "..RRRRRRRRRR..", "RRRRRRRRRRRRRR",
                          ".CCCCCCCCCCCC.", ".CBBCCCCCCBBC.", ".CBBCCDDCCBBC.", ".CCCCCDDCCCCC.", ".CCCCCDDCCCCC."],
                         {"R": (220, 70, 60), "C": (250, 236, 204), "B": (120, 196, 248), "D": (150, 96, 56)})
    ic["car"] = pixmap(["...RRRRRR.....", "..RBBRRBBR....", ".RRRRRRRRRRRR.", "RRRRRRRRRRRRRY", "RRKKRRRRRKKRRR", "..KK.....KK..."],
                       {"R": (226, 60, 56), "B": (150, 220, 255), "K": (40, 36, 44), "Y": (255, 230, 120)})
    ic["books"] = pixmap(["GGGGGGGGGG", "GWWWWWWWWG", "BBBBBBBBB.", "BWWWWWWWB.", ".RRRRRRRRR", ".RWWWWWWWR"],
                         {"G": (90, 180, 90), "B": (80, 130, 230), "R": (220, 80, 80), "W": (250, 246, 230)})
    ic["clock"] = pixmap(["..WWWW..", ".WWWWWW.", "WWWKWWWW", "WWWKWWWW", "WWWKKKWW", "WWWWWWWW", ".WWWWWW.", "..WWWW.."],
                         {"W": WHITE, "K": OUT})
    ic["up"] = pixmap(["..G..", ".GGG.", "GGGGG", ".GGG.", ".GGG."], {"G": GREEN})
    return ic


ICONS = make_icons()


# ---------- 头像 ----------

PORTRAITS = {
    "顾问": dict(hair=(150, 96, 214), shirt=(64, 176, 172), style="girl"),
    "小林": dict(hair=LIN["hair"], shirt=LIN["shirt"], style="short"),
    "老板": dict(hair=(184, 184, 192), shirt=(56, 56, 74), style="boss"),
    "朋友": dict(hair=(244, 144, 48), shirt=(250, 212, 64), style="friend"),
}
_PORT = {}


def portrait(who):
    if who in _PORT:
        return _PORT[who]
    P = PORTRAITS[who]
    hair, shirt, st = P["hair"], P["shirt"], P["style"]
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if st == "girl":
        d.rectangle([5, 9, 26, 28], fill=hair)
    d.ellipse([3, 24, 28, 42], fill=shirt)
    d.rectangle([13, 20, 18, 25], fill=SKIN_D)
    if st == "boss":
        d.polygon([(12, 25), (19, 25), (15, 31)], fill=WHITE)
        d.rectangle([15, 25, 16, 31], fill=RED)
    if st == "girl":
        d.polygon([(11, 25), (20, 25), (15, 30)], fill=WHITE)
    d.ellipse([8, 6, 23, 23], fill=SKIN)
    if st == "girl":
        d.ellipse([5, 2, 26, 14], fill=hair)
        for x in range(8, 24):
            d.line([(x, 8), (x, 10 + (x % 3 == 0))], fill=hair)
        d.rectangle([5, 9, 8, 27], fill=hair)
        d.rectangle([23, 9, 26, 27], fill=hair)
    elif st == "short":
        d.ellipse([6, 3, 25, 13], fill=hair)
        for x in range(8, 24):
            d.line([(x, 7), (x, 8 + (x % 4 == 1))], fill=hair)
        d.rectangle([7, 8, 8, 14], fill=hair)
        d.rectangle([23, 8, 24, 14], fill=hair)
    elif st == "boss":
        d.rectangle([6, 10, 8, 16], fill=hair)
        d.rectangle([23, 10, 25, 16], fill=hair)
        d.point([(12, 8), (13, 8), (12, 9)], fill=WHITE)
        d.line([(10, 11), (13, 11)], fill=hair)
        d.line([(18, 11), (21, 11)], fill=hair)
    elif st == "friend":
        d.ellipse([6, 3, 25, 12], fill=hair)
        for k in range(5):
            x0 = 7 + k * 4
            d.polygon([(x0, 6), (x0 + 4, 6), (x0 + 1, 0)], fill=hair)
        for x in range(8, 24):
            d.line([(x, 7), (x, 8)], fill=hair)
    if st == "friend":
        d.rectangle([9, 13, 22, 16], fill=OUT)
        d.point([(11, 14), (19, 14)], fill=WHITE)
    else:
        for ex in (11, 19):
            d.rectangle([ex, 13, ex + 1, 16], fill=(44, 34, 56))
            d.point([(ex, 13)], fill=WHITE)
    if st == "girl":
        d.rectangle([9, 12, 14, 17], outline=(90, 60, 120))
        d.rectangle([17, 12, 22, 17], outline=(90, 60, 120))
        d.line([(15, 14), (16, 14)], fill=(90, 60, 120))
    if st == "boss":
        d.rectangle([12, 18, 19, 19], fill=hair)
    else:
        d.line([(15, 20), (16, 20)], fill=(200, 90, 90))
        d.line([(9, 18), (10, 18)], fill=BLUSH)
        d.line([(21, 18), (22, 18)], fill=BLUSH)
    pad = Image.new("RGBA", (34, 34), (0, 0, 0, 0))
    pad.paste(im, (1, 1))
    spr = outlined(pad)
    _PORT[who] = spr
    return spr


# ---------- 场景元素 ----------

def wall_window(d, x, y, w, h, t=0.0):
    d.rectangle([x, y, x + w, y + h], fill=(120, 92, 70))
    d.rectangle([x + 1, y + 1, x + w - 1, y + h - 1], fill=WHITE)
    for yy in range(y + 3, y + h - 2):
        d.line([(x + 3, yy), (x + w - 3, yy)], fill=lerp_c((110, 196, 250), (196, 236, 255), (yy - y) / h))
    cx = x + 6 + int((t * 3) % (w - 8))
    d.rectangle([cx, y + 7, cx + 8, y + 9], fill=WHITE)
    d.rectangle([cx + 2, y + 5, cx + 6, y + 6], fill=WHITE)
    d.line([(x + w // 2, y + 2), (x + w // 2, y + h - 2)], fill=WHITE)
    d.line([(x + 2, y + h // 2), (x + w - 2, y + h // 2)], fill=WHITE)


def floor_wood(d, y0, y1, x0=0, x1=W):
    for y in range(y0, y1):
        band = (y - y0) // 9
        c = (218, 162, 100) if band % 2 else (208, 152, 92)
        if (y - y0) % 9 == 0:
            c = (172, 118, 70)
        d.line([(x0, y), (x1, y)], fill=c)
    for band in range((y1 - y0) // 9 + 1):
        off = (band * 29) % 52
        for x in range(x0 + off, x1, 52):
            d.line([(x, y0 + band * 9), (x, min(y1, y0 + band * 9 + 8))], fill=(176, 122, 74))


def floor_tile(d, y0, y1, x0=0, x1=W, c1=(238, 224, 196), c2=(226, 208, 178)):
    for y in range(y0, y1, 16):
        for x in range(x0, x1, 16):
            c = c1 if ((x - x0) // 16 + (y - y0) // 16) % 2 == 0 else c2
            d.rectangle([x, y, min(x1, x + 15), min(y1, y + 15)], fill=c)


def wallpaper(d, y0, y1, x0=0, x1=W, c=(246, 234, 210), stripe=(236, 220, 192)):
    d.rectangle([x0, y0, x1, y1], fill=c)
    for x in range(x0 + 4, x1, 10):
        d.line([(x, y0), (x, y1)], fill=stripe)


def plant(d, x, y):
    d.rectangle([x - 5, y - 6, x + 5, y + 2], fill=(176, 96, 56), outline=OUT)
    d.ellipse([x - 9, y - 22, x + 9, y - 5], fill=(80, 176, 80), outline=OUT)
    d.ellipse([x - 4, y - 26, x + 6, y - 14], fill=(104, 200, 96), outline=OUT)
    d.point([(x - 3, y - 18), (x + 2, y - 22), (x + 4, y - 12)], fill=(160, 230, 140))


def desk(d, x, y):
    d.rectangle([x - 17, y, x + 17, y + 9], fill=(236, 200, 144), outline=OUT)
    d.rectangle([x - 17, y + 10, x + 17, y + 15], fill=(178, 122, 74), outline=OUT)
    d.line([(x - 16, y + 1), (x + 16, y + 1)], fill=(252, 226, 180))
    d.rectangle([x + 4, y - 7, x + 15, y + 3], fill=(120, 128, 150), outline=OUT)
    d.rectangle([x + 6, y - 5, x + 13, y + 1], fill=(92, 98, 120))
    d.rectangle([x - 12, y + 3, x - 2, y + 6], fill=(220, 224, 232), outline=OUT)


# ---------- 时间线 ----------

class Chapter:
    def __init__(self, key, num, title, scene, hud=False):
        self.key, self.num, self.title, self.scene, self.hud_on = key, num, title, scene, hud
        self.t = 0.0
        self.items, self.marks, self.hud, self.sfx_list, self.music_list = [], {}, [], [], []
        self.open_popups = []

    def wait(self, d):
        self.t += d

    def act(self, name, d=0.0):
        self.marks[name] = self.t
        self.t += d

    def sfx(self, name, offset=0.0, **kw):
        self.sfx_list.append((self.t + offset, name, kw))

    def music(self, track, offset=0.0):
        self.music_list.append((self.t + offset, track))

    def set(self, offset=0.0, anim=0.8, **vals):
        self.hud.append((self.t + offset, anim, vals))

    def banner(self):
        self.items.append(dict(kind="banner", t0=self.t, dur=2.6))
        self.sfx("jingle", 0.15)
        self.t += 2.6

    def say(self, who, text, hold=None):
        dur = len(text) / CPS + (hold if hold is not None else 1.25 + 0.03 * len(text))
        self.items.append(dict(kind="dialog", t0=self.t, dur=dur, who=who, text=text))
        for k, ch in enumerate(text):
            if k % 2 == 0 and ch not in "，。！？：、「」… ":
                self.sfx("blip", k / CPS, who=who)
        self.t += dur

    def menu(self, options, enabled, script, dur, title=None):
        self.items.append(dict(kind="menu", t0=self.t, dur=dur, options=options, enabled=enabled,
                               script=script, title=title))
        for at, _, action in script:
            self.sfx({"move": "cursor", "buzz": "buzz", "select": "select"}[action], at)
        self.t += dur

    def popup(self, text, icon=None, style="blue", y=40, dur=None, offset=0.0, sound=None):
        it = dict(kind="popup", t0=self.t + offset, t1=None if dur is None else self.t + offset + dur,
                  text=text, icon=icon, style=style, y=y)
        self.items.append(it)
        if dur is None:
            self.open_popups.append(it)
        if sound:
            self.sfx(sound, offset)
        return it

    def clear_popups(self):
        for it in self.open_popups:
            it["t1"] = self.t
        self.open_popups = []

    def finish(self, tail=0.5):
        self.t += tail
        self.clear_popups()
        self.dur = self.t

    # --- 播放时查询 ---
    def m(self, name):
        return self.marks.get(name, 1e9)

    def hud_at(self, lt):
        cur = {}
        for t0, anim, vals in self.hud:
            if t0 > lt:
                break
            p = smooth((lt - t0) / anim) if anim > 0 else 1.0
            for k, v in vals.items():
                if isinstance(v, (int, float)) and k in cur:
                    cur[k] = lerp(cur[k], v, p)
                else:
                    cur[k] = v
        return cur


def freedom_str(cash, must):
    f = cash / must if must else 0
    if f < 1:
        return f"{int(round(f * 30))}天"
    return f"{int(f + 1e-6)}个月"


# ---------- HUD 与界面层 ----------

def draw_hud(img, d, ch, lt):
    v = ch.hud_at(lt)
    d.rectangle([0, 0, W, 17], fill=(26, 36, 76))
    d.line([(0, 17), (W, 17)], fill=(120, 160, 240))
    d.line([(0, 18), (W, 18)], fill=OUT)
    x = 5
    txt(d, x, 3, v.get("date", ""), WHITE)
    x += tw(v.get("date", "")) + 12
    put(img, ICONS["coin"], x, 4)
    x += 12
    s = f"资金 {money(v.get('cash', 0))}"
    txt(d, x, 3, "资金", DIM)
    txt(d, x + tw("资金 "), 3, money(v.get("cash", 0)), YELLOW)
    x += tw(s) + 12
    for label, key in (("月收入", "income"), ("必须花", "must")):
        txt(d, x, 3, label, DIM)
        txt(d, x + tw(label + " "), 3, money(v.get(key, 0)), WHITE)
        x += tw(f"{label} {money(v.get(key, 0))}") + 12
    fs = freedom_str(v.get("cash", 0), v.get("must", 1))
    bx = 374
    flash = ch.m("hud_flash") <= lt < ch.m("hud_flash") + 3.4
    low = v.get("cash", 0) / max(1, v.get("must", 1)) < 1
    border = (YELLOW if int(lt * 6) % 2 else RED) if flash else (YELLOW if not low else RED)
    d.rectangle([bx, 1, W - 3, 15], fill=OUT)
    d.rectangle([bx + 1, 2, W - 4, 14], fill=border)
    d.rectangle([bx + 2, 3, W - 5, 13], fill=(44, 30, 60))
    txt(d, bx + 5, 2, "能停下来", (255, 200, 200) if low else (200, 240, 200), shadow=None)
    txt(d, W - 7, 2, fs, RED if low else YELLOW, shadow=None, anchor="r")
    if flash:
        ay = 22 + int(abs(math.sin(lt * 7)) * 4)
        cx = (bx + W - 3) // 2
        for i in range(5):
            d.line([(cx - i, ay + i), (cx + i, ay + i)], fill=YELLOW)
        d.rectangle([cx - 2, ay + 5, cx + 2, ay + 10], fill=YELLOW)


def draw_banner(img, d, ch, it, lt):
    k = lt - it["t0"]
    overlay(img, (10, 10, 30), 0.45 * smooth(k / 0.3) * (1 - smooth((k - it["dur"] + 0.3) / 0.3)))
    x = lerp(-440, 30, ease_out(k / 0.35)) if k < it["dur"] - 0.35 else lerp(30, 500, smooth((k - it["dur"] + 0.35) / 0.35))
    d = draw(img)
    window(d, x, 104, 420, 60, "gold")
    otxt(d, x + 210, 110, ch.num, WHITE, anchor="m")
    put_big(img, ch.title, 2, x + 210, 124)


def draw_dialog(img, d, it, lt):
    k = lt - it["t0"]
    n = int(k * CPS)
    window(d, 6, 198, 468, 68, "blue")
    who = it["who"]
    d.rectangle([11, 204, 46, 239], fill=OUT)
    d.rectangle([12, 205, 45, 238], fill=(170, 214, 250))
    put(img, portrait(who), 12, 205)
    nw = tw(who) + 14
    window(d, 8, 184, nw, 17, "gold")
    otxt(d, 8 + nw // 2, 186, who, WHITE, anchor="m")
    shown = it["text"][:n]
    lines = wrap(it["text"], 404)
    used = 0
    for i, line in enumerate(lines):
        part = shown[used:used + len(line)]
        used += len(line)
        txt(d, 56, 206 + i * 15, part, WHITE)
    if n >= len(it["text"]) and int(lt * 3) % 2 == 0:
        x, y = 458, 254
        for i in range(4):
            d.line([(x - 3 + i, y + i), (x + 3 - i, y + i)], fill=YELLOW)


def draw_menu(img, d, it, lt):
    k = lt - it["t0"]
    opts = it["options"]
    h = 12 + 17 * len(opts) + (17 if it["title"] else 0)
    x, y = 334, 112
    window(d, x, y, 128, h, "blue")
    oy = y + 6
    if it["title"]:
        txt(d, x + 64, oy, it["title"], YELLOW, anchor="m")
        oy += 17
    cur, flash = 0, None
    for at, idx, action in it["script"]:
        if k >= at:
            cur = idx
            if action in ("buzz", "select") and k < at + 0.7:
                flash = (idx, action)
    for i, s in enumerate(opts):
        c = WHITE if it["enabled"][i] else (120, 126, 160)
        if flash and flash[0] == i:
            c = RED if flash[1] == "buzz" and int(k * 12) % 2 else (YELLOW if flash[1] == "select" and int(k * 12) % 2 else c)
        txt(d, x + 24, oy + i * 17, s, c)
        if not it["enabled"][i]:
            d.line([(x + 22, oy + i * 17 + 6), (x + 26 + tw(s), oy + i * 17 + 6)], fill=(120, 126, 160))
    cursor_tri(d, x + 10 + int(abs(math.sin(lt * 6)) * 2), oy + cur * 17 + 2)


def draw_popup(img, d, it, lt):
    k = lt - it["t0"]
    pop = ease_out(k / 0.18)
    w = tw(it["text"]) + (34 if it["icon"] else 20)
    x = 240 - w // 2
    y = it["y"] - int((1 - pop) * 8)
    window(d, x, y, w, 26, it["style"])
    tx = x + 10
    if it["icon"]:
        ic = ICONS[it["icon"]]
        put(img, ic, x + 8, y + 13 - ic.height // 2)
        tx = x + 10 + ic.width + 4
    otxt(d, tx, y + 7, it["text"], WHITE)


def draw_items(img, ch, lt):
    d = draw(img)
    for it in ch.items:
        if it["kind"] == "popup":
            t1 = it["t1"] if it["t1"] is not None else ch.dur
            if it["t0"] <= lt < t1:
                draw_popup(img, d, it, lt)
    for it in ch.items:
        if it["kind"] in ("menu", "dialog", "banner") and it["t0"] <= lt < it["t0"] + it["dur"]:
            if it["kind"] == "menu":
                draw_menu(img, d, it, lt)
            elif it["kind"] == "dialog":
                draw_dialog(img, d, it, lt)
            else:
                draw_banner(img, d, ch, it, lt)
                d = draw(img)


# ---------- 场景：标题 ----------

_CACHE = {}


def cached(name, fn):
    if name not in _CACHE:
        _CACHE[name] = fn()
    return _CACHE[name]


def skyline_bg():
    img = Image.new("RGBA", (W, H))
    d = draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=lerp_c((84, 170, 248), (196, 234, 255), y / 200))
    r = np.random.default_rng(5)
    x = 0
    while x < W:
        bw, bh = int(r.integers(22, 44)), int(r.integers(40, 110))
        d.rectangle([x, 210 - bh, x + bw, 210], fill=(150, 190, 226))
        x += bw + int(r.integers(0, 6))
    x = -10
    while x < W:
        bw, bh = int(r.integers(26, 52)), int(r.integers(30, 80))
        col = [(236, 120, 96), (250, 196, 96), (120, 170, 236), (180, 140, 220), (240, 236, 220)][int(r.integers(0, 5))]
        d.rectangle([x, 222 - bh, x + bw, 222], fill=col, outline=OUT)
        for wy in range(222 - bh + 5, 216, 9):
            for wx in range(x + 4, x + bw - 4, 8):
                d.rectangle([wx, wy, wx + 3, wy + 4], fill=(255, 248, 200) if r.random() < 0.5 else (90, 120, 170))
        x += bw + int(r.integers(2, 10))
    d.rectangle([0, 222, W, H], fill=(96, 196, 88))
    for x in range(0, W, 6):
        d.point([(x + (x // 6) % 3, 226), (x + 2, 238 + (x // 6) % 5)], fill=(70, 160, 70))
    return img


def cloud(d, x, y, s=1):
    for dx, dy, r in ((0, 4, 7), (8, 0, 9), (18, 4, 7), (10, 6, 8)):
        d.ellipse([x + dx * s - r * s, y + dy * s - r * s // 2, x + dx * s + r * s, y + dy * s + r * s // 2 + 2], fill=WHITE)


def scene_title(img, ch, lt):
    img.paste(cached("skyline", skyline_bg), (0, 0))
    d = draw(img)
    for i, (cx, cy, sp) in enumerate(((40, 14, 6), (200, 30, 4), (360, 12, 7), (300, 36, 3))):
        cloud(d, (cx + lt * sp * 3) % (W + 60) - 40, cy, 1)
    drop = ease_out((lt - 0.3) / 0.7)
    if lt > 0.3:
        y = lerp(-60, 54, drop) + (math.sin((lt - 1.0) * 10) * 3 * max(0, 1 - (lt - 1.0) * 2) if lt > 1 else 0)
        put_big(img, "人生经营物语", 4, W // 2, int(y), color=WHITE, grad=((255, 236, 120), (240, 140, 40)))
    if lt > 1.3:
        put_big(img, "～金钱的艺术～", 2, W // 2, 132, color=WHITE)
    st = ch.m("start")
    if 1.8 < lt < st and int(lt * 2.5) % 2 == 0:
        otxt(d, W // 2, 178, "按下开始", WHITE, anchor="m")
    if st <= lt:
        if int(lt * 14) % 2 == 0:
            otxt(d, W // 2, 178, "开始游戏！", YELLOW, anchor="m")
        overlay(img, (255, 255, 255), 0.7 * (1 - smooth((lt - st) / 0.25)))


# ---------- 场景：办公室 ----------

def office_bg():
    img = Image.new("RGBA", (W, H))
    d = draw(img)
    wallpaper(d, 18, 76, c=(236, 228, 210), stripe=(228, 218, 198))
    d.rectangle([0, 18, W, 22], fill=(196, 176, 150))
    for wx in (30, 142, 254):
        wall_window(d, wx, 30, 64, 34)
    d.rectangle([360, 32, 398, 58], fill=WHITE, outline=OUT)
    for i, c in enumerate(((236, 80, 80), (80, 160, 236), (90, 190, 90))):
        d.rectangle([366 + i * 10, 52 - (i + 1) * 5, 372 + i * 10, 54], fill=c)
    d.rectangle([420, 34, 448, 76], fill=(150, 96, 60), outline=OUT)
    d.rectangle([423, 37, 445, 76], fill=(178, 118, 74))
    d.point([(441, 58), (441, 59)], fill=YELLOW)
    d.rectangle([0, 76, W, 80], fill=(150, 104, 70))
    floor_wood(d, 81, H)
    plant(d, 14, 104)
    plant(d, 466, 112)
    d.rectangle([396, 86, 412, 112], fill=(210, 230, 246), outline=OUT)
    d.rectangle([398, 80, 410, 88], fill=(120, 190, 250), outline=OUT)
    return img


DESKS = [(80, 104), (200, 104), (320, 104), (80, 156), (200, 156), (320, 156)]
LIN_DESK = 4


def scene_office(img, ch, lt):
    img.paste(cached("office", office_bg), (0, 0))
    d = draw(img)
    # 小林与同事坐在桌后
    for i, (x, y) in enumerate(DESKS):
        c = LIN if i == LIN_DESK else COWORKERS[i % len(COWORKERS)]
        bob = (int(lt * 4 + i) % 2) if i != LIN_DESK or lt < ch.m("menu") else 0
        put_feet(img, person(c), x - 6, y + 4 - bob)
    for x, y in DESKS:
        desk(d, x, y)
        if int(lt * 5 + x) % 3 == 0:
            d.line([(x + 7, y - 3), (x + 12, y - 3)], fill=(160, 230, 255))
    lx, ly = DESKS[LIN_DESK][0] - 6, DESKS[LIN_DESK][1] + 4
    # 老板
    door, spot = (434, 78), (240, 160)
    bi, bo = ch.m("boss_in"), ch.m("boss_out")
    if lt >= bi and lt < bo + 2.4:
        if lt < bo:
            x, y, mv, f = path(lt, bi, 1.8, door, spot)
            f = "left" if mv else "left"
        else:
            x, y, mv, f = path(lt, bo, 2.0, spot, door)
        put_feet(img, person(BOSS, f, walk_frame(lt, mv)), x, y)
        if ch.m("refused") <= lt < bo:
            sweat(d, x, y)
    # 情绪
    if ch.m("buzz") <= lt < ch.m("buzz") + 6:
        sweat(d, lx, ly)
    if ch.m("refused") <= lt < ch.m("refused") + 3:
        bubble(d, lx, ly, "!")
    stats_window(img, ch, lt)


def stats_window(img, ch, lt):
    g0 = ch.m("grow")
    if not (g0 <= lt < ch.m("boss_in")):
        return
    d = draw(img)
    k = smooth((lt - g0) / 4.5)
    x, y = 300, 26
    window(d, x, y, 172, 86, "dark")
    otxt(d, x + 86, y + 6, "这一年，小林攒下了", YELLOW, anchor="m")
    rows = [("退路·存款", f"{money(lerp(24000, 120000, k))}"),
            ("技能", f"Lv {int(lerp(1, 3.99, k))}"),
            ("人脉", "")]
    for i, (a, b) in enumerate(rows):
        yy = y + 24 + i * 18
        txt(d, x + 10, yy, a, DIM)
        if b:
            txt(d, x + 162, yy, b, WHITE, anchor="r")
    sk = lerp(0.25, 0.75, k)
    d.rectangle([x + 46, y + 47, x + 120, y + 52], fill=OUT)
    d.rectangle([x + 47, y + 48, x + 47 + int(72 * sk), y + 51], fill=GREEN)
    n = int(lerp(1, 4.99, k))
    for i in range(5):
        put(img, ICONS["star"] if i < n else ICONS["heart_empty"], x + 52 + i * 12, y + 61)


# ---------- 场景：家 ----------

def home_bg():
    img = Image.new("RGBA", (W, H))
    d = draw(img)
    wallpaper(d, 18, 84, c=(250, 236, 214), stripe=(242, 224, 198))
    d.rectangle([0, 18, W, 22], fill=(210, 170, 130))
    wall_window(d, 40, 30, 80, 40)
    d.rectangle([180, 40, 282, 80], fill=(60, 60, 70), outline=OUT)
    d.rectangle([184, 44, 278, 72], fill=(70, 150, 220))
    d.rectangle([224, 80, 238, 84], fill=(80, 80, 90))
    d.rectangle([330, 30, 380, 84], fill=(176, 120, 76), outline=OUT)
    for sy in (44, 58, 72):
        d.line([(332, sy), (378, sy)], fill=(120, 80, 50))
        for bx in range(334, 376, 6):
            d.rectangle([bx, sy - 11, bx + 4, sy - 1], fill=[(220, 80, 80), (80, 140, 220), (240, 200, 80), (110, 190, 110)][bx % 4])
    d.rectangle([420, 40, 450, 84], fill=(160, 104, 64), outline=OUT)
    d.rectangle([423, 43, 447, 84], fill=(190, 130, 84))
    d.point([(443, 64), (443, 65)], fill=YELLOW)
    d.rectangle([0, 84, W, 88], fill=(180, 130, 90))
    floor_tile(d, 89, H)
    d.ellipse([150, 120, 330, 186], fill=(236, 140, 120), outline=OUT)
    d.ellipse([170, 130, 310, 176], fill=(246, 176, 150))
    d.rectangle([40, 140, 110, 160], fill=(220, 90, 90), outline=OUT)
    d.rectangle([40, 128, 110, 142], fill=(200, 70, 72), outline=OUT)
    d.rectangle([36, 132, 46, 162], fill=(200, 70, 72), outline=OUT)
    d.rectangle([104, 132, 114, 162], fill=(200, 70, 72), outline=OUT)
    plant(d, 140, 104)
    plant(d, 400, 110)
    return img


def scene_home(img, ch, lt):
    img.paste(cached("home", home_bg), (0, 0))
    d = draw(img)
    me = (240, 150)
    bob = int(lt * 2) % 2
    boom = ch.m("boom")
    put_feet(img, person(LIN), me[0], me[1] - (bob if lt < boom else 0))
    if ch.m("raise") <= lt < ch.m("raise") + 3:
        bubble(d, *me, "heart")
    if ch.m("cost1") <= lt < ch.m("chapter_talk"):
        sweat(d, *me)
    # 朋友
    fi = ch.m("friend_in")
    fpos = (290, 150)
    if fi <= lt < boom:
        x, y, mv, f = path(lt, fi, 1.6, (434, 96), fpos)
        put_feet(img, person(FRIEND, f if mv else "left", walk_frame(lt, mv)), x, y)
        if ch.m("invest") <= lt:
            k = lt - ch.m("invest")
            window(d, 262, 98, 58, 18, "green")
            put(img, ICONS["up"], 268, 103)
            otxt(d, 278, 101, f"+{int(min(20, k * 8))}%", WHITE)
            for j in range(6):
                q = (k - j * 0.35)
                if 0 < q < 0.6:
                    qq = q / 0.6
                    cx = lerp(me[0], fpos[0], qq)
                    cy = lerp(me[1] - 20, fpos[1] - 20, qq) - math.sin(qq * math.pi) * 26
                    put(img, ICONS["coin"], cx - 5, cy - 5)
    if boom <= lt:
        explosion(img, d, lt - boom, fpos[0], fpos[1] - 10)
        if lt < ch.m("load"):
            sweat(d, *me)
    chart_window(img, ch, lt)
    load_window(img, ch, lt)
    if ch.m("raise") <= lt:
        confetti(img, d, lt - ch.m("raise"))


CONF = [(np.random.default_rng(9).uniform(0, W), np.random.default_rng(i).uniform(-120, 0),
         np.random.default_rng(i + 99).uniform(40, 90), i % 5) for i in range(70)]


def confetti(img, d, k):
    if k > 3.2:
        return
    cols = [RED, YELLOW, GREEN, (100, 170, 255), (240, 130, 220)]
    for i, (x0, y0, sp, c) in enumerate(CONF):
        x = (x0 + i * 37) % W + math.sin(k * 4 + i) * 6
        y = y0 + k * sp * 1.6
        if 18 < y < 196:
            if int(k * 8 + i) % 2:
                d.rectangle([x, y, x + 2, y + 1], fill=cols[c])
            else:
                d.rectangle([x, y, x + 1, y + 2], fill=cols[c])


DEBRIS = [(math.cos(a) * s, math.sin(a) * s - 60) for a, s in
          zip(np.linspace(0, 2 * math.pi, 18, endpoint=False), np.random.default_rng(4).uniform(60, 140, 18))]


def explosion(img, d, k, x, y):
    if k < 0.12:
        overlay(img, (255, 255, 255), 0.85)
        d = draw(img)
    if k < 1.3:
        r = 6 + 52 * ease_out(k / 0.5)
        fade = 1 - smooth((k - 0.6) / 0.7)
        for rr, c in ((r, (120, 110, 120)), (r * 0.8, (236, 90, 50)), (r * 0.6, (255, 170, 60)), (r * 0.35, (255, 246, 180))):
            if fade > 0.05:
                d.ellipse([x - rr, y - rr * 0.8, x + rr, y + rr * 0.8], fill=c)
        for i, (vx, vy) in enumerate(DEBRIS):
            px, py = x + vx * k, y + vy * k + 160 * k * k
            if py < 196:
                d.rectangle([px, py, px + 2, py + 2], fill=YELLOW if i % 2 else (90, 80, 90))
    if k < 2.4:
        jx = int(math.sin(k * 40) * 2)
        put_big(img, "暴雷！", 3, W // 2 + jx, 40, color=WHITE, grad=((255, 120, 100), (200, 30, 40)))


def chart_window(img, ch, lt):
    c0 = ch.m("chart")
    if not (c0 <= lt < ch.m("load")):
        return
    d = draw(img)
    k = lt - c0
    x, y, w, h = 56, 30, 368, 150
    window(d, x, y, w, h, "dark")
    otxt(d, x + w // 2, y + 6, "本金 10 万，30 年后会怎样？", YELLOW, anchor="m")
    gx0, gy0, gx1, gy1 = x + 34, y + 30, x + w - 70, y + h - 22
    d.line([(gx0, gy0), (gx0, gy1), (gx1, gy1)], fill=DIM)
    for v in (0, 20, 40):
        yy = gy1 - (gy1 - gy0) * v / 45
        txt(d, gx0 - 4, yy - 6, f"{v}万", DIM, shadow=None, anchor="r")
        d.line([(gx0 + 1, yy), (gx1, yy)], fill=(60, 70, 120))
    for yr in (0, 10, 20, 30):
        xx = gx0 + (gx1 - gx0) * yr / 30
        txt(d, xx, gy1 + 3, f"{yr}年", DIM, shadow=None, anchor="m")
    prog = clamp(k / 3.2)

    def pt(yr, v):
        return gx0 + (gx1 - gx0) * yr / 30, gy1 - (gy1 - gy0) * min(v, 45) / 45

    steady = [pt(yr / 2, 10 * 1.05 ** (yr / 2)) for yr in range(61)]
    wild = []
    for yr2 in range(61):
        yr = yr2 / 2
        if yr <= 5:
            v = 10 * 1.2 ** yr
        elif yr < 5.5:
            v = 0
        else:
            v = (yr - 5.5) * 0.3
        wild.append(pt(yr, v))
    n = max(2, int(61 * prog))
    d.line(steady[:n], fill=GREEN, width=2)
    d.line(wild[:n], fill=RED, width=2)
    if prog > 0.18:
        bx, by = pt(5, 24.9)
        put_big(img, "!", 1, bx, by - 22, color=YELLOW)
    if prog >= 1:
        ex, ey = steady[-1]
        otxt(d, ex + 4, ey - 6, "稳健 5%", GREEN)
        otxt(d, ex + 4, ey + 6, "43 万", WHITE)
        wx, wy = wild[-1]
        otxt(d, wx + 4, wy - 20, "激进 20%", RED)
        otxt(d, wx + 4, wy - 8, "暴雷后", WHITE)
        otxt(d, wx + 4, wy + 4, "从零开始", WHITE)


def load_window(img, ch, lt):
    l0 = ch.m("load")
    if not (l0 <= lt < l0 + 1.7):
        return
    overlay(img, (0, 0, 20), 0.5)
    d = draw(img)
    k = clamp((lt - l0) / 1.3)
    window(d, 140, 90, 200, 50, "blue")
    otxt(d, 240, 98, "读取存档中……" if k < 1 else "读取完成！", YELLOW if k >= 1 else WHITE, anchor="m")
    d.rectangle([156, 118, 324, 126], fill=OUT)
    d.rectangle([157, 119, 157 + int(166 * k), 125], fill=GREEN)


# ---------- 场景：两个人（第二章） ----------

def split_bg():
    img = Image.new("RGBA", (W, H))
    d = draw(img)
    d.rectangle([0, 0, W, H], fill=(40, 46, 80))
    # 左：小林的大房子
    wallpaper(d, 70, 112, 0, 236, c=(250, 236, 214), stripe=(240, 222, 196))
    wall_window(d, 14, 78, 50, 26)
    d.rectangle([90, 80, 160, 108], fill=(60, 60, 70), outline=OUT)
    d.rectangle([93, 83, 157, 104], fill=(80, 160, 230))
    floor_tile(d, 113, H, 0, 236)
    d.rectangle([20, 150, 90, 168], fill=(220, 90, 90), outline=OUT)
    d.rectangle([20, 140, 90, 152], fill=(200, 70, 72), outline=OUT)
    plant(d, 214, 128)
    d.rectangle([236, 64, 243, H], fill=OUT)
    # 右：小陈的小房间
    wallpaper(d, 70, 112, 244, W, c=(226, 236, 228), stripe=(214, 226, 216))
    wall_window(d, 300, 80, 40, 24)
    floor_wood(d, 113, H, 244, W)
    d.rectangle([396, 120, 466, 160], fill=(240, 240, 250), outline=OUT)
    d.rectangle([396, 120, 418, 160], fill=(120, 170, 230), outline=OUT)
    d.rectangle([262, 112, 300, 126], fill=(200, 150, 96), outline=OUT)
    d.rectangle([266, 104, 274, 112], fill=(250, 230, 140), outline=OUT)
    return img


PEOPLE2 = [dict(c=LIN, name="小林", income=30000, must=28000, x=0, me=(150, 160)),
           dict(c=CHEN, name="小陈", income=8000, must=4000, x=244, me=(340, 160))]


def scene_split(img, ch, lt):
    img.paste(cached("split", split_bg), (0, 0))
    d = draw(img)
    y0, y1 = ch.m("year"), ch.m("year") + 4.2
    yk = clamp((lt - y0) / 4.2)
    month = int(yk * 12)
    for p in PEOPLE2:
        put_feet(img, person(p["c"]), *p["me"])
        x = p["x"] + 6
        if lt >= ch.m("cards"):
            a = ease_out((lt - ch.m("cards")) / 0.3)
            window(d, x, 6 - int((1 - a) * 10), 224, 58, "blue")
            otxt(d, x + 10, 11, p["name"], YELLOW)
            txt(d, x + 10, 27, "月入", DIM)
            txt(d, x + 104, 27, money(p["income"]), WHITE, anchor="r")
            txt(d, x + 116, 27, "必须花", DIM)
            txt(d, x + 214, 27, money(p["must"]), WHITE, anchor="r")
            txt(d, x + 10, 43, "每月剩", DIM)
            txt(d, x + 104, 43, money(p["income"] - p["must"]), GREEN, anchor="r")
            txt(d, x + 116, 43, "存款", DIM)
            txt(d, x + 214, 43, money((p["income"] - p["must"]) * month), YELLOW, anchor="r")
        if y0 <= lt < y1:
            k = (lt - y0) * 12 / 4.2
            q = k - int(k)
            put(img, ICONS["coin"], p["me"][0] - 5, p["me"][1] - 40 - q * 10)
    if y0 <= lt:
        window(d, 196, 78, 88, 20, "gold")
        otxt(d, 240, 82, f"第 {max(1, month)} 个月" if month < 12 else "一年过去了", WHITE, anchor="m")
    b0 = ch.m("bars")
    if b0 <= lt:
        k = ease_out((lt - b0) / 2.2)
        window(d, 30, 108, 420, 80, "dark")
        otxt(d, 240, 114, "存款能让他停下来多久？", YELLOW, anchor="m")
        for i, (p, months, label) in enumerate(((PEOPLE2[0], 24000 / 28000, "26 天"), (PEOPLE2[1], 12, "12 个月"))):
            yy = 136 + i * 24
            txt(d, 44, yy, p["name"], WHITE)
            d.rectangle([84, yy + 1, 364, yy + 11], fill=OUT)
            ww = int(278 * months / 12 * k)
            d.rectangle([85, yy + 2, 85 + max(1, ww), yy + 10], fill=RED if i == 0 else GREEN)
            if k > 0.6:
                otxt(d, 372, yy, label, RED if i == 0 else GREEN)


# ---------- 场景：小区（第五章） ----------

def town_world():
    WW = 1240
    img = Image.new("RGBA", (WW, H))
    d = draw(img)
    for y in range(H):
        d.line([(0, y), (WW, y)], fill=lerp_c((96, 180, 250), (200, 236, 255), y / 150))
    for x in range(0, WW, 140):
        d.ellipse([x - 40, 112, x + 120, 170], fill=(150, 210, 140))
    d.rectangle([0, 150, WW, 172], fill=(110, 196, 96))
    d.rectangle([0, 172, WW, 182], fill=(214, 206, 190))
    for x in range(0, WW, 12):
        d.line([(x, 172), (x, 182)], fill=(190, 182, 168))
    d.rectangle([0, 183, WW, H], fill=(96, 98, 112))
    for x in range(0, WW, 40):
        d.rectangle([x, 222, x + 20, 224], fill=(240, 236, 220))

    def house(x, w, h, roof, wall, floors=1, label=None):
        base = 170
        d.rectangle([x, base - h, x + w, base], fill=wall, outline=OUT)
        rh = max(14, w // 5)
        d.polygon([(x - 6, base - h), (x + w // 2, base - h - rh), (x + w + 6, base - h)], fill=roof, outline=OUT)
        for f in range(floors):
            wy = base - h + 8 + f * (h // floors)
            for wx in range(x + 8, x + w - 14, 22):
                d.rectangle([wx, wy, wx + 10, wy + 10], fill=(150, 214, 250), outline=OUT)
                d.line([(wx + 5, wy), (wx + 5, wy + 10)], fill=WHITE)
        d.rectangle([x + w // 2 - 6, base - 18, x + w // 2 + 6, base], fill=(150, 96, 56), outline=OUT)
        if label:
            dd = d
            dd.rectangle([x + w // 2 - 22, base - h - rh - 18, x + w // 2 + 22, base - h - rh - 4], fill=WHITE, outline=OUT)
            txt(dd, x + w // 2, base - h - rh - 18, label, OUT, shadow=None, anchor="m")

    def tree(x, s=1.0):
        d.rectangle([x - 2, 150, x + 2, 168], fill=(130, 84, 50), outline=OUT)
        d.ellipse([x - 14 * s, 150 - 30 * s, x + 14 * s, 156], fill=(70, 168, 80), outline=OUT)
        d.ellipse([x - 8 * s, 150 - 34 * s, x + 6 * s, 150 - 14 * s], fill=(100, 196, 96))

    def hedge(x0, x1):
        for x in range(x0, x1, 10):
            d.ellipse([x, 160, x + 12, 172], fill=(64, 156, 72), outline=OUT)

    def fence(x0, x1):
        d.line([(x0, 164), (x1, 164)], fill=WHITE)
        for x in range(x0, x1 + 1, 6):
            d.rectangle([x, 160, x + 2, 171], fill=WHITE, outline=OUT)

    for x, s_ in ((20, 0.8), (200, 1.0), (455, 1.0), (1052, 1.1), (1228, 0.9)):
        tree(x, s_)
    house(40, 110, 46, (220, 80, 70), (250, 236, 210), 1, "小林家")
    house(240, 150, 70, (80, 120, 220), (240, 240, 250), 2)
    d.rectangle([400, 150, 440, 160], fill=(150, 210, 255), outline=OUT)
    house(470, 220, 90, (60, 60, 80), (250, 250, 250), 2)
    d.rectangle([700, 148, 760, 162], fill=(110, 196, 255), outline=OUT)
    house(780, 260, 110, (200, 160, 60), (236, 224, 200), 3)
    house(1070, 140, 128, (230, 190, 70), (210, 200, 230), 4)
    fence(30, 160)
    hedge(236, 394)
    hedge(466, 694)
    fence(776, 1046)
    hedge(1066, 1214)
    car = ICONS["car"].resize((ICONS["car"].width * 2, ICONS["car"].height * 2), Image.NEAREST)
    img.paste(car, (990, 168 - car.height + 10), car)
    img.paste(ICONS["car"], (330, 162), ICONS["car"])
    return img


def scene_town(img, ch, lt):
    world = cached("town", town_world)
    w0 = ch.m("walk")
    k = clamp((lt - w0) / 6.5)
    px = lerp(96, 1000, k)
    cam = int(clamp(px - 200, 0, world.width - W))
    img.paste(world.crop((cam, 0, cam + W, H)), (0, 0))
    d = draw(img)
    moving = 0 < lt - w0 < 6.5
    put_feet(img, person(LIN, "right" if moving else "down", walk_frame(lt, moving)), px - cam, 180)
    hearts = 4 - (px > 300) - (px > 560) - (px > 820)
    if lt >= ch.m("walk") and hearts < 4 and int(lt * 2) % 2 == 0:
        bubble(d, px - cam, 180, "...")
    window(d, 8, 8, 120, 34, "blue")
    txt(d, 16, 12, "满足感", WHITE)
    for i in range(5):
        put(img, ICONS["heart"] if i < hearts else ICONS["heart_empty"], 16 + i * 11, 27)
    window(d, 352, 8, 120, 20, "blue")
    txt(d, 360, 12, "月收入", DIM)
    txt(d, 464, 12, "60,000", YELLOW, anchor="r")


# ---------- 场景：通勤地图（第六章） ----------

def map_bg():
    img = Image.new("RGBA", (W, H))
    d = draw(img)
    for y in range(0, H, 8):
        for x in range(0, W, 8):
            c = (120, 200, 104) if (x // 8 + y // 8) % 2 else (112, 192, 98)
            d.rectangle([x, y, x + 7, y + 7], fill=c)
    for y in range(0, H):
        x = 196 + int(math.sin(y / 18) * 8)
        d.line([(x, y), (x + 26, y)], fill=(96, 170, 240))
        if y % 9 == 0:
            d.line([(x + 6, y), (x + 12, y)], fill=(180, 226, 255))
    d.rectangle([0, 128, W, 132], fill=(200, 196, 180))
    for x in range(48, 432, 6):
        d.line([(x, 125), (x, 135)], fill=(130, 96, 70))
    d.line([(48, 127), (432, 127)], fill=(90, 90, 100))
    d.line([(48, 133), (432, 133)], fill=(90, 90, 100))
    d.rectangle([188, 122, 232, 138], outline=OUT, fill=None)
    r = np.random.default_rng(12)
    for _ in range(26):
        x, y = int(r.integers(0, W)), int(r.integers(30, 190))
        if abs(y - 130) < 16 or 180 < x < 240:
            continue
        d.ellipse([x - 6, y - 6, x + 6, y + 5], fill=(60, 150, 70), outline=OUT)
    for bx in range(300, 470, 22):
        bh = int(r.integers(20, 50))
        d.rectangle([bx, 118 - bh, bx + 16, 118], fill=(190, 200, 220), outline=OUT)
    d.rectangle([428, 46, 470, 120], fill=(150, 170, 210), outline=OUT)
    for wy in range(52, 116, 8):
        for wx in (434, 446, 458):
            d.rectangle([wx, wy, wx + 6, wy + 4], fill=(240, 240, 180))
    img.paste(ICONS["house"], (22, 104), ICONS["house"])
    for x0, x1 in ((20, 44), (434, 466)):
        pass
    return img


def scene_map(img, ch, lt):
    img.paste(cached("map", map_bg), (0, 0))
    d = draw(img)
    window(d, 8, 84, 52, 18, "gold")
    otxt(d, 34, 87, "家", WHITE, anchor="m")
    window(d, 420, 24, 54, 18, "gold")
    otxt(d, 447, 27, "公司", WHITE, anchor="m")
    c0 = ch.m("count")
    fast = 1.0 if lt < c0 else (1 + 9 * smooth((lt - c0) / 0.8))
    cycle = 6.0
    ph = (lt * fast) % cycle / cycle
    if ph < 0.42:
        tx = lerp(56, 408, smooth(ph / 0.42))
    elif ph < 0.5:
        tx = 408
    elif ph < 0.92:
        tx = lerp(408, 56, smooth((ph - 0.5) / 0.42))
    else:
        tx = 56
    for j in range(3):
        cx = tx + j * 9 - 9
        d.rectangle([cx, 124, cx + 8, 132], fill=(240, 240, 240), outline=OUT)
        d.line([(cx + 1, 129), (cx + 7, 129)], fill=(60, 170, 90))
        d.point([(cx + 3, 126), (cx + 5, 126)], fill=(120, 190, 250))
    window(d, 172, 150, 140, 18, "blue")
    put(img, ICONS["clock"], 180, 154)
    txt(d, 194, 153, "单程 1 小时", WHITE)
    hours = 0
    if lt < c0:
        hours = int(lt / cycle) * 2
    else:
        hours = int(lerp(min(6, int(c0 / cycle) * 2), 500, smooth((lt - c0) / 2.8)))
    window(d, 8, 8, 168, 34, "dark")
    txt(d, 16, 12, "今年花在路上的时间", DIM)
    otxt(d, 168, 26, f"{hours} 小时", YELLOW if hours < 500 else RED, anchor="r")
    k0 = ch.m("calc")
    if k0 <= lt:
        k = lt - k0
        window(d, 184, 6, 216, 96, "blue")
        rows = [("每月省房租", "1,500 元", WHITE), ("一年省下", "18,000 元", WHITE),
                ("一年通勤", "500 小时", WHITE), ("相当于每小时", "36 元", YELLOW)]
        for i, (a, b, c) in enumerate(rows):
            if k > i * 0.35:
                yy = 12 + i * 20 + (6 if i == 3 else 0)
                txt(d, 194, yy, a, DIM if i < 3 else WHITE)
                otxt(d, 390, yy, b, c, anchor="r") if i == 3 else txt(d, 390, yy, b, c, anchor="r")
        if k > 1.0:
            d.line([(194, 76), (390, 76)], fill=WHITE)


# ---------- 场景：结尾 ----------

STARS = [(np.random.default_rng(i).uniform(0, W), np.random.default_rng(i + 500).uniform(0, 150)) for i in range(80)]


def night_bg():
    img = Image.new("RGBA", (W, H))
    d = draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=lerp_c((14, 18, 52), (60, 50, 110), y / H))
    r = np.random.default_rng(21)
    x = -6
    while x < W:
        bw, bh = int(r.integers(24, 50)), int(r.integers(40, 120))
        d.rectangle([x, 270 - bh, x + bw, 270], fill=(30, 32, 66), outline=OUT)
        for wy in range(270 - bh + 6, 266, 9):
            for wx in range(x + 4, x + bw - 4, 8):
                if r.random() < 0.45:
                    d.rectangle([wx, wy, wx + 3, wy + 4], fill=(255, 220, 120))
        x += bw + int(r.integers(1, 8))
    return img


END_LINES = ["决定你自由的，", "不是你赚多少，", "而是你必须花多少。"]


def scene_end(img, ch, lt):
    img.paste(cached("night", night_bg), (0, 0))
    d = draw(img)
    for i, (x, y) in enumerate(STARS):
        if int(lt * 3 + i) % 5:
            d.point([(x, y)], fill=WHITE if i % 3 else YELLOW)
    window(d, 70, 40, 340, 128, "dark")
    for i, s in enumerate(END_LINES):
        t0 = 0.6 + i * 1.5
        n = int(clamp((lt - t0) * 8, 0, len(s)))
        if n:
            put(img, big_text(s[:n], 2, color=YELLOW if i == 2 else WHITE), 92, 52 + i * 34)
    if lt > 5.6:
        window(d, 160, 180, 160, 22, "gold")
        otxt(d, 240, 184, "人生经营物语 · 完", WHITE, anchor="m")


# ---------- 剧本 ----------

def build():
    chs = []

    c = Chapter("title", None, None, scene_title)
    c.music("main", 0.2)
    c.wait(4.4)
    c.act("start")
    c.sfx("select")
    c.wait(1.0)
    c.finish(0.2)
    chs.append(c)

    c = Chapter("ch1", "第一章", "钱买的到底是什么", scene_office, hud=True)
    c.set(anim=0, date="第1年 4月", cash=24000, income=30000, must=28000)
    c.banner()
    c.wait(0.6)
    c.act("boss_in", 1.9)
    c.say("老板", "小林，这周末来加班。没有加班费。")
    c.act("menu")
    c.marks["buzz"] = c.t + 1.0
    c.popup("存款只够撑 26 天，拒绝不起。", style="red", y=78, offset=1.1, dur=2.2)
    c.menu(["接受", "拒绝"], [True, False], [(0.5, 1, "move"), (1.0, 1, "buzz"), (2.7, 0, "move"), (3.3, 0, "select")],
           3.9, title="怎么回答？")
    c.act("boss_out")
    c.wait(0.3)
    c.say("顾问", "这个游戏里，最重要的数值不是资金。")
    c.act("hud_flash")
    c.say("顾问", "而是右上角这个：「能停下来多久」。")
    c.say("顾问", "它等于：存款 ÷ 每个月必须花的钱。")
    c.say("顾问", "钱真正能买到的，是说「不」的权利。")
    c.say("顾问", "这个数值太小的时候，你只能说「好」。")
    c.finish()
    chs.append(c)

    c = Chapter("ch2", "第二章", "决定自由的，是必须花的钱", scene_split)
    c.banner()
    c.act("cards", 0.8)
    c.say("顾问", "来看两个人。小林月入三万，小陈月入八千。")
    c.say("顾问", "小林不是乱花钱。房贷、车、孩子的课，每一样都说得过去。")
    c.act("year")
    for mth in range(12):
        c.sfx("coin", mth * 0.35)
    c.wait(4.6)
    c.act("bars", 2.6)
    c.say("顾问", "小林赚的是小陈的近四倍，可存一年，只够停下来 26 天。")
    c.say("顾问", "小陈存一年，能停下来一整年。")
    c.say("顾问", "决定你自由的，不是你赚多少，而是你必须花多少。")
    c.finish()
    chs.append(c)

    c = Chapter("ch3", "第三章", "涨薪的陷阱", scene_home, hud=True)
    c.set(anim=0, date="第2年 4月", cash=24000, income=30000, must=28000)
    c.banner()
    c.act("raise")
    c.popup("升职加薪！月收入 30,000 → 38,000", icon="star", style="gold", y=40, dur=2.8, sound="fanfare")
    c.set(offset=0.4, income=38000)
    c.wait(3.0)
    for i, (s, ic, must) in enumerate((("换了更大的房子  每月 +4,000", "house", 32000),
                                        ("换了一辆新车  每月 +2,500", "car", 34500),
                                        ("孩子多报两个班  每月 +2,000", "books", 36500))):
        if i == 0:
            c.act("cost1")
        c.popup(s, icon=ic, y=34 + i * 30, sound="cost")
        c.set(offset=0.1, must=must)
        c.wait(1.3)
    c.wait(1.2)
    c.clear_popups()
    c.act("chapter_talk")
    c.say("顾问", "收入涨了八千，必须花的钱涨了八千五。")
    c.say("顾问", "能停下来的时间，反而从 26 天缩到了 20 天。")
    c.say("顾问", "笼子换大了，人还在笼子里。")
    c.say("顾问", "每次涨薪先问一句：这笔钱，要不要变成新的「必须」？")
    c.finish()
    chs.append(c)

    c = Chapter("ch4", "第四章", "别出局", scene_home, hud=True)
    c.set(anim=0, date="第2年 9月", cash=24000, income=38000, must=36500)
    c.music("tense")
    c.banner()
    c.act("friend_in", 1.7)
    c.say("朋友", "稳赚不赔的项目！年化 20%！把存款都投进来吧！")
    c.menu(["全部投入", "算了"], [True, True], [(0.6, 0, "select")], 1.3)
    c.act("invest")
    for j in range(6):
        c.sfx("coin", j * 0.35)
    c.set(offset=0.2, anim=2.6, cash=28800)
    c.wait(3.0)
    c.act("boom")
    c.music(None)
    c.sfx("explosion")
    c.set(offset=0.15, anim=0.4, cash=0)
    c.wait(2.6)
    c.say("顾问", "大部分人不是输在收益太低，而是输在一次被打穿。")
    c.act("chart")
    c.music("calm")
    c.wait(3.6)
    c.say("顾问", "复利很强，但它只奖励一直留在场上的人。")
    c.say("顾问", "所以顺序是：先保证不会被一次打倒，再谈赚多少。")
    c.say("顾问", "应急金、保险、不碰看不懂的东西。很无聊，但最重要。")
    c.say("顾问", "还好这是游戏，可以读档。现实里，没有存档。")
    c.act("load")
    c.sfx("load")
    c.set(offset=1.3, anim=0, cash=24000)
    c.wait(1.8)
    c.finish()
    chs.append(c)

    c = Chapter("ch5", "第五章", "「够」是比出来的", scene_town)
    c.music("main")
    c.banner()
    c.say("顾问", "三年后，小林收入涨到六万，搬进了高级小区。")
    c.act("walk")
    for j in range(3):
        c.sfx("down", 1.2 + j * 1.9)
    c.wait(7.0)
    c.say("顾问", "可邻居的房子更大，车更好。他的满足感一路往下掉。")
    c.say("顾问", "他不是在跟自己的需要比，而是在跟邻居比。")
    c.say("顾问", "「够」不是一个数字，而是你选谁来比。")
    c.finish()
    chs.append(c)

    c = Chapter("ch6", "第六章", "看不见的时间", scene_map)
    c.music("calm")
    c.banner()
    c.say("顾问", "为了每月省 1,500 房租，很多人搬到离公司一小时远的地方。")
    c.act("count")
    for j in range(16):
        c.sfx("tick", j * 0.17)
    c.wait(3.0)
    c.say("顾问", "一天来回两小时，一年就是将近 500 小时。")
    c.act("calc")
    for j in range(4):
        c.sfx("cursor", j * 0.35)
    c.wait(1.6)
    c.say("顾问", "一年省 18,000 元，除以 500 小时，每小时 36 元。")
    c.say("顾问", "等于你用每小时 36 块，把自己的时间卖掉了。")
    c.say("顾问", "我们对看得见的钱很敏感，对看不见的时间很迟钝。")
    c.say("顾问", "不是说不能这么选，而是要先算清楚这个汇率。")
    c.finish()
    chs.append(c)

    c = Chapter("ch7", "第七章", "底气是攒出来的", scene_office, hud=True)
    c.set(anim=0, date="第2年 9月", cash=24000, income=38000, must=36500)
    c.music("main")
    c.banner()
    c.say("顾问", "回到最开始的问题：怎样才能说「不」？")
    c.say("顾问", "很多人说要有勇气。我觉得，勇气被高估了。")
    for i, (s, ic, must) in enumerate((("换回小一点的房子  每月 -4,000", "house", 32500),
                                        ("卖掉车，改坐地铁  每月 -2,500", "car", 30000))):
        c.popup(s, icon=ic, y=40 + i * 30, sound="coin")
        c.set(offset=0.1, must=must)
        c.wait(1.4)
    c.wait(1.0)
    c.clear_popups()
    c.act("grow")
    c.set(anim=4.5, cash=120000)
    c.set(offset=4.5, anim=0, date="第3年 9月")
    for j in range(12):
        c.sfx("coin", j * 0.38)
    c.wait(5.0)
    c.say("顾问", "有用的东西都很无聊：少一点「必须」，多一段能停下来的时间，再多一条离开公司也能走的路。")
    c.act("boss_in", 1.9)
    c.say("老板", "小林，这周末来加班。没有加班费。")
    c.act("menu")
    c.menu(["接受", "拒绝"], [True, True], [(0.5, 1, "move"), (1.1, 1, "select")], 1.6, title="怎么回答？")
    c.act("refused")
    c.say("小林", "这周末不行，我有安排。")
    c.say("老板", "……那好吧。")
    c.act("boss_out")
    c.music("calm")
    c.say("顾问", "能让你说「不」的，从来不是想通了。")
    c.say("顾问", "而是一点一点攒下来的退路。")
    c.finish()
    chs.append(c)

    c = Chapter("end", None, None, scene_end)
    c.wait(8.5)
    c.sfx("jingle", 5.6)
    c.finish(0.3)
    chs.append(c)

    t = 0.0
    for c in chs:
        c.start = t
        t += c.dur
    return chs, t


CHAPTERS, DURATION = build()
N_FRAMES = int(DURATION * FPS)


# ---------- 渲染一帧 ----------

def render(i):
    t = i / FPS
    ch = CHAPTERS[-1]
    for c in CHAPTERS:
        if c.start <= t < c.start + c.dur:
            ch = c
            break
    lt = t - ch.start
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    ch.scene(img, ch, lt)
    if ch.hud_on:
        draw_hud(img, draw(img), ch, lt)
    draw_items(img, ch, lt)
    arr = np.asarray(img.convert("RGB"))
    k = ch.m("boom")
    if k <= lt < k + 0.8:
        arr = np.roll(arr, (int(math.sin(lt * 70) * 3), int(math.cos(lt * 55) * 3)), axis=(0, 1))
    fade = smooth(lt / 0.35) * smooth((ch.dur - lt) / 0.35)
    if fade < 1:
        arr = (arr.astype(np.float32) * fade).astype(np.uint8)
    return arr.repeat(SCALE, axis=0).repeat(SCALE, axis=1)


# ---------- 声音 ----------

def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tt_(dur):
    return np.arange(int(dur * SR)) / SR


def square(f, dur, duty=0.5, vol=0.1, decay=2.0):
    t = tt_(dur)
    s = np.where((t * f) % 1 < duty, 1.0, -1.0)
    env = (0.55 + 0.45 * np.exp(-t * decay)) * np.minimum(1, (dur - t) / 0.012).clip(0, 1)
    return s * env * vol


def triangle(f, dur, vol=0.2):
    t = tt_(dur)
    s = 4 * np.abs((t * f) % 1 - 0.5) - 1
    return s * np.minimum(1, (dur - t) / 0.01).clip(0, 1) * vol


NOISE = np.random.default_rng(1).uniform(-1, 1, SR * 3)


def noise(dur, decay, vol, hp=False):
    n = NOISE[: int(dur * SR)].copy()
    if hp:
        n = np.diff(np.concatenate([[0], n]))
    return n * np.exp(-tt_(dur) * decay) * vol


def kick():
    t = tt_(0.14)
    f = 50 + 110 * np.exp(-t * 40)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 20) * 0.35


TRACKS = {
    "main": dict(bpm=132, lead_duty=0.25, roots=[36, 33, 29, 31, 36, 33, 29, 31],
                 chords=[(60, 64, 67), (57, 60, 64), (57, 60, 65), (55, 59, 62)] * 2,
                 lead=[72, 76, 79, 76, 74, 76, 72, -1, 72, 69, 72, 76, 74, 72, 69, -1,
                       69, 72, 77, 76, 74, 72, 74, 76, 74, 71, 67, 71, 74, -1, 79, -1,
                       79, 77, 76, 74, 76, 79, 84, -1, 81, 79, 76, 72, 74, 76, 72, -1,
                       77, 76, 74, 72, 69, 72, 74, 77, 79, -1, 74, -1, 71, 74, 72, -1],
                 drums="K.hSK.hS" * 8, vol=1.0),
    "calm": dict(bpm=92, lead_duty=0.125, roots=[36, 31, 33, 29, 36, 31, 33, 29],
                 chords=[(60, 64, 67), (59, 62, 67), (57, 60, 64), (57, 60, 65)] * 2,
                 lead=[76, -1, -1, -1, 74, -1, -1, -1, 74, -1, -1, -1, 71, -1, -1, -1,
                       72, -1, -1, -1, 76, -1, -1, -1, 77, -1, 76, -1, 74, -1, -1, -1,
                       76, -1, -1, -1, 79, -1, -1, -1, 79, -1, 77, -1, 74, -1, -1, -1,
                       72, -1, 74, -1, 76, -1, 72, -1, 69, -1, -1, -1, 72, -1, -1, -1],
                 drums="." * 64, vol=0.8, arp=True),
    "tense": dict(bpm=144, lead_duty=0.5, roots=[33, 33, 29, 28, 33, 33, 29, 28],
                  chords=[(57, 60, 64), (57, 60, 64), (57, 60, 65), (56, 59, 64)] * 2,
                  lead=[69, 0, 72, 0, 76, 0, 75, 0, 76, 0, 72, 0, 69, 0, 71, 0,
                        72, 0, 69, 0, 65, 0, 69, 0, 68, 0, 71, 0, 74, 0, 76, -1] * 2,
                  drums="KhhhKhSh" * 8, vol=0.9),
}
_LOOPS = {}


def track_loop(name):
    if name in _LOOPS:
        return _LOOPS[name]
    sp = TRACKS[name]
    step = 60 / sp["bpm"] / 2
    n = int(64 * step * SR)
    buf = np.zeros(n + SR)

    def add(sig, at):
        s = int(at * SR)
        buf[s:s + len(sig)] += sig[: len(buf) - s]

    lead = sp["lead"]
    i = 0
    while i < 64:
        m = lead[i]
        j = i + 1
        while j < 64 and lead[j] == -1:
            j += 1
        if m > 0:
            add(square(mtof(m), (j - i) * step * 0.92, sp["lead_duty"], 0.075, 3.0), i * step)
        i = j
    for bar in range(8):
        r = sp["roots"][bar]
        ch = sp["chords"][bar]
        for s in range(8):
            at = (bar * 8 + s) * step
            if sp.get("arp"):
                tones = [ch[0], ch[1], ch[2], ch[1] + 12, ch[2], ch[1], ch[0], ch[2]]
                add(triangle(mtof(tones[s] - 12), step * 0.9, 0.12), at)
                if s % 4 == 0:
                    add(triangle(mtof(r), step * 3.8, 0.16), at)
            else:
                add(triangle(mtof(r + (12 if s % 2 else 0)), step * 0.85, 0.2), at)
                if s % 2 == 1:
                    for c in ch:
                        add(square(mtof(c), step * 0.45, 0.5, 0.018, 8.0), at)
            dr = sp["drums"][bar * 8 + s]
            if dr == "K":
                add(kick(), at)
            elif dr == "S":
                add(noise(0.12, 28, 0.14), at)
            elif dr == "h":
                add(noise(0.04, 90, 0.06, hp=True), at)
    loop = buf[:n] * sp["vol"]
    _LOOPS[name] = loop
    return loop


def sfx_sound(name, kw):
    if name == "blip":
        f = {"顾问": 1180, "老板": 520, "朋友": 880, "小林": 760}.get(kw.get("who"), 1000)
        return square(f, 0.035, 0.5, 0.05, 20)
    if name == "cursor":
        return square(1568, 0.035, 0.5, 0.07, 10)
    if name == "select":
        return np.concatenate([square(1319, 0.05, 0.5, 0.08), square(1760, 0.09, 0.5, 0.08, 8)])
    if name == "buzz":
        return square(98, 0.28, 0.5, 0.12, 1) + square(104, 0.28, 0.5, 0.08, 1)
    if name == "coin":
        return np.concatenate([square(988, 0.05, 0.5, 0.07), square(1319, 0.18, 0.5, 0.07, 12)])
    if name == "cost":
        return np.concatenate([square(659, 0.09, 0.5, 0.08), square(494, 0.16, 0.5, 0.08, 6)])
    if name == "down":
        return np.concatenate([square(523, 0.08, 0.5, 0.06), square(392, 0.12, 0.5, 0.06, 6)])
    if name == "tick":
        return square(2093, 0.02, 0.5, 0.05, 30)
    if name == "jingle":
        return np.concatenate([square(mtof(m), 0.07, 0.25, 0.08) for m in (72, 76, 79)] + [square(mtof(84), 0.3, 0.25, 0.08, 5)])
    if name == "fanfare":
        a = np.concatenate([square(mtof(m), d, 0.25, 0.09) for m, d in ((72, 0.1), (72, 0.1), (72, 0.1), (76, 0.3), (79, 0.6))])
        b = np.zeros_like(a)
        tail = sum(square(mtof(m), 0.6, 0.5, 0.03, 3) for m in (60, 64, 67))
        b[-len(tail):] += tail
        return a + b
    if name == "explosion":
        t = tt_(1.6)
        n = np.convolve(NOISE[: len(t)], np.ones(18) / 18, "same") * 3
        rumble = np.sin(2 * np.pi * np.cumsum(40 + 60 * np.exp(-t * 6)) / SR)
        return (n * 0.5 + rumble * 0.4) * np.exp(-t * 2.6)
    if name == "load":
        t = tt_(1.2)
        f = 300 + 900 * t / 1.2
        s = np.where((np.cumsum(f) / SR) % 1 < 0.5, 1.0, -1.0) * 0.05
        return np.concatenate([s, square(1568, 0.08, 0.5, 0.07), square(2093, 0.25, 0.5, 0.07, 8)])
    raise ValueError(name)


def make_audio(path):
    n = int(DURATION * SR)
    music = np.zeros(n)
    fx = np.zeros(n + 3 * SR)
    segs = []
    for c in CHAPTERS:
        for t0, tr in c.music_list:
            segs.append((c.start + t0, tr))
    segs.sort()
    merged = []
    for t0, tr in segs:
        if merged and merged[-1][1] == tr:
            continue
        merged.append((t0, tr))
    for k, (t0, tr) in enumerate(merged):
        if tr is None:
            continue
        t1 = merged[k + 1][0] if k + 1 < len(merged) else DURATION
        s0, s1 = int(t0 * SR), int(t1 * SR)
        loop = track_loop(tr)
        reps = (s1 - s0) // len(loop) + 1
        seg = np.tile(loop, reps)[: s1 - s0].copy()
        fl = min(len(seg), int(0.25 * SR))
        seg[:int(0.03 * SR)] *= np.linspace(0, 1, int(0.03 * SR))
        seg[-fl:] *= np.linspace(1, 0, fl) ** 2 if merged[k + 1:] and merged[k + 1][1] is None else np.linspace(1, 0, fl)
        music[s0:s1] += seg
    for c in CHAPTERS:
        for t0, name, kw in c.sfx_list:
            s = int((c.start + t0) * SR)
            sig = sfx_sound(name, kw)
            fx[s:s + len(sig)] += sig[: len(fx) - s]
    mix = music * 0.55 + fx[:n]
    tt = np.arange(n) / SR
    mix *= np.minimum(1, (DURATION - tt) / 1.2)
    mix = np.tanh(mix * 1.6) / np.tanh(1.6)
    mix /= max(1e-9, np.max(np.abs(mix))) / 0.9
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.stack([pcm, pcm], axis=1).tobytes())


# ---------- 主程序 ----------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"duration {DURATION:.1f}s, {N_FRAMES} frames")
    wav = os.path.join(OUT_DIR, "_life_story.wav")
    make_audio(wav)
    out = os.path.join(OUT_DIR, "life_story.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W * SCALE}x{H * SCALE}", "-r", str(FPS), "-i", "-",
           "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-tune", "animation",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(N_FRAMES):
        proc.stdin.write(render(i).tobytes())
        if i % 300 == 0:
            print(f"frame {i}/{N_FRAMES}")
    proc.stdin.close()
    proc.wait()
    os.remove(wav)
    print("done:", out)


if __name__ == "__main__":
    main()
