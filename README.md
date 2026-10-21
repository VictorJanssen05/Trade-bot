# Trade-bot

Alpaca trading bot (paper trading / nepgeld) met meerdere strategieën en een backtest.

## Starten

1. Maak paper API keys aan op https://app.alpaca.markets (Paper Trading -> API Keys).
2. Kopieer `.env.example` naar `.env` en vul je keys in.
3. Installeer en draai:

```bash
python -m venv .venv
.venv\Scripts\activate        # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

## Strategie kiezen

1. Test eerst welke strategie het best werkt: `python backtest.py` (Nvidia) of `python backtest.py AAPL TSLA`.
2. Zet de beste bovenaan `bot.py` bij `STRATEGY`.

Strategieën staan in `strategies.py`: `buy_hold`, `sma_cross`, `trend_200`, `rsi2`, `breakout`.
