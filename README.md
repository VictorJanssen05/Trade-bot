# Trade-bot

Simpele Alpaca trading bot (paper trading / nepgeld) met een SMA crossover strategie.

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
