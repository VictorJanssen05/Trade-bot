"""Daytrade-strategieën op minuutkoersen. Alles wordt dezelfde dag weer verkocht.

Dezelfde code wordt gebruikt door intraday_backtest.py en intraday_bot.py,
zodat de live-bot precies doet wat in de backtest getest is.
Elke minuut krijgt de strategie een bar (open/high/low/close/volume, tijd in New York)
en zegt "buy", "sell" of niks.
"""
import math

NO_ENTRY_AFTER = 15 * 60 + 30   # na 15:30 geen nieuwe aankopen
CLOSE_ALL_AT = 15 * 60 + 55     # om 15:55 alles verkopen


def minutes(t):
    return t.hour * 60 + t.minute


class Strategy:
    def new_day(self):
        self.pv = self.vol = 0.0
        self.vwap = None

    def update_vwap(self, b):
        self.pv += (b.high + b.low + b.close) / 3 * b.volume
        self.vol += b.volume
        self.vwap = self.pv / self.vol if self.vol else b.close

    def on_fill(self, price):
        self.entry = price


class OpeningRange(Strategy):
    """Opening range breakout: kijk de eerste 15 minuten wat het hoogste en laagste punt is.
    Breekt de koers daarna boven dat hoogste punt (en boven VWAP) -> kopen.
    Stop op het laagste punt, winst nemen op 2x het risico. Max 1 trade per dag."""
    name = "opening_range"

    def __init__(self, range_min=15, reward=2.0):
        self.range_min, self.reward = range_min, reward

    def new_day(self):
        super().new_day()
        self.hi, self.lo, self.done = -math.inf, math.inf, False

    def on_bar(self, b, in_pos):
        self.update_vwap(b)
        if minutes(b.t) < 9 * 60 + 30 + self.range_min:
            self.hi, self.lo = max(self.hi, b.high), min(self.lo, b.low)
            return None
        if in_pos:
            return "sell" if b.close <= self.stop or b.close >= self.target else None
        if not self.done and b.close > self.hi and b.close > self.vwap:
            return "buy"

    def on_fill(self, price):
        super().on_fill(price)
        self.done = True
        self.stop = self.lo if self.lo < price else price * 0.99
        self.target = price + self.reward * (price - self.stop)


class VwapDip(Strategy):
    """Koop als de koers ver onder de VWAP (gemiddelde prijs van vandaag) zakt en weer omhoog tikt.
    Verkoop zodra hij terug is bij de VWAP, of bij de stop-loss. Max 3 trades per dag."""
    name = "vwap_dip"

    def __init__(self, dip=0.01, max_trades=3):
        self.dip, self.max_trades = dip, max_trades

    def new_day(self):
        super().new_day()
        self.prev, self.trades = None, 0

    def on_bar(self, b, in_pos):
        self.update_vwap(b)
        prev, self.prev = self.prev, b.close
        if minutes(b.t) < 9 * 60 + 45 or prev is None:
            return None
        if in_pos:
            return "sell" if b.close >= self.vwap or b.close <= self.stop else None
        if self.trades < self.max_trades and b.close < self.vwap * (1 - self.dip) and b.close > prev:
            return "buy"

    def on_fill(self, price):
        super().on_fill(price)
        self.trades += 1
        self.stop = price * (1 - self.dip)


class Momentum(Strategy):
    """Volg de beweging: koop als het snelle gemiddelde (10 min) boven het trage (30 min) kruist
    en de koers boven VWAP staat. Verkoop als het weer onder kruist of bij -1%."""
    name = "momentum"

    def __init__(self, fast=10, slow=30, stop=0.01):
        self.af, self.as_, self.stop_pct = 2 / (fast + 1), 2 / (slow + 1), stop
        self.fast = self.slow = None

    def on_bar(self, b, in_pos):
        self.update_vwap(b)
        if self.fast is None:
            self.fast = self.slow = b.close
        was_above = self.fast > self.slow
        self.fast += self.af * (b.close - self.fast)
        self.slow += self.as_ * (b.close - self.slow)
        above = self.fast > self.slow
        if minutes(b.t) < 9 * 60 + 45:
            return None
        if in_pos:
            return "sell" if not above or b.close <= self.stop else None
        if above and not was_above and b.close > self.vwap:
            return "buy"

    def on_fill(self, price):
        super().on_fill(price)
        self.stop = price * (1 - self.stop_pct)


STRATEGIES = {s.name: s for s in [OpeningRange, VwapDip, Momentum]}


class Runner:
    """Houdt bij of we een positie hebben en dwingt de dagregels af."""

    def __init__(self, strategy):
        self.s, self.in_pos, self.day = strategy, False, None

    def on_bar(self, b):
        if b.t.date() != self.day:
            self.day = b.t.date()
            self.s.new_day()
        signal = self.s.on_bar(b, self.in_pos)
        m = minutes(b.t)
        if self.in_pos and m >= CLOSE_ALL_AT:
            return "sell"
        if signal == "buy" and not self.in_pos and m < NO_ENTRY_AFTER:
            return "buy"
        if signal == "sell" and self.in_pos:
            return "sell"
        return None
