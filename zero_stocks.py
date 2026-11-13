#!/usr/bin/python3
"""Stocks for the M5Stack CardputerZero (320x170 LCD): a live watchlist with
intraday sparklines, and a K-line (candlestick) chart per stock with a
selectable candle period. Data from Yahoo Finance (no API key).

Usage:
  zero_stocks.py                  run on the LCD
  zero_stocks.py --fetch          fetch the watchlist once and print it
  zero_stocks.py --preview out.png [--detail SYM] [--add] [--settings]
  zero_stocks.py --make-icon out.png
"""
import json
import os
import sys
import threading
import time

import config
import keys
import net
import quotes as Q
import views
from theme import DIM, FAINT, RED, WARN, W, H, F_BOLD_SMALL

CACHE = os.path.expanduser('~/.local/share/zero-stocks/quotes.json')
FB = '/dev/fb0'
KBD = '/dev/input/cardputer-zero-internal'
CLOSED_POLL = 300     # seconds between refreshes when every market is closed
RETRY = 30            # after a failed fetch
K_A, K_S, K_R = 30, 31, 19


def load_cache():
    try:
        with open(CACHE) as f:
            c = json.load(f)
        return c['quotes'], c['at']
    except (OSError, ValueError, KeyError):
        return {}, 0


def save_cache(quotes, at):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'quotes': quotes, 'at': at}, f)
    os.replace(tmp, CACHE)


def fmt_ago(seconds):
    s = max(0, int(seconds))
    if s < 60:
        return f'{s}s ago'
    if s < 3600:
        return f'{s // 60}m ago'
    return f'{s // 3600}h ago'


class Fetcher(threading.Thread):
    """Refreshes the watchlist quotes and the open detail view's candles."""

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.quotes, self.quotes_at = load_cache()
        self.asked = set()
        self.charts = {}      # (symbol, interval) -> {'candles', 'gmtoffset', 'at'}
        self.want = None      # (symbol, interval) shown in the detail view
        self.force = False
        self.retry_at = 0
        self.busy = False
        self.error = None
        self.version = 0
        self.wake = threading.Event()

    def poll_every(self, quote_list, now):
        live = any(Q.state(q, now) != 'closed' for q in quote_list)
        return self.cfg['refresh'] if live else CLOSED_POLL

    def quotes_due(self, now):
        syms = self.cfg['symbols']
        if set(syms) - self.asked:
            return True
        return now - self.quotes_at >= self.poll_every(self.quotes.values(), now)

    def chart_due(self, want, now):
        c = self.charts.get(want)
        q = self.quotes.get(want[0])
        return c is None or now - c['at'] >= self.poll_every([q] if q else [], now)

    def step(self, now):
        force, self.force = self.force, False
        if not force and now < self.retry_at:
            return
        want = self.want
        do_quotes = force or self.quotes_due(now)
        do_chart = want and (force or self.chart_due(want, now))
        if not (do_quotes or do_chart):
            return
        self.busy = True
        self.version += 1
        try:
            if do_quotes:
                syms = list(self.cfg['symbols'])
                self.quotes = Q.fetch_quotes(syms) if syms else {}
                self.asked, self.quotes_at = set(syms), now
                save_cache(self.quotes, self.quotes_at)
            if do_chart:
                chart = Q.fetch_candles(*want)
                chart['at'] = now
                self.charts[want] = chart
            self.error = None
        except Exception as e:
            self.error = str(e) or type(e).__name__
            self.retry_at = now + RETRY
        self.busy = False
        self.version += 1

    def refresh(self):
        self.force = True
        self.wake.set()

    def run(self):
        while True:
            self.step(time.time())
            self.wake.wait(1)
            self.wake.clear()


