"""Quotes, candles and symbol search from Yahoo Finance's public endpoints.

Symbols use Yahoo's suffixes: AAPL (US), 0700.HK (Hong Kong), 2330.TW and
6488.TWO (Taiwan), 600519.SS / 000001.SZ (China), 7203.T (Japan), ^GSPC (index).
"""
import json
import urllib.parse
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64) zero-stocks/1.0'}
SPARK_URL = ('https://query1.finance.yahoo.com/v7/finance/spark'
             '?symbols={symbols}&range=1d&interval=5m')
CHART_URL = ('https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
             '?range={range}&interval={interval}')
SEARCH_URL = ('https://query1.finance.yahoo.com/v1/finance/search'
              '?quotesCount=10&newsCount=0&q={q}')
SPARK_BATCH = 20

# Candle period: (label, Yahoo interval, range fetched to have enough candles)
INTERVALS = [('1m', '1m', '1d'), ('5m', '5m', '5d'), ('15m', '15m', '5d'),
             ('30m', '30m', '1mo'), ('1h', '60m', '1mo'), ('1D', '1d', '6mo'),
             ('1W', '1wk', '2y'), ('1M', '1mo', '10y')]
INTERVAL_LABELS = [i[0] for i in INTERVALS]

MARKETS = ['US', 'HK', 'TW', 'CN', 'JP', 'All']
SUFFIX_MARKET = {'HK': 'HK', 'TW': 'TW', 'TWO': 'TW', 'SS': 'CN', 'SZ': 'CN', 'T': 'JP'}
EXCHANGE_MARKET = {'HKG': 'HK', 'TAI': 'TW', 'TWO': 'TW', 'SHH': 'CN', 'SHZ': 'CN', 'JPX': 'JP'}
STOCK_TYPES = {'EQUITY', 'ETF', 'INDEX', 'MUTUALFUND'}
ANY_TYPES = STOCK_TYPES | {'CRYPTOCURRENCY', 'CURRENCY', 'FUTURE'}
INDEX_NAMES = {'^GSPC': 'S&P 500', '^IXIC': 'NASDAQ', '^DJI': 'DOW', '^RUT': 'RUSSELL',
               '^HSI': 'HSI', '^TWII': 'TAIEX', '^N225': 'NIKKEI', '^VIX': 'VIX'}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def market_of(symbol, exchange=''):
    if '.' in symbol:
        return SUFFIX_MARKET.get(symbol.rsplit('.', 1)[1], 'Other')
    return EXCHANGE_MARKET.get(exchange, 'US')


def label(symbol):
    """Short display name for a list row."""
    return INDEX_NAMES.get(symbol, symbol)


def _periods(meta):
    p = meta.get('currentTradingPeriod') or {}
    return {k: [v['start'], v['end']] for k, v in p.items() if 'start' in v and 'end' in v}


def quote_from(meta, timestamps, closes):
    return {
        'symbol': meta['symbol'],
        'name': meta.get('longName') or meta.get('shortName') or meta['symbol'],
        'price': meta.get('regularMarketPrice'),
        'prev': meta.get('chartPreviousClose') or meta.get('previousClose'),
        'high': meta.get('regularMarketDayHigh'),
        'low': meta.get('regularMarketDayLow'),
        'hi52': meta.get('fiftyTwoWeekHigh'),
        'lo52': meta.get('fiftyTwoWeekLow'),
        'volume': meta.get('regularMarketVolume'),
        'currency': meta.get('currency') or '',
        'decimals': meta.get('priceHint', 2),
        'exchange': meta.get('fullExchangeName') or meta.get('exchangeName') or '',
        'gmtoffset': meta.get('gmtoffset', 0),
        'periods': _periods(meta),
        'time': meta.get('regularMarketTime'),
        'points': [[t, c] for t, c in zip(timestamps, closes) if c is not None],
    }


def parse_spark(data):
    """{symbol: quote} from a spark response; unknown symbols are left out."""
    out = {}
    for r in (data.get('spark') or {}).get('result') or []:
        resp = (r.get('response') or [None])[0]
        if not resp or 'meta' not in resp:
            continue
        q = (resp.get('indicators', {}).get('quote') or [{}])[0]
        out[r['symbol']] = quote_from(resp['meta'], resp.get('timestamp') or [], q.get('close') or [])
    return out


