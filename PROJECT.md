# DKTrenchBot — Living Project Doc
*Last updated: 2026-04-06 22:56 UTC*

## What This Is
XRPL AMM memecoin trading bot. Auto-discovers new token launches, scores them, enters positions, and exits via a 4-tier TP system + trailing stop. Goal: 500 XRP/week.

## Bot Wallet
`rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF`
Seed → `memory/secrets.md`

## Infrastructure
- **Start**: `cd /home/agent/workspace/trading-bot-v2 && nohup python3 -u bot.py >> state/bot.log 2>&1 &`
- **Kill**: `pkill -f "python3.*bot.py"`
- **Log**: `state/bot.log`
- **State**: `state/state.json`
- **CLIO RPC**: `https://rpc.xrplclaw.com`
- **Dashboard**: https://dktrenchbot.pages.dev

---

## Current Config (Data-Driven, 2026-04-06)

| Setting | Value | Why |
|---------|-------|-----|
| Entry threshold | 42 | Score 0-59 = 47-50% WR; 60-100 = 0-22% WR |
| Elite threshold | 50 | Gets bigger sizing |
| TVL sweet spot | 500-2K XRP | Fresh launches = runners; high TVL = stale |
| Stale timer | 1.5hr | Was 3hr; 40% of trades were stales |
| Trading hours | 08:00-01:00 UTC | 02-07 UTC = 6-17% WR (dead) |
| Max positions | 4 | Focused capital |
| Hold sizing | ~13-15 XRP (scales with capital) | Capital-aware: 10-15% of wallet |
| Scalp sizing | 4 XRP | TVL <1K or score 35-41 |
| Hard stop | -15% | -10% in first 30min |
| Trailing stop | -20% from peak | |
| TP1 | +20% → sell 30% | |
| TP2 | +50% → sell 30% | |
| TP3 | +300% → sell 30% | |
| TP4 | +600% → sell all | |

---

## Architecture

```
bot.py (main loop, ~60s cycles)
├── scanner.py        — discovers tokens from XRPL AMM pools
├── realtime_watcher.py — WebSocket stream, catches AMMCreate instantly
├── safety.py         — concentration, issuer, blackhole checks
├── scoring.py        — 0-100 score (TVL, chart, BQ, smart money)
├── chart_intelligence.py — pre_breakout / continuation / orphan
├── breakout.py       — breakout quality (BQ) metric
├── dynamic_exit.py   — TP1/2/3/4, trailing stop, stale, scalp exits
├── execution.py      — XRPL transaction signing + submission
├── regime.py         — hot/neutral/cold/danger (last 15 trades)
├── learn.py          — self-learning weights from trade history
├── route_engine.py   — slippage estimation
├── smart_money.py    — whale wallet detection
├── wallet_hygiene.py — auto-close zero-balance trustlines
└── reconcile.py      — sync state.json with on-chain reality
```

---

## What's Working ✅
- Pre_breakout chart state gate (only tradeable state by data)
- 4-tier TP system — catches TP3+ runners (M1N +1275%, ROOSEVELT, BRETT)
- Realtime WebSocket launch detection
- Non-meme token filter (no XDC, SGB, SOLO, etc.)
- Proven token reload (PHX-style: 2+ TP wins = priority rebuy, no cooldown)
- Hold vs scalp auto-classifier (TVL-based)
- Capital-aware position sizing (scales linearly with wallet)
- Partial exit dedup (90s guard prevents double-firing TP levels)
- 4hr cooldown per symbol (prevents 30x duplicate entries)
- Regime based on last 15 trades only (not poisoned by old data)

## Known Issues / Watch List 🔍
- CHICKEN (-9.3%) and TABS (flat) are legacy positions from old config — exit when stale timer hits
- brizzly, PRSV, CHEST, LAWAS still held as dust — hygiene cleaning them up
- Cycle time ~130s — could be faster if discovery is optimized

---

## Performance Data (Actual Trades)

| Date | WR | Notes |
|------|----|-------|
| Apr 3 | 43% | Early bot, learning |
| Apr 4 | 53% | M1N +1275% |
| Apr 5 | 20% | Bad day — orphans, dead market |
| Apr 6 | 44% | Rebuilt config mid-day |
| **Simulated (new config)** | **53%** | **+36.7 XRP est. over 4 days** |

**Backtest finding**: Score band 80-100 = 0% WR (all stales). Score 0-49 = 47% WR (best). High TVL = dead money.

---

## Roadmap — What's Next

### High Priority
- [ ] **More data accumulation** — need 50+ trades under new config to retrain learn.py properly
- [ ] **Runner detection improvement** — M1N/BRETT/JEET all had TVL growth spike before the move; detect this earlier
- [ ] **Proven token list** — expand beyond PHX/ROOS; any token with 2+ TP wins gets priority

### Medium Priority
- [ ] **Time-of-day sizing** — bigger entries 13:00-20:00 UTC (highest WR window), smaller outside
- [ ] **TP3/TP4 trail optimization** — after TP2, tighten trailing stop to -15% (lock in gains)
- [ ] **Auto-report** — daily Telegram/dashboard summary with PnL, positions, regime

### Low Priority / Ideas
- [ ] **Cross-token correlation** — if PHX is pumping, scan for related tokens launching
- [ ] **Volume spike detector** — sudden AMM volume = someone buying big = entry signal
- [ ] **Exit price improvement** — current sells use market order; limit orders could reduce slippage

---

## Capital Math

| Capital | Est. Weekly | Path to 500 XRP/week |
|---------|-------------|----------------------|
| 90 XRP | ~52 XRP | Baseline |
| 190 XRP | ~130 XRP | After +100 XRP deposit |
| 300 XRP | ~250 XRP | Compound from profits |
| 500 XRP | ~500 XRP | Target achieved |

Key insight: every XRP compounded back in scales linearly. Don't withdraw early.

---

## Rules (Never Break These)
1. **No orphan trades** — 14% WR, rugpull magnet. Disabled permanently.
2. **No continuation trades** — 17% WR. Disabled permanently.
3. **No non-meme tokens** — XDC, SGB, SOLO, CORE, CSC, ETH etc. No explosive upside.
4. **No auto-bridge EVM funds** — burned ~50 XRP on 2026-04-04. Manual only.
5. **No entries 02:00-07:00 UTC** — 6-17% WR. Dead hours.
6. **Kill all bot.py instances before restart** — `pkill -f "python3.*bot.py"`
7. **Never overwrite MEMORY.md** — append to `memory/2026-MM-DD.md`
