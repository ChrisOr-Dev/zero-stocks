import os
import tempfile
import unittest
from unittest import mock

import config
import keys
import quotes as Q
import views
import zero_stocks as Z
from add_ui import AddSymbol
from hold_exit import ExitHold
from settings_ui import Settings

T0 = 1794493800  # a regular-session open (US)


def meta(symbol='AAPL', price=110.0, prev=100.0, **kw):
    m = {'symbol': symbol, 'shortName': symbol, 'regularMarketPrice': price,
         'chartPreviousClose': prev, 'priceHint': 2, 'currency': 'USD', 'gmtoffset': -18000,
         'currentTradingPeriod': {
             'pre': {'start': T0 - 19800, 'end': T0},
             'regular': {'start': T0, 'end': T0 + 23400},
             'post': {'start': T0 + 23400, 'end': T0 + 37800}}}
    m.update(kw)
    return m


def quote(symbol='AAPL', price=110.0, prev=100.0, points=None):
    pts = points or [[T0 + i * 300, 100 + i] for i in range(11)]
    return Q.quote_from(meta(symbol, price, prev), [p[0] for p in pts], [p[1] for p in pts])


def candles(n=80):
    return [[T0 + i * 300, 100 + i % 7, 104 + i % 7, 98 + i % 7, 101 + (i * 3) % 9, 1000 + i]
            for i in range(n)]


class TestQuotes(unittest.TestCase):
    def test_parse_spark_skips_missing_and_nulls(self):
        data = {'spark': {'result': [
            {'symbol': 'AAPL', 'response': [{'meta': meta(), 'timestamp': [1, 2, 3],
                                             'indicators': {'quote': [{'close': [1, None, 3]}]}}]},
            {'symbol': 'BAD.HK', 'response': []}]}}
        out = Q.parse_spark(data)
        self.assertEqual(list(out), ['AAPL'])
        self.assertEqual(out['AAPL']['points'], [[1, 1], [3, 3]])
        self.assertEqual(out['AAPL']['prev'], 100.0)

    def test_parse_chart_drops_incomplete_candles(self):
        data = {'chart': {'result': [{'meta': {'gmtoffset': 28800}, 'timestamp': [1, 2],
                                      'indicators': {'quote': [{'open': [1, None], 'high': [2, 2],
                                                                'low': [0, 0], 'close': [1.5, 1],
                                                                'volume': [None, 5]}]}}]}}
        out = Q.parse_chart(data)
        self.assertEqual(out['candles'], [[1, 1, 2, 0, 1.5, 0]])
        self.assertEqual(out['gmtoffset'], 28800)

    def test_parse_chart_fills_live_close(self):
        # Yahoo leaves today's daily close null after the session; use the live price.
        data = {'chart': {'result': [{'meta': {'regularMarketPrice': 398.8}, 'timestamp': [1, 2],
                                      'indicators': {'quote': [{'open': [414, 404], 'high': [415, 405.8],
                                                                'low': [406, 395.8], 'close': [409.6, None],
                                                                'volume': [10, 20]}]}}]}}
        self.assertEqual(Q.parse_chart(data, '1d')['candles'][-1], [2, 404, 405.8, 395.8, 398.8, 20])

    def test_parse_chart_merges_split_week(self):
        # The current week arrives as last week's bar plus a separate live bar.
        week, day = 7 * 86400, 86400
        data = {'chart': {'result': [{'meta': {}, 'timestamp': [0, week, week + 3 * day],
                                      'indicators': {'quote': [{'open': [1, 425, 404], 'high': [2, 428, 405],
                                                                'low': [0, 406, 395], 'close': [1, 409, 398],
                                                                'volume': [1, 50, 25]}]}}]}}
        self.assertEqual(Q.parse_chart(data, '1wk')['candles'],
                         [[0, 1, 2, 0, 1, 1], [week, 425, 428, 395, 398, 75]])
        self.assertEqual(len(Q.parse_chart(data, '1d')['candles']), 3)

    def test_parse_chart_error(self):
        with self.assertRaisesRegex(ValueError, 'No data'):
            Q.parse_chart({'chart': {'result': None, 'error': {'description': 'No data found'}}})

    def test_market_of(self):
        self.assertEqual(Q.market_of('0700.HK'), 'HK')
        self.assertEqual(Q.market_of('6488.TWO'), 'TW')
        self.assertEqual(Q.market_of('600519.SS'), 'CN')
        self.assertEqual(Q.market_of('^HSI', 'HKG'), 'HK')
        self.assertEqual(Q.market_of('AAPL', 'NMS'), 'US')
        self.assertEqual(Q.market_of('HSBA.L'), 'Other')

    def test_search_query_pads_hk_codes(self):
        self.assertEqual(Q.search_query(' 700 ', 'HK'), '0700')
        self.assertEqual(Q.search_query('700', 'TW'), '700')
        self.assertEqual(Q.search_query('tencent', 'HK'), 'tencent')

    def test_filter_results_by_market(self):
        items = [{'symbol': '0700.HK', 'exchange': 'HKG', 'quoteType': 'EQUITY', 'shortname': 'TENCENT'},
                 {'symbol': 'TCEHY', 'exchange': 'PNK', 'quoteType': 'EQUITY'},
                 {'symbol': 'BTC-USD', 'exchange': 'CCC', 'quoteType': 'CRYPTOCURRENCY'},
                 {'symbol': 'X261113P00700000', 'exchange': 'OPR', 'quoteType': 'OPTION'}]
        sym = lambda m: [r['symbol'] for r in Q.filter_results(items, m)]
        self.assertEqual(sym('HK'), ['0700.HK'])
        self.assertEqual(sym('US'), ['TCEHY'])
        self.assertEqual(sym('All'), ['0700.HK', 'TCEHY', 'BTC-USD'])

    def test_state(self):
        q = quote()
        self.assertEqual(Q.state(q, T0 - 60), 'pre')
        self.assertEqual(Q.state(q, T0 + 60), 'open')
        self.assertEqual(Q.state(q, T0 + 23400 + 60), 'post')
        self.assertEqual(Q.state(q, T0 + 40000), 'closed')
        self.assertEqual(Q.state({}, T0), 'closed')

    def test_change_and_format(self):
        d, p = Q.change(quote(price=110, prev=100))
        self.assertAlmostEqual(d, 10)
        self.assertAlmostEqual(p, 10)
        self.assertEqual(Q.change({'price': 1, 'prev': None}), (None, None))
        self.assertEqual(Q.fmt_price(7626.0234), '7,626.02')
        self.assertEqual(Q.fmt_price(0.1234, 4), '0.1234')
        self.assertEqual(Q.fmt_price(None), '--')
        self.assertEqual(Q.fmt_volume(16290791), '16.3M')
        self.assertEqual(Q.fmt_volume(0), '--')


