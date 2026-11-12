"""Watchlist and preferences in ~/.config/zero-stocks.json."""
import json
import os

from quotes import INTERVAL_LABELS

PATH = os.path.expanduser('~/.config/zero-stocks.json')
DEFAULT_SYMBOLS = ['^GSPC', '^IXIC', 'AAPL', 'NVDA', 'MSFT', 'TSLA', 'AMZN', 'GOOGL']
REFRESH_CHOICES = [10, 15, 30, 60]
DEFAULTS = {'symbols': DEFAULT_SYMBOLS, 'red_up': False, 'refresh': 15, 'interval': '5m',
            'market': 'US'}


def load():
    cfg = dict(DEFAULTS, symbols=list(DEFAULT_SYMBOLS))
    try:
        with open(PATH) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return cfg
    if isinstance(raw.get('symbols'), list):
        cfg['symbols'] = [str(s) for s in raw['symbols']]
    cfg['red_up'] = bool(raw.get('red_up', False))
    if raw.get('refresh') in REFRESH_CHOICES:
        cfg['refresh'] = raw['refresh']
    if raw.get('interval') in INTERVAL_LABELS:
        cfg['interval'] = raw['interval']
    if isinstance(raw.get('market'), str):
        cfg['market'] = raw['market']
    return cfg


def save(cfg):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({k: cfg[k] for k in DEFAULTS}, f)
    os.replace(tmp, PATH)
