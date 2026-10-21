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