class TestViews(unittest.TestCase):
    def test_fmt_span(self):
        cs = [[T0, 0, 0, 0, 0, 0], [T0 + 3600, 0, 0, 0, 0, 0]]
        self.assertEqual(views.fmt_span(cs, '5m', -18000), '11/12 09:30-10:30')
        self.assertEqual(views.fmt_span(cs, '1M', -18000), '2026/11-2026/11')

    def test_axis_labels_fit(self):
        self.assertEqual(views.fmt_axis(2590.0, 2), '2,590')
        self.assertEqual(views.fmt_axis(398.8, 3), '398.80')
        self.assertEqual(views.fmt_axis(0.1234, 4), '0.1234')

    def test_render_screens(self):
        qs = {'AAPL': quote(), '0700.HK': quote('0700.HK', 90, 100)}
        img = views.render_list(['AAPL', '0700.HK', 'GONE'], qs, 1, 0, False, T0 + 60,
                                ('updated 3s ago', (1, 1, 1)), confirm='AAPL')
        self.assertEqual(img.size, (320, 170))
        for chart in (None, {'candles': [], 'gmtoffset': 0}, {'candles': candles(), 'gmtoffset': 0},
                      {'candles': candles(1), 'gmtoffset': 0}):
            img = views.render_detail(qs['AAPL'], chart, '5m', True, T0, ('', (1, 1, 1)))
            self.assertEqual(img.size, (320, 170))

    def test_candles_use_up_and_down_colors(self):
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (320, 170))
        flat = [[T0, 100, 101, 99, 100, 0], [T0 + 60, 100, 105, 95, 104, 10]]
        views.draw_candles(ImageDraw.Draw(img), flat, False, 2)
        x = views.CHART[2] - views.CANDLE_W + views.CANDLE_W // 2
        self.assertEqual(img.getpixel((x, 90))[:3], (38, 186, 120))  # rising candle green


class AppTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        p = mock.patch.object(config, 'PATH', os.path.join(tmp, 'cfg.json'))
        p.start()
        self.addCleanup(p.stop)
        self.app = Z.App()
        self.app.cfg['symbols'] = ['A', 'B', 'C']
        self.hold = ExitHold()

    def key(self, code):
        return self.app.handle(code, self.hold, 0)


