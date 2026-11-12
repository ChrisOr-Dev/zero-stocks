"""Add-to-watchlist screen: pick a market, type a name or code, choose a result."""
from PIL import Image, ImageDraw

import keys
import quotes as Q
from theme import ACCENT, BG, DIM, F_SMALL, F_SYM, F_TEXT, F_TINY, F_TITLE, FAINT, FG, GREEN, \
    H, LINE, RED, SEL, W, clip

K_TAB = 15
MAX_INPUT = 30
ROW_H = 18
ROWS = 6
EXAMPLES = {'US': 'e.g. AAPL, apple, ^GSPC', 'HK': 'e.g. 700, tencent, ^HSI',
            'TW': 'e.g. 2330, 6488, ^TWII', 'CN': 'e.g. 600519, kweichow',
            'JP': 'e.g. 7203, toyota', 'All': 'e.g. BTC-USD, GC=F, HSBA.L'}


class AddSymbol:
    """handle() returns 'close', ('add', symbol) or None."""

    def __init__(self, existing, market='US'):
        self.existing = set(existing)
        self.market = market if market in Q.MARKETS else 'US'
        self.state = 'input'  # input | searching | results
        self.text = ''
        self.results = []
        self.sel = 0
        self.msg = ''
        self.dirty = True

    def handle(self, code):
        self.dirty = True
        if self.state == 'input':
            return self._input_key(code)
        if self.state == 'results':
            return self._results_key(code)
        return None

    def _cycle(self, step):
        i = Q.MARKETS.index(self.market)
        self.market = Q.MARKETS[(i + step) % len(Q.MARKETS)]

    def _input_key(self, code):
        base = code % keys.SHIFT
        if base == keys.K_ESC:
            return 'close'
        if base in (K_TAB, keys.K_RIGHT):
            self._cycle(1)
        elif base == keys.K_LEFT:
            self._cycle(-1)
        elif base == keys.K_BACKSPACE:
            self.text = self.text[:-1]
        elif base == keys.K_ENTER and self.text.strip():
            self.state = 'searching'
        else:
            c = keys.to_char(code)
            if c and len(self.text) < MAX_INPUT:
                self.text += c
        return None

    def _results_key(self, code):
        k = keys.nav(code)
        if k == keys.K_ESC:
            self.state = 'input'
        elif k == keys.K_UP and self.results:
            self.sel = (self.sel - 1) % len(self.results)
        elif k == keys.K_DOWN and self.results:
            self.sel = (self.sel + 1) % len(self.results)
        elif k == keys.K_ENTER and self.results:
            sym = self.results[self.sel]['symbol']
            if sym not in self.existing:
                self.existing.add(sym)
                return ('add', sym)
        return None

    def tick(self, search=Q.search):
        """Run a pending search; called by the main loop after a frame is drawn."""
        if self.state != 'searching':
            return
        try:
            self.results = search(self.text, self.market)
            self.msg = '' if self.results else f'No {self.market} results. ESC to edit.'
        except Exception as e:
            self.results, self.msg = [], f'Search failed: {e}'[:44]
        self.state, self.sel, self.dirty = 'results', 0, True

    def render(self):
        self.dirty = False
        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((10, 6), 'ADD STOCK', font=F_TITLE, fill=ACCENT)
        x = W - 8
        for m in reversed(Q.MARKETS):
            w = d.textlength(m, font=F_TINY) + 8
            x -= w
            if m == self.market:
                d.rounded_rectangle((x, 6, x + w, 19), radius=3, fill=ACCENT)
            d.text((x + w / 2, 13), m, font=F_TINY, fill=BG if m == self.market else DIM,
                   anchor='mm')
            x -= 2
        d.line((8, 25, W - 8, 25), fill=LINE)
        if self.state == 'results':
            self._draw_results(d)
        else:
            self._draw_input(d)
        return img

    def _draw_input(self, d):
        d.text((12, 34), f'{self.market} name or code ({EXAMPLES[self.market]})', font=F_TINY,
               fill=DIM)
        d.rounded_rectangle((8, 52, W - 8, 76), radius=4, outline=ACCENT)
        shown = self.text
        while shown and d.textlength(shown + '_', font=F_TEXT) > W - 28:
            shown = shown[1:]
        cursor = '' if self.state == 'searching' else '_'
        d.text((14, 57), shown + cursor, font=F_TEXT, fill=FG)
        if self.state == 'searching':
            d.text((12, 86), 'Searching...', font=F_TEXT, fill=ACCENT)
        d.text((10, H - 15), 'TAB market  ENTER search  ESC back', font=F_SMALL, fill=DIM)

    def _draw_results(self, d):
        if not self.results:
            d.text((12, 40), self.msg, font=F_TEXT, fill=RED)
        top = max(0, min(self.sel - ROWS + 1, len(self.results) - ROWS))
        for i, r in enumerate(self.results[top:top + ROWS]):
            y = 31 + i * ROW_H
            if top + i == self.sel:
                d.rounded_rectangle((4, y - 2, W - 4, y + ROW_H - 4), radius=4, fill=SEL)
            d.text((10, y), r['symbol'], font=F_SYM, fill=FG)
            added = r['symbol'] in self.existing
            right = 'added' if added else r['exchange']
            d.text((W - 10, y + 1), right, font=F_TINY, fill=GREEN if added else FAINT,
                   anchor='ra')
            d.text((104, y + 1), clip(d, r['name'], F_SMALL, W - 160), font=F_SMALL, fill=DIM)
        d.text((10, H - 15), 'F/X select  ENTER add  ESC back', font=F_SMALL, fill=DIM)
