import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv(Path(__file__).with_name(".env"))
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
if not API_KEY or not SECRET_KEY:
    raise SystemExit(
        "Geen API keys gevonden. Maak een bestand '.env' (niet .env.example of .env.txt) "
        "in dezelfde map als bot.py met ALPACA_API_KEY=... en ALPACA_SECRET_KEY=..."
    )

_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)


def get_daily_bars(symbol: str, days: int):
    """Dagkoersen, gecorrigeerd voor splits en dividend."""
    now = datetime.now(timezone.utc)
    kwargs = dict(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=now - timedelta(days=days),
        adjustment=Adjustment.ALL,
    )
    try:
        # Volledige marktdata; gratis accounts mogen die tot 15 min geleden ophalen.
        req = StockBarsRequest(**kwargs, end=now - timedelta(minutes=16), feed="sip")
        bars = _client.get_stock_bars(req).df
    except APIError:
        bars = _client.get_stock_bars(StockBarsRequest(**kwargs, feed="iex")).df
    return bars.loc[symbol][["open", "high", "low", "close"]]


def get_price(symbol: str) -> float:
    """Laatste prijs (realtime via de gratis IEX-feed)."""
    req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed="iex")
    return float(_client.get_stock_latest_trade(req)[symbol].price)


def get_minute_bars(symbol: str, start, end):
    """Minuutkoersen tijdens normale beurstijd (09:30-16:00 New York)."""
    req = StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, start=start,
        end=min(end, datetime.now(timezone.utc) - timedelta(minutes=16)),
        adjustment=Adjustment.ALL, feed="sip",
    )
    bars = _client.get_stock_bars(req).df.loc[symbol][["open", "high", "low", "close", "volume"]]
    ny = bars.index.tz_convert("America/New_York")
    minutes = ny.hour * 60 + ny.minute
    return bars[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)]


def get_today_bars(symbol: str):
    """Minuutkoersen van vandaag tot nu (IEX-feed, realtime), tijd in New York."""
    now = datetime.now(timezone.utc)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute,
                           start=now - timedelta(hours=12), feed="iex")
    df = _client.get_stock_bars(req).df
    if df.empty:
        return df
    bars = df.loc[symbol][["open", "high", "low", "close", "volume"]]
    bars.index = bars.index.tz_convert("America/New_York")
    return bars[bars.index.date == bars.index[-1].date()]