class TestApp(AppTest):
    def test_move_and_reorder(self):
        self.key(45)                       # X down
        self.assertEqual(self.app.sel, 1)
        self.key(33 + keys.SHIFT)          # Shift+F moves B up
        self.assertEqual(self.app.symbols, ['B', 'A', 'C'])
        self.assertEqual(self.app.sel, 0)
        self.assertEqual(config.load()['symbols'], ['B', 'A', 'C'])

    def test_remove_needs_confirmation(self):
        self.key(keys.K_BACKSPACE)
        self.key(keys.K_ESC)
        self.assertEqual(self.app.symbols, ['A', 'B', 'C'])
        self.assertIsNone(self.hold.start)  # ESC cancelled, did not start the exit hold
        self.key(keys.K_BACKSPACE)
        self.key(keys.K_ENTER)
        self.assertEqual(self.app.symbols, ['B', 'C'])

    def test_detail_interval_and_stock_keys(self):
        self.app.fetcher = Z.Fetcher(self.app.cfg)
        self.key(keys.K_ENTER)
        self.assertEqual(self.app.fetcher.want, ('A', '5m'))
        self.key(46)                       # C: next candle period
        self.assertEqual(self.app.fetcher.want, ('A', '15m'))
        self.assertEqual(config.load()['interval'], '15m')
        self.key(44)                       # Z: previous
        self.key(44)
        self.assertEqual(self.app.cfg['interval'], '1m')
        self.key(45)                       # X: next stock
        self.assertEqual(self.app.fetcher.want, ('B', '1m'))
        self.key(keys.K_ESC)
        self.assertEqual(self.app.view, 'list')
        self.assertIsNone(self.app.fetcher.want)
        self.assertIsNone(self.hold.start)

    def test_add_flow(self):
        self.key(Z.K_A)
        for c in (11, 8, 11):              # types 0 7 0
            self.key(c)
        self.key(15)                       # TAB: US -> HK
        self.assertEqual(self.app.sub.market, 'HK')
        self.key(keys.K_ENTER)
        self.app.sub.tick(search=lambda text, m: [{'symbol': '0700.HK', 'name': 'TENCENT',
                                                   'exchange': 'HKG'}])
        self.key(keys.K_ENTER)
        self.assertEqual(self.app.symbols[-1], '0700.HK')
        self.assertEqual(self.app.sel, 3)
        self.key(keys.K_ENTER)             # already added: no duplicate
        self.assertEqual(self.app.symbols.count('0700.HK'), 1)
        self.key(keys.K_ESC)
        self.key(keys.K_ESC)
        self.assertIsNone(self.app.sub)
        self.assertEqual(config.load()['market'], 'HK')

    def test_settings(self):
        s = Settings(self.app.cfg)
        s.handle(keys.K_ENTER)
        self.assertTrue(config.load()['red_up'])
        s.handle(45)
        s.handle(keys.K_ENTER)
        self.assertEqual(config.load()['refresh'], 30)
        self.assertEqual(s.handle(keys.K_ESC), 'close')

    def test_add_search_failure_message(self):
        a = AddSymbol([], 'TW')
        a.text, a.state = 'x', 'searching'

        def boom(*_):
            raise OSError('offline')
        a.tick(search=boom)
        self.assertEqual(a.state, 'results')
        self.assertIn('offline', a.msg)
        self.assertEqual(a.render().size, (320, 170))


class TestFetcher(AppTest):
    def test_unknown_symbol_is_not_refetched_every_second(self):
        f = Z.Fetcher(self.app.cfg)
        calls = []
        with mock.patch.object(Q, 'fetch_quotes', lambda s: calls.append(s) or {'A': quote('A')}), \
                mock.patch.object(Z, 'save_cache'):
            f.step(T0 + 60)
            f.step(T0 + 61)
            self.assertEqual(len(calls), 1)         # B, C missing but already asked
            f.step(T0 + 60 + 15)                    # market open: refresh after 15 s
            self.assertEqual(len(calls), 2)

    def test_error_backs_off(self):
        f = Z.Fetcher(self.app.cfg)
        calls = []

        def fail(s):
            calls.append(s)
            raise OSError('down')
        with mock.patch.object(Q, 'fetch_quotes', fail):
            f.step(0)
            f.step(1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(f.error, 'down')


if __name__ == '__main__':
    unittest.main()
