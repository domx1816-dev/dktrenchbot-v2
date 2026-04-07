# DKTrenchBot v2 — XRPL Meme Token Trading Bot

Production-grade automated trading bot for XRPL meme tokens using AMM pools and DEX order books.

## Quick Start

```bash
cd /home/agent/workspace/trading-bot-v2
python3 bot.py
```

## Stop

```bash
# Ctrl+C in terminal, or:
kill $(cat state/status.json | python3 -c "import sys,json; print(json.load(sys.stdin)['pid'])")
```

## Configuration

Edit `config.py` to tune:
- `POLL_INTERVAL_SEC` — scan frequency (default: 60s)
- `XRP_PER_TRADE_BASE` — base position size (default: 5 XRP)
- `SCORE_TRADEABLE` — minimum score to enter (default: 70)
- `MAX_POSITIONS` — max concurrent positions (default: 5)
- `MIN_TVL_XRP` — minimum pool TVL (default: 3000 XRP)
- `HARD_STOP_PCT` — hard stop loss (default: 5%)
- `TRAIL_STOP_PCT` — trailing stop (default: 10%)
- `TP1_PCT / TP2_PCT / TP3_PCT` — take profit levels (6%, 12%, 25%)
- `STALE_EXIT_HOURS` — exit if no move after N hours (default: 2)
- `MAX_HOLD_HOURS` — maximum hold time (default: 4)

## State Files

All in `state/` directory:

| File | Contents |
|------|----------|
| `bot.log` | Main loop log |
| `status.json` | Current cycle status, PID, open positions |
| `state.json` | Positions, trade history, performance |
| `scan_results.json` | Latest scanner output |
| `safety_cache.json` | Safety check cache |
| `regime.json` | Current market regime |
| `route_log.json` | Route evaluation log |
| `execution_log.json` | Trade execution log |
| `breakout_data.json` | Price history for breakout detection |
| `smart_money.json` | Smart wallet tracking |
| `improvements.json` | Self-improvement adjustments |
| `daily_report.txt` | Latest daily report |
| `reconcile.log` | Reconciliation log |
| `hygiene.log` | Wallet hygiene log |
| `sniper.log` | Sniper activity log |

## Architecture

```
bot.py          — Main loop orchestrator
config.py       — All tunable parameters
scanner.py      — Token discovery + momentum bucketing
safety.py       — Hard safety filter (TVL, LP burn, freeze, etc.)
breakout.py     — Price breakout quality detection
chart_intelligence.py — Market structure classification
scoring.py      — Composite 0-100 score
regime.py       — Market regime detection (hot/neutral/cold/danger)
route_engine.py — AMM vs DEX slippage + exit feasibility
execution.py    — WebSocket TX submit with retry + fill parsing
dynamic_exit.py — All exit logic (TP, stops, dynamic signals)
smart_money.py  — Smart wallet tracking + score boost
state.py        — Persistent state management
reconcile.py    — Chain sync on startup + every 30min
wallet_hygiene.py — Dust liquidation + trustline cleanup
improve.py      — Self-optimization every 6 hours
report.py       — Daily performance report
sniper.py       — New AMM pool + trustline surge detection
```

## Token Registry

27 verified XRPL meme tokens pre-loaded. Add custom tokens to `TOKEN_REGISTRY` in `config.py`:

```python
{"symbol": "MYTOKEN", "issuer": "rIssuerAddress..."},
```

For tokens > 3 characters, currency code is auto-converted to hex.

## Switching from Old Bot

1. Stop the old bot: `kill <old_pid>`
2. Check old bot state: `cat /home/agent/workspace/trading-signals/state/`
3. Ensure no open positions in old bot before switching
4. Start new bot: `cd /home/agent/workspace/trading-bot-v2 && python3 bot.py`

Both bots use the same wallet. **Never run both simultaneously.**

## Wallet

- Bot address: `rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF`
- Seed: stored in `/home/agent/workspace/memory/secrets.md` (never logged)
- Operator wallet: `rUWWnjZyBsmGPPLirtCf3NbUXJ1amet86e`

## Known Limitations

1. **No OHLCV data** — XRPL doesn't provide candles natively; breakout/chart detection uses price readings over time (1 reading per poll cycle)
2. **AMM-only execution** — Uses OfferCreate for trades; direct AMMSwap not used (OfferCreate routes through AMM automatically)
3. **Price history builds slowly** — Need ~20 poll cycles (20 min) before breakout quality is reliable
4. **Smart money tracking** — Seeded empty; builds over time as winning trades are recorded
5. **LP burn check** — Complex to determine accurately; defaults to UNKNOWN (warn but allow) when supply cannot be determined
6. **Concentration check** — Only checks issuer's account_lines, not full holder distribution
7. **Sniper** — Heuristic-based scoring; newly created tokens are high risk

## Security

- Seed never logged or printed
- All transactions via private XRPL endpoint
- WebSocket with retry on failures
