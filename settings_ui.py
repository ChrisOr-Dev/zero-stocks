"""Settings screen: up/down colors and refresh interval."""
from PIL import Image, ImageDraw

import config
import keys
from theme import ACCENT, BG, DIM, F_SMALL, F_TEXT, F_TITLE, FG, H, LINE, SEL, W, updown

ITEMS = ['red_up', 'refresh']


class Settings:
    """handle() returns 'close' or None; every change is saved at once."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.sel = 0
        self.dirty = True

    def handle(self, code):
        self.dirty = True
        k = keys.nav(code)
        if k == keys.K_ESC:
            return 'close'
        if k in (keys.K_UP, keys.K_DOWN):
            self.sel = 1 - self.sel
        elif k in (keys.K_ENTER, keys.K_RIGHT, keys.K_LEFT):
            step = -1 if k == keys.K_LEFT else 1
            if ITEMS[self.sel] == 'red_up':
                self.cfg['red_up'] = not self.cfg['red_up']
            else:
                ch = config.REFRESH_CHOICES
                self.cfg['refresh'] = ch[(ch.index(self.cfg['refresh']) + step) % len(ch)]
            config.save(self.cfg)
        return None

    def tick(self):
        pass

    def render(self):
        self.dirty = False
        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((10, 6), 'SETTINGS', font=F_TITLE, fill=ACCENT)
        d.line((8, 25, W - 8, 25), fill=LINE)
        up = updown(self.cfg['red_up'])[0]
        rows = [('Rising color', 'Red up' if self.cfg['red_up'] else 'Green up', up),
                ('Refresh while open', f"{self.cfg['refresh']} s", FG)]
        for i, (left, right, col) in enumerate(rows):
            y = 36 + i * 24
            if i == self.sel:
                d.rounded_rectangle((4, y - 3, W - 4, y + 17), radius=4, fill=SEL)
            d.text((12, y), left, font=F_TEXT, fill=FG)
            d.text((W - 12, y), right, font=F_TEXT, fill=col, anchor='ra')
        d.text((12, 94), 'Red up is the Taiwan / China convention.', font=F_SMALL, fill=DIM)
        d.text((12, 110), 'Closed markets refresh every 5 minutes.', font=F_SMALL, fill=DIM)
        d.text((10, H - 15), 'F/X select  ENTER change  ESC back', font=F_SMALL, fill=DIM)
        return img
