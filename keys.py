"""Keyboard input for the CardputerZero (evdev key codes).

read_keys returns raw key codes, plus SHIFT when a Shift key is held, so text
input can type ':' '?' '&' and capitals; is_down tells whether a key is held. nav() turns a code into a navigation
key: plain F/Z/X/C act as arrows (CardputerZero key spec), Shift is ignored.
"""
import os
import struct

K_ESC, K_BACKSPACE, K_Q, K_R, K_P, K_ENTER, K_S, K_SPACE = 1, 14, 16, 19, 25, 28, 31, 57
K_UP, K_LEFT, K_RIGHT, K_DOWN = 103, 105, 106, 108
SHIFT = 1000
SHIFT_KEYS = (42, 54)
ARROW_ALIASES = {33: K_UP, 44: K_LEFT, 45: K_DOWN, 46: K_RIGHT}

CHARS = {57: ' ', 12: '-', 13: '=', 26: '[', 27: ']', 39: ';', 40: "'", 41: '`', 43: '\\',
         51: ',', 52: '.', 53: '/', 74: '-', 78: '+'}
SHIFTED = {12: '_', 13: '+', 39: ':', 40: '"', 51: '<', 52: '>', 53: '?', 43: '|',
           2: '!', 3: '@', 4: '#', 5: '$', 6: '%', 7: '^', 8: '&', 9: '*', 10: '(', 11: ')'}
for _i, _c in enumerate('1234567890'):
    CHARS[2 + _i] = _c
for _row, _start in (('qwertyuiop', 16), ('asdfghjkl', 30), ('zxcvbnm', 44)):
    for _i, _c in enumerate(_row):
        CHARS[_start + _i] = _c

_down = set()   # keys currently held, from press/release events
_EVENT = struct.calcsize('llHHi')


def read_keys(fd):
    """Codes of keys pressed since the last call, in order (+SHIFT if shifted)."""
    if fd is None:
        return []
    try:
        buf = os.read(fd, _EVENT * 64)
    except BlockingIOError:
        return []
    pressed = []
    for i in range(0, len(buf) - _EVENT + 1, _EVENT):
        _, _, etype, code, value = struct.unpack_from('llHHi', buf, i)
        if etype != 1:
            continue
        if value == 0:
            _down.discard(code)
            continue
        _down.add(code)
        if value == 1 and code not in SHIFT_KEYS:
            pressed.append(code + (SHIFT if _down.intersection(SHIFT_KEYS) else 0))
    return pressed


def is_down(code):
    """Whether the key is held now (as of the last read_keys)."""
    return code in _down


def nav(code):
    """The code for navigation: Shift dropped, F/Z/X/C as arrows."""
    base = code % SHIFT
    return ARROW_ALIASES.get(base, base)


def to_char(code):
    """The character a key types, or None."""
    base, shifted = code % SHIFT, code >= SHIFT
    if shifted and base in SHIFTED:
        return SHIFTED[base]
    c = CHARS.get(base)
    return c.upper() if c and shifted else c