class App:
    def __init__(self, fetcher=None):
        self.cfg = config.load()
        self.fetcher = fetcher
        self.view = 'list'     # list | detail
        self.sel = self.top = 0
        self.confirm = None    # symbol awaiting remove confirmation
        self.sub = None        # AddSymbol or Settings screen

    @property
    def symbols(self):
        return self.cfg['symbols']

    def _scroll(self):
        n = len(self.symbols)
        self.sel = max(0, min(self.sel, n - 1))
        self.top = max(0, min(self.top, self.sel, n - views.ROWS))
        if self.sel >= self.top + views.ROWS:
            self.top = self.sel - views.ROWS + 1

    def _want(self):
        if self.fetcher:
            self.fetcher.want = ((self.symbols[self.sel], self.cfg['interval'])
                                 if self.view == 'detail' else None)
            self.fetcher.wake.set()

    def handle(self, code, hold, now):
        """One key press. Returns True when the frame must be redrawn."""
        if self.sub:
            result = self.sub.handle(code)
            if result == 'close':
                self.sub = None
            elif isinstance(result, tuple) and result[0] == 'add':
                self.symbols.append(result[1])
                self.cfg['market'] = self.sub.market
                config.save(self.cfg)
                self.sel = len(self.symbols) - 1
                self._scroll()
                if self.fetcher:
                    self.fetcher.wake.set()
            return True
        k, shifted = keys.nav(code), code >= keys.SHIFT
        if self.view == 'detail':
            return self._detail_key(k)
        if self.confirm:
            if k == keys.K_ENTER and self.confirm in self.symbols:
                self.symbols.remove(self.confirm)
                config.save(self.cfg)
                self._scroll()
            self.confirm = None
            return True
        if k == keys.K_ESC:
            hold.press(now)
            return False
        n = len(self.symbols)
        if k in (keys.K_UP, keys.K_DOWN) and n:
            step = -1 if k == keys.K_UP else 1
            if shifted and 0 <= self.sel + step < n:  # Shift+F/X moves the stock
                s = self.symbols
                s[self.sel], s[self.sel + step] = s[self.sel + step], s[self.sel]
                config.save(self.cfg)
                self.sel += step
            elif not shifted:
                self.sel = (self.sel + step) % n
            self._scroll()
        elif k == keys.K_ENTER and n:
            self.view = 'detail'
            self._want()
        elif k == keys.K_BACKSPACE and n:
            self.confirm = self.symbols[self.sel]
        elif k == K_A:
            from add_ui import AddSymbol
            self.sub = AddSymbol(self.symbols, self.cfg['market'])
        elif k == K_S:
            from settings_ui import Settings
            self.sub = Settings(self.cfg)
        elif k == K_R and self.fetcher:
            self.fetcher.refresh()
        else:
            return False
        hold.cancel()
        return True

    def _detail_key(self, k):
        if k == keys.K_ESC:
            self.view = 'list'
        elif k in (keys.K_LEFT, keys.K_RIGHT):
            labels = Q.INTERVAL_LABELS
            i = labels.index(self.cfg['interval']) + (1 if k == keys.K_RIGHT else -1)
            self.cfg['interval'] = labels[i % len(labels)]
            config.save(self.cfg)
        elif k in (keys.K_UP, keys.K_DOWN):
            self.sel = (self.sel + (1 if k == keys.K_DOWN else -1)) % len(self.symbols)
            self._scroll()
        elif k == K_R and self.fetcher:
            self.fetcher.refresh()
            return True
        else:
            return False
        self._want()
        return True

    def status(self, now):
        f = self.fetcher
        if f.error:
            return f.error[:34], RED
        if f.busy:
            return 'updating...', DIM
        if not f.quotes_at:
            return 'waiting for data', WARN
        age = now - f.quotes_at
        return f'updated {fmt_ago(age)}', WARN if age > 2 * CLOSED_POLL else FAINT

    def render(self, now):
        if self.sub:
            return self.sub.render()
        f = self.fetcher
        red_up = self.cfg['red_up']
        if self.view == 'detail':
            sym = self.symbols[self.sel]
            quote = f.quotes.get(sym) or {'symbol': sym, 'name': '', 'price': None, 'prev': None,
                                          'high': None, 'low': None, 'volume': None,
                                          'currency': '', 'decimals': 2, 'periods': {}}
            chart = f.charts.get((sym, self.cfg['interval']))
            return views.render_detail(quote, chart, self.cfg['interval'], red_up, now,
                                       self.status(now))
        return views.render_list(self.symbols, f.quotes, self.sel, self.top, red_up, now,
                                 self.status(now), self.confirm)


