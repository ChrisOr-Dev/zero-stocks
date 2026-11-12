"""Watchlist and K-line (candlestick) screens."""
import time

from PIL import Image, ImageDraw

import quotes as Q
from theme import (ACCENT, BG, DIM, F_BOLD_SMALL, F_PRICE, F_SMALL, F_SYM, F_TEXT, F_TINY,
                   F_TITLE, FAINT, FG, FLAT, GREEN, H, LINE, SEL, W, WARN, clip, color_for,
                   updown)

ROW_Y, ROW_H = 29, 20
ROWS = (H - ROW_Y - 18) // ROW_H
CANDLE_W = 5                       # slot per candle: 3 px body + 2 px gap
CHART = (8, 52, W - 50, 124)       # candle area; the price axis sits to its right
VOL = (8, 127, W - 50, 139)
STATE_TAG = {'open': ('OPEN', GREEN), 'pre': ('PRE', WARN), 'post': ('AFTER', WARN),
             'closed': ('CLOSED', FAINT)}


def dotted(d, x0, x1, y, fill, step=4):
    for x in range(int(x0), int(x1), step):
        d.point((x, y), fill=fill)
        d.point((x + 1, y), fill=fill)


def sparkline(d, box, quote, red_up):
    """Intraday close line; x spans the whole session so a partial day stays partial."""
    x0, y0, x1, y1 = box
    pts = quote.get('points') or []
    if len(pts) < 2:
        dotted(d, x0, x1, (y0 + y1) // 2, FAINT)
        return
    prev = quote.get('prev')
    vals = [c for _, c in pts] + ([prev] if prev else [])
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    reg = quote.get('periods', {}).get('regular')
    t0 = pts[0][0]
    t1 = max(pts[-1][0], t0 + (reg[1] - reg[0] if reg else 0))
    tspan = (t1 - t0) or 1

    def xy(t, v):
        return x0 + (t - t0) / tspan * (x1 - x0), y1 - (v - lo) / span * (y1 - y0)

    if prev:
        dotted(d, x0, x1, round(xy(t0, prev)[1]), FAINT)
    d.line([xy(t, c) for t, c in pts], fill=color_for(Q.change(quote)[0], red_up), width=1)


def change_chip(d, box, quote, red_up):
    _, pct = Q.change(quote)
    col = color_for(pct, red_up)
    d.rounded_rectangle(box, radius=3, fill=col)
    text = '--' if pct is None else f'{pct:+.2f}%'
    d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2 + 1), text, font=F_BOLD_SMALL,
           fill=BG if col != FLAT else FG, anchor='mm')


def market_states(symbols, quotes, now):
    """[(market, state)] for each market in the watchlist, in list order."""
    seen = {}
    for s in symbols:
        q = quotes.get(s)
        m = Q.market_of(s, '')
        if q and m not in seen and m != 'Other':
            seen[m] = Q.state(q, now)
    return list(seen.items())


def footer(d, status, hint):
    text, col = status
    d.text((10, H - 15), text, font=F_SMALL, fill=col)
    d.text((W - 10, H - 15), hint, font=F_SMALL, fill=FAINT, anchor='ra')


