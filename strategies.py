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
    r = rsi(df.close, 2)
    up = df.close > sma(df.close, trend)
    exit_line = sma(df.close, exit_sma)
    pos, out = 0, []
    for i in range(len(df)):
        if pos == 0 and up.iloc[i] and r.iloc[i] < entry:
            pos = 1
        elif pos == 1 and df.close.iloc[i] > exit_line.iloc[i]:
            pos = 0
        out.append(pos)
    return pd.Series(out, index=df.index)


def breakout(df, entry=55, exit=20):
    """Trendvolger (Donchian): koop bij een 55-daags hoogste punt,
    verkoop bij een 20-daags laagste punt."""
    hi = df.high.rolling(entry).max().shift(1)
    lo = df.low.rolling(exit).min().shift(1)
    pos, out = 0, []
    for i in range(len(df)):
        if pos == 0 and df.close.iloc[i] > hi.iloc[i]:
            pos = 1
        elif pos == 1 and df.close.iloc[i] < lo.iloc[i]:
            pos = 0
        out.append(pos)
    return pd.Series(out, index=df.index)


STRATEGIES = {
    "buy_hold": buy_hold,
    "sma_cross": sma_cross,
    "trend_200": trend_200,
    "rsi2": rsi2,
    "breakout": breakout,
}