def to_rgb565(img):
    import numpy as np
    a = np.asarray(img, dtype=np.uint16)
    v = ((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)
    return v.astype('<u2').tobytes()


def run():
    import signal
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    from hold_exit import ExitHold, bar, BAR_H
    try:
        kbd = os.open(KBD, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        kbd = None
    app = App()
    app.fetcher = fetcher = Fetcher(app.cfg)
    fetcher.start()
    hold = ExitHold()
    last_key, frame, written, shown_bar = None, None, 0, False
    with open(FB, 'r+b', buffering=0) as fb:
        try:
            while True:
                now = time.time()
                dirty = False
                for code in keys.read_keys(kbd):
                    dirty |= app.handle(code, hold, now)
                if app.sub:
                    app.sub.tick()
                    dirty |= app.sub.dirty
                listing = app.view == 'list' and not app.sub
                progress = hold.progress(now, keys.is_down(keys.K_ESC)) if listing else None
                if progress is not None and progress >= 1:
                    break
                key = (fetcher.version, int(now // 5))
                changed = dirty or key != last_key or frame is None
                if changed:
                    frame = to_rgb565(app.render(now))
                    last_key = key
                # write only on change, while the exit bar shows, and once a second
                if changed or progress is not None or shown_bar or now - written >= 1:
                    fb.seek(0)
                    if progress is None:
                        fb.write(frame)
                    else:  # the countdown bar replaces the bottom rows
                        fb.write(frame[:(H - BAR_H) * W * 2])
                        fb.write(to_rgb565(bar(progress, W, F_BOLD_SMALL)))
                    written, shown_bar = now, progress is not None
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            fb.seek(0)
            fb.write(b'\x00' * (W * H * 2))


def make_icon(path, size=100):
    from PIL import Image, ImageDraw
    from theme import BG, GREEN, RED as R
    k = size / 100
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1, fill, r=0):
        d.rounded_rectangle(tuple(round(v * k) for v in (x0, y0, x1, y1)), radius=round(r * k),
                            fill=fill)

    box(4, 4, 96, 96, BG + (255,), 20)
    # (x, wick top, body top, body bottom, wick bottom, rising)
    for x, wt, bt, bb, wb, rising in ((24, 52, 58, 76, 82, False), (40, 40, 46, 66, 72, True),
                                      (56, 48, 54, 64, 70, False), (72, 22, 28, 54, 62, True)):
        col = GREEN if rising else R
        box(x - 1.5, wt, x + 1.5, wb, col)
        box(x - 6, bt, x + 6, bb, col, 2)
    img.save(path)


def main(argv):
    net.prefer_ipv4()
    if '--fetch' in argv:
        cfg = config.load()
        for s, q in Q.fetch_quotes(cfg['symbols']).items():
            _, pct = Q.change(q)
            print(f"{s:10} {Q.fmt_price(q['price'], q['decimals']):>12} "
                  f"{pct if pct is None else round(pct, 2)}%  {Q.state(q, time.time())}")
    elif '--make-icon' in argv:
        make_icon(argv[argv.index('--make-icon') + 1])
    elif '--preview' in argv:
        out = argv[argv.index('--preview') + 1]
        app = App()
        app.fetcher = f = Fetcher(app.cfg)
        f.step(time.time())
        if '--add' in argv:
            from add_ui import AddSymbol
            app.sub = AddSymbol(app.symbols, 'HK')
            app.sub.text = '700'
            app.sub.state = 'searching'
            app.sub.tick()
        elif '--settings' in argv:
            from settings_ui import Settings
            app.sub = Settings(app.cfg)
        elif '--detail' in argv:
            sym = argv[argv.index('--detail') + 1]
            if sym not in app.symbols:
                app.symbols.append(sym)
                f.step(time.time() + CLOSED_POLL)
            app.sel = app.symbols.index(sym)
            if '--interval' in argv:
                app.cfg['interval'] = argv[argv.index('--interval') + 1]
            app.view = 'detail'
            app._want()
            f.step(time.time())
        app.render(time.time()).save(out)
    else:
        run()


if __name__ == '__main__':
    main(sys.argv[1:])