def render_list(symbols, quotes, sel, top, red_up, now, status, confirm=None):
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((10, 6), 'STOCKS', font=F_TITLE, fill=ACCENT)
    x = 70
    for market, st in market_states(symbols, quotes, now):
        d.text((x, 8), market, font=F_TINY, fill=DIM)
        x += d.textlength(market, font=F_TINY) + 3
        d.ellipse((x, 11, x + 5, 16), fill=STATE_TAG[st][1])
        x += 12
    d.text((W - 10, 6), time.strftime('%H:%M', time.localtime(now)), font=F_TITLE, fill=DIM,
           anchor='ra')
    d.line((8, 25, W - 8, 25), fill=LINE)

    if not symbols:
        d.text((W / 2, 80), 'Watchlist is empty. Press A to add.', font=F_TEXT, fill=DIM,
               anchor='mm')
    for i, sym in enumerate(symbols[top:top + ROWS]):
        y = ROW_Y + i * ROW_H
        if top + i == sel:
            d.rounded_rectangle((4, y - 1, W - 4, y + ROW_H - 3), radius=4, fill=SEL)
        q = quotes.get(sym)
        d.text((10, y + 2), clip(d, Q.label(sym), F_SYM, 66), font=F_SYM, fill=FG)
        if not q:
            d.text((W - 10, y + 2), 'loading', font=F_SMALL, fill=FAINT, anchor='ra')
            continue
        sparkline(d, (82, y + 2, 148, y + ROW_H - 6), q, red_up)
        d.text((246, y + 2), Q.fmt_price(q['price'], q['decimals']), font=F_TEXT, fill=FG,
               anchor='ra')
        change_chip(d, (252, y + 1, W - 8, y + ROW_H - 5), q, red_up)
    if len(symbols) > ROWS:  # scroll indicator
        bar_h = max(8, (H - 18 - ROW_Y) * ROWS // len(symbols))
        by = ROW_Y + (H - 18 - ROW_Y - bar_h) * top // max(1, len(symbols) - ROWS)
        d.rectangle((W - 3, by, W - 2, by + bar_h), fill=FAINT)

    if confirm:
        d.rectangle((0, H - 20, W, H), fill=LINE)
        d.text((10, H - 16), f'Remove {Q.label(confirm)}?  ENTER yes  ESC no', font=F_SMALL,
               fill=FG)
    else:
        footer(d, status, 'A add  S setup  hold ESC')
    return img


def fmt_span(candles, interval, off):
    def fmt(t, f):
        return time.strftime(f, time.gmtime(t + off))
    a, b = candles[0][0], candles[-1][0]
    if interval in ('1W', '1M'):
        return f"{fmt(a, '%Y/%m')}-{fmt(b, '%Y/%m')}"
    if interval == '1D':
        return f"{fmt(a, '%y/%m/%d')}-{fmt(b, '%m/%d')}"
    if fmt(a, '%m/%d') == fmt(b, '%m/%d'):
        return f"{fmt(a, '%m/%d %H:%M')}-{fmt(b, '%H:%M')}"
    return f"{fmt(a, '%m/%d %H:%M')}-{fmt(b, '%m/%d')}"


def fmt_axis(v, decimals):
    """Price-axis label: fits the 48 px axis (no decimals from 1,000 up, at most 2 from 1 up)."""
    return Q.fmt_price(v, 0 if abs(v) >= 1000 else decimals if abs(v) < 1 else min(decimals, 2))


def draw_candles(d, candles, red_up, decimals):
    x0, y0, x1, y1 = CHART
    n = (x1 - x0) // CANDLE_W
    cs = candles[-n:]
    hi, lo = max(c[2] for c in cs), min(c[3] for c in cs)
    span = (hi - lo) or abs(hi) * 0.01 or 1
    up, down = updown(red_up)

    def y(v):
        return round(y1 - (v - lo) / span * (y1 - y0))

    for gy in (y0, (y0 + y1) // 2, y1):
        dotted(d, x0, x1, gy, LINE, 3)
    vmax = max(c[5] for c in cs) or 1
    for i, (_, o, h, low, c, v) in enumerate(cs):
        x = x1 - (len(cs) - i) * CANDLE_W + CANDLE_W // 2
        col = up if c >= o else down
        d.line((x, y(h), x, y(low)), fill=col)
        top, bot = y(max(o, c)), y(min(o, c))
        d.rectangle((x - 1, top, x + 1, max(bot, top)), fill=col)
        if v:
            vh = max(1, round((VOL[3] - VOL[1]) * v / vmax))
            d.rectangle((x - 1, VOL[3] - vh, x + 1, VOL[3]), fill=tuple(k // 2 for k in col))

    ax = x1 + 4
    d.text((ax, y0 - 6), fmt_axis(hi, decimals), font=F_TINY, fill=DIM)
    d.text((ax, y1 - 6), fmt_axis(lo, decimals), font=F_TINY, fill=DIM)
    last = cs[-1]
    ly = y(last[4])
    col = up if last[4] >= last[1] else down
    dotted(d, x0, x1, ly, col, 3)
    d.rectangle((x1 + 2, ly - 6, W - 2, ly + 6), fill=col)
    d.text((ax, ly), fmt_axis(last[4], decimals), font=F_TINY, fill=BG, anchor='lm')
    return cs


def render_detail(quote, chart, interval, red_up, now, status):
    """quote: watchlist quote (price, change); chart: {'candles', 'gmtoffset'} or None."""
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    sym = quote['symbol']
    d.text((10, 5), Q.label(sym), font=F_TITLE, fill=ACCENT)
    tag, tag_col = STATE_TAG[Q.state(quote, now)]
    tw = d.textlength(tag, font=F_TINY) + 10
    d.rounded_rectangle((W - 8 - tw, 5, W - 8, 19), radius=3, outline=tag_col)
    d.text((W - 8 - tw / 2, 12), tag, font=F_TINY, fill=tag_col, anchor='mm')
    name_x = 16 + d.textlength(Q.label(sym), font=F_TITLE)
    d.text((name_x, 7), clip(d, quote['name'], F_SMALL, W - 22 - tw - name_x), font=F_SMALL,
           fill=DIM)

    delta, pct = Q.change(quote)
    col = color_for(delta, red_up)
    price = Q.fmt_price(quote['price'], quote['decimals'])
    d.text((10, 21), price, font=F_PRICE, fill=FG)
    px = 16 + d.textlength(price, font=F_PRICE)
    if delta is not None:
        d.text((px, 24), f"{delta:+,.{quote['decimals']}f}", font=F_BOLD_SMALL, fill=col)
        d.text((px, 36), f'{pct:+.2f}%', font=F_BOLD_SMALL, fill=col)
    dec = quote['decimals']
    d.text((W - 10, 23), f"H {Q.fmt_price(quote['high'], dec)}  L {Q.fmt_price(quote['low'], dec)}",
           font=F_TINY, fill=DIM, anchor='ra')
    d.text((W - 10, 36), f"Vol {Q.fmt_volume(quote['volume'])}  {quote['currency']}",
           font=F_TINY, fill=DIM, anchor='ra')

    span = ''
    if chart and chart['candles']:
        cs = draw_candles(d, chart['candles'], red_up, dec)
        span = fmt_span(cs, interval, chart['gmtoffset'])
    else:
        d.text(((CHART[0] + CHART[2]) / 2, 90), 'loading candles...' if chart is None
               else 'no candles for this period', font=F_SMALL, fill=FAINT, anchor='mm')

    x = 8
    for lab in Q.INTERVAL_LABELS:
        w = d.textlength(lab, font=F_TINY) + 8
        if lab == interval:
            d.rounded_rectangle((x, 142, x + w, 154), radius=3, fill=ACCENT)
        d.text((x + w / 2, 148), lab, font=F_TINY, fill=BG if lab == interval else DIM, anchor='mm')
        x += w + 2
    d.text((W - 8, 148), span, font=F_TINY, fill=DIM, anchor='rm')
    footer(d, status, 'Z/C period  F/X stock  ESC')
    return img
