"""Strategieën. Elke functie krijgt een DataFrame met dagkoersen
(kolommen open/high/low/close) en geeft per dag 1 (aandeel houden) of 0 (niks) terug.
Het signaal van dag X gebruikt alleen koersen t/m dag X.
"""
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def rsi(s: pd.Series, n: int) -> pd.Series:
    delta = s.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down)


def _hold(df, buy, sell):
    """Koop als `buy` waar is, houd vast tot `sell` waar is."""
    pos, out = 0, []
    for b, s in zip(buy, sell):
        if pos == 0 and b:
            pos = 1
        elif pos == 1 and s:
            pos = 0
        out.append(pos)
    return pd.Series(out, index=df.index)


def buy_hold(df):
    """Gewoon kopen en vasthouden. Dit is de lat om overheen te springen."""
    return pd.Series(1, index=df.index)


def sma_cross(df, fast=10, slow=30):
    """Korte gemiddelde boven lange -> houden."""
    return (sma(df.close, fast) > sma(df.close, slow)).astype(int)


def trend_200(df, n=200):
    """Alleen houden als de prijs boven het 200-daags gemiddelde ligt.
    Doel: grote crashes ontwijken."""
    return (df.close > sma(df.close, n)).astype(int)


def rsi2(df, entry=10, exit_sma=5, trend=200):
    """Koop dips in een stijgende trend (Connors RSI-2).
    Kopen: prijs boven SMA200 en RSI(2) onder `entry`.
    Verkopen: prijs sluit boven SMA5."""
    buy = ((df.close > sma(df.close, trend)) & (rsi(df.close, 2) < entry)).to_numpy()
    sell = (df.close > sma(df.close, exit_sma)).to_numpy()
    return _hold(df, buy, sell)


def breakout(df, entry=55, exit=20):
    """Trendvolger (Donchian): koop bij een 55-daags hoogste punt,
    verkoop bij een 20-daags laagste punt."""
    buy = (df.close > df.high.rolling(entry).max().shift(1)).to_numpy()
    sell = (df.close < df.low.rolling(exit).min().shift(1)).to_numpy()
    return _hold(df, buy, sell)


def trend_50(df):
    """Zoals trend_200 maar sneller: houden boven het 50-daags gemiddelde."""
    return trend_200(df, 50)


def golden_cross(df):
    """Houden zolang het 50-daags gemiddelde boven het 200-daags gemiddelde staat."""
    return sma_cross(df, 50, 200)


def ema_cross(df, fast=20, slow=50):
    """Zoals sma_cross, maar met gemiddelden die recente dagen zwaarder laten tellen."""
    return (df.close.ewm(span=fast).mean() > df.close.ewm(span=slow).mean()).astype(int)


def macd(df):
    """MACD: houden als de MACD-lijn boven zijn signaallijn staat."""
    line = df.close.ewm(span=12).mean() - df.close.ewm(span=26).mean()
    return (line > line.ewm(span=9).mean()).astype(int)


def momentum_12m(df):
    """Houden als het aandeel het afgelopen jaar gestegen is."""
    return (df.close > df.close.shift(252)).astype(int)


def bollinger(df, n=20, k=2.0):
    """Koop als de koers onder de onderste Bollinger-band zakt in een stijgende trend,
    verkoop als hij terug is bij het 20-daags gemiddelde."""
    mid = sma(df.close, n)
    lower = mid - k * df.close.rolling(n).std()
    buy = ((df.close < lower) & (df.close > sma(df.close, 200))).to_numpy()
    sell = (df.close > mid).to_numpy()
    return _hold(df, buy, sell)


def breakout_20(df):
    """Snellere breakout: koop bij een 20-dagen record, verkoop bij een 10-dagen dieptepunt."""
    return breakout(df, 20, 10)


def trend_rsi(df):
    """Combinatie: in het aandeel boven het 200-daags gemiddelde, maar pas instappen na een dip (RSI(2) < 20)."""
    up = (df.close > sma(df.close, 200)).to_numpy()
    buy = up & (rsi(df.close, 2) < 20).to_numpy()
    return _hold(df, buy, ~up)


STRATEGIES = {
    "buy_hold": buy_hold,
    "sma_cross": sma_cross,
    "trend_200": trend_200,
    "rsi2": rsi2,
    "breakout": breakout,
    "trend_50": trend_50,
    "golden_cross": golden_cross,
    "ema_cross": ema_cross,
    "macd": macd,
    "momentum_12m": momentum_12m,
    "bollinger": bollinger,
    "breakout_20": breakout_20,
    "trend_rsi": trend_rsi,
}