def fetch_quotes(symbols):
    out = {}
    for i in range(0, len(symbols), SPARK_BATCH):
        part = ','.join(urllib.parse.quote(s) for s in symbols[i:i + SPARK_BATCH])
        out.update(parse_spark(_get(SPARK_URL.format(symbols=part))))
    return out


BAR_SPAN = {'1wk': 7 * 86400, '1mo': 28 * 86400}


def parse_chart(data, interval=None):
    """Candles [t, open, high, low, close, volume] and the exchange UTC offset."""
    chart = data.get('chart') or {}
    if not chart.get('result'):
        err = chart.get('error') or {}
        raise ValueError(err.get('description') or 'no chart data')
    r = chart['result'][0]
    meta = r.get('meta', {})
    q = (r.get('indicators', {}).get('quote') or [{}])[0]
    ts = r.get('timestamp') or []
    cols = [list(q.get(k) or [None] * len(ts)) for k in ('open', 'high', 'low', 'close', 'volume')]
    if ts and cols[3][-1] is None and meta.get('regularMarketPrice') is not None:
        cols[3][-1] = meta['regularMarketPrice']  # today's bar before Yahoo fills its close
    candles = [[t, o, h, lo, c, v or 0] for t, o, h, lo, c, v in zip(ts, *cols)
               if None not in (o, h, lo, c)]
    span = BAR_SPAN.get(interval)
    if span and len(candles) >= 2 and candles[-1][0] - candles[-2][0] < span:
        last = candles.pop()  # the live part of the current week/month, sent as its own bar
        prev = candles[-1]
        prev[2], prev[3] = max(prev[2], last[2]), min(prev[3], last[3])
        prev[4], prev[5] = last[4], prev[5] + last[5]
    return {'candles': candles, 'gmtoffset': meta.get('gmtoffset', 0)}


def fetch_candles(symbol, interval_label):
    _, interval, rng = INTERVALS[INTERVAL_LABELS.index(interval_label)]
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol), range=rng, interval=interval)
    return parse_chart(_get(url), interval)


def search_query(text, market):
    """HK codes are 4+ digits on Yahoo: 700 -> 0700."""
    text = text.strip()
    if market == 'HK' and text.isdigit():
        return text.zfill(4)
    return text


def filter_results(items, market):
    out = []
    for i in items:
        sym, typ = i.get('symbol'), i.get('quoteType')
        if not sym:
            continue
        m = market_of(sym, i.get('exchange', ''))
        if market == 'All' and typ in ANY_TYPES or m == market and typ in STOCK_TYPES:
            out.append({'symbol': sym, 'name': i.get('shortname') or i.get('longname') or '',
                        'exchange': i.get('exchDisp') or i.get('exchange', '')})
    return out


def search(text, market):
    q = urllib.parse.quote(search_query(text, market))
    return filter_results(_get(SEARCH_URL.format(q=q)).get('quotes') or [], market)


def state(quote, now):
    """'open', 'pre', 'post' or 'closed' from the quote's trading periods."""
    for name in ('regular', 'pre', 'post'):
        p = quote.get('periods', {}).get(name)
        if p and p[0] <= now < p[1]:
            return 'open' if name == 'regular' else name
    return 'closed'


def change(quote):
    """(absolute, percent) change vs the previous close, or (None, None)."""
    p, prev = quote.get('price'), quote.get('prev')
    if p is None or not prev:
        return None, None
    return p - prev, (p - prev) / prev * 100


def fmt_price(v, decimals=2):
    if v is None:
        return '--'
    decimals = max(0, min(4, int(decimals)))
    if abs(v) >= 10000:
        decimals = min(decimals, 2)
    return f'{v:,.{decimals}f}'


def fmt_volume(v):
    if not v:
        return '--'
    for div, unit in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if v >= div:
            return f'{v / div:.1f}{unit}'
    return str(int(v))
