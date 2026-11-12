"""Screen size, colors and fonts shared by all screens."""
import os

from PIL import ImageFont

W, H = 320, 170
FONT_DIRS = ['/usr/share/APPLaunch/share/font', os.path.dirname(os.path.abspath(__file__))]

BG = (12, 15, 22)
FG = (236, 238, 242)
DIM = (130, 140, 158)
FAINT = (70, 80, 98)
LINE = (36, 44, 58)
SEL = (30, 40, 58)
ACCENT = (110, 180, 255)
WARN = (232, 178, 70)
GREEN = (38, 186, 120)
RED = (232, 72, 72)
FLAT = (120, 128, 142)


def font(name, size):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


F_TITLE = font('JetBrainsMono-Bold.ttf', 13)
F_SYM = font('JetBrainsMono-Bold.ttf', 12)
F_TEXT = font('JetBrainsMono-Regular.ttf', 12)
F_SMALL = font('JetBrainsMono-Regular.ttf', 11)
F_TINY = font('JetBrainsMono-Regular.ttf', 10)
F_BOLD_SMALL = font('JetBrainsMono-Bold.ttf', 11)
F_PRICE = font('Montserrat-Bold.ttf', 22)


def updown(red_up):
    """(up, down) colors: green up by default, red up for the Asian convention."""
    return (RED, GREEN) if red_up else (GREEN, RED)


def color_for(delta, red_up):
    if delta is None or delta == 0:
        return FLAT
    up, down = updown(red_up)
    return up if delta > 0 else down


def clip(d, text, fnt, width):
    if d.textlength(text, font=fnt) <= width:
        return text
    while text and d.textlength(text + '...', font=fnt) > width:
        text = text[:-1]
    return text + '...'
