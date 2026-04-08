# DKTrenchBot v2 — Master Log

*A living document. Updated after every session. Journal of successes, failures, pivots, and learnings.*

---

## Project: DKTrenchBot v2 — XRPL Memecoin Trading Bot
**Status:** Live (as of Apr 8 2026)
**Wallet:** rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF | Balance: ~197 XRP
**Dashboard:** https://dktrenchbot.pages.dev

---

## 📋 Architecture Overview

### Pipeline
```
scanner → pre_move_detector → classify → memecoin_filter → disagreement_engine → strategy_routing → sizing → execution → dynamic_exit → learn
```

### Components
| File | Purpose |
|---|---|
| `bot.py` | Main loop (1s cycle) |
| `pre_move_detector.py` | Early entry detection ($400-$5k TVL window) |
| `classifier.py` | Route to strategy: BURST / CLOB_LAUNCH / PRE_BREAKOUT / TREND / MICRO_SCALP |
| `disagreement.py` | 6-check veto engine (rug, fake burst, LP trap, smart money, blacklist, regime) |
| `dynamic_tp.py` | Per-strategy TP ladders + trail stops + stale limits |
| `sizing.py` | TVL-based slippage-safe position sizing |
| `trustset_watcher.py` | PHX-type launch detection (8+ TS/hr) |
| `shadow_ml.py` | Paper trade + real outcome tracking, strategy WR feedback |
| `wallet_intelligence.py` | Smart money tracking, whale cluster alerts |
| `route_engine.py` | AMM vs CLOB execution routing |
| `scanner.py` | Hot token detection, momentum, sustained signals |
| `chart_intelligence.py` | Price/TVL pattern classification |

---

## 🔑 Core Configuration

| Parameter | Value |
|---|---|
| MAX_POSITIONS | 999 (no limit — full release mode) |
| Entry size (pre-move) | 5 XRP |
| Slippage buffer | 10% |
| Min TVL | 200 XRP |
| Poll interval | 1 second |
| Token discovery | ~10 min (xrpl.to + xpmarket APIs) |
| Pre-move TVL window | $400-$5k AMM (~$800-$10k est MC) |
| TrustSet burst threshold | 8/hr (to catch DKLEDGER-type at $400 MC) |
| Max position per token | No hard cap |

---

## 📊 Strategy Exits (dynamic_tp.py)

| Strategy | Trail | Hard Stop | Stale Limit | TP Ladder |
|---|---|---|---|---|
| BURST | 20% | 10% | 1 hr | 2x→50%, 3x→30%, 6x→100% |
| CLOB_LAUNCH | 15% | 8% | 30 min | 1.4x→40%, 2x→30%, 3x→100% |
| PRE_BREAKOUT | 25% | 12% | 3 hr | 1.3x→20%, 2x→20%, 5x→30%, 10x→100% |
| TREND | 18% | 8% | 2 hr | 1.2x→20%, 1.5x→20%, 2x→30%, 4x→100% |
| MICRO_SCALP | 8% | 6% | 45 min | 1.1x→60%, 1.2x→100% |

---

## 🚫 Disagreement Engine Veto Checks (disagreement.py)

Any veto = hard skip, no overrides:
1. **Rug fingerprint:** issuer seq<5 = veto | burned keys = +bonus
2. **Fake burst:** <3 unique wallets in TrustSets = wash veto
3. **Liquidity trap:** 95%+ LP in one wallet = drain veto
4. **Smart money:** 3+ tracked wallets selling = veto
5. **Hard blacklist:** rug registry + 3+ hard stops on token = veto
6. **Regime:** DANGER mode requires 50+ TS/hr or score≥75

---

## 📈 Backtest Results

**Upgraded Sim (14-day, 595 tokens):**
- Trades: 9,944 | Win Rate: 61.4% | Profit Factor: 6.82x
- Best TVL band: micro 500-2k XRP (62% WR, avg +33.81 XRP)
- Burst 50+ TS/hr: 72% WR | 25-50 TS/hr: 64% | 8-25 TS/hr (DKLEDGER-type): 60%
- Real trades (Apr 6-8): 24 trades | WR=16.7% | PnL=-19.77 XRP | 75% stale exits

**Key insight:** The old bot (Apr 6-8) was fundamentally different architecture. Master build has 6.82x profit factor in sim.

---

## 🧠 Memecoin Filter (bot.py)

**Blocks:** stablecoins, L1s (HBAR/ETH/SOL/etc), wrapped assets, DeFi, utility tokens, commodities, RWA
**Blocks suffixes:** IOU, LP, POOL, VAULT
**Allows:** Anonymous XRPL issuers with large supply = meme fingerprint

---

## 🔧 Key Decisions Log

### Apr 8, 2026 — Initial Master Build Deployment

**Problem:** Old bot missed brizzly, PRSV, Serpent, PHASER — tokens that had 3-100x moves.

**Root causes identified:**
1. TVL stale-zone threshold too blunt (>10K = skipped even when whale was accumulating)
2. Fee=100% filter excluded active tokens (brizzly, PRSV, Serpent had 100% fee AMMs but were live)
3. No pre-accumulation detection — bot entered mid-move, not before
4. Position sizing too aggressive on mid-cap tokens (PHASER: $23 entry vs 5 XRP correct)
5. Execution log showed `tecUNFUNDED_OFFER` failures on Serpent/ROOSEVELT — offer-based sells failing on thin books

**Decisions made:**
- Remove MAX_POSITIONS cap (set to 999)
- Remove 100% fee filter — evaluate all AMMs regardless
- Build `pre_move_detector.py` — dedicated pre-accumulation scanner
- Add TVL doubling detection (50%+ surge = whale accumulating)
- Override entry size to 5 XRP for pre-move signals
- Bot log truncated (51M lines → 10k)
- Stats reset to clean slate

**Removed:**
- Axiom bot entirely (`rm -rf axiom-bot/`)
- Warden cron job (broken, 21 consecutive errors)
- Axiom daily report cron (timing out)

---

## 📊 Operator Token Performance (Execution Log — Apr 6-8)

| Token | Entry | Exit | Real PnL | Issue |
|---|---|---|---|---|
| PHX | 9 buys @ ~$0.26 | 22 sells | **+$7.67 XRP** | ✅ Only winner |
| Serpent | 5 buys @ ~$0.04 | 6 sells (20 failed) | **-$3.40 XRP** | ❌ Offer sell failures |
| brizzly | 1 buy @$0.023 | 1 sell @$0.020 | **-$1.35 XRP** | ❌ Entry after move, too late |
| ROOSEVELT | 4 buys @$3.7e-6 | 8 sells (many failed) | **-$0.08 XRP** | ⚠️ Sell failures |
| PRSV | 1 buy @$5.3e-6 | Open (no sell yet) | **-$3.66 XRP** | 🟡 Still open, ~3.5x from entry |
| PHASER | 1 buy @$23.92 | Partial @ $7.77 | **-$16.15 XRP** | ❌ Size too big ($23 vs $5 correct) |

**Total realized PnL on operator's tokens: ~-$16.97 XRP**

---

## 🚀 Pre-Move Detector — Signal Framework

### Signals
| Signal | Trigger | Action |
|---|---|---|
| PRE_ACCUMULATION | TVL $400-$5k + LP>100k + TS<15/hr | Enter 5 XRP |
| WHALE_BUILDING | TVL +50%+ in one cycle, price stable | Enter 5 XRP |
| CONFIRMED_MOVE | TS burst ≥15/hr + TVL in window | Scale up |
| SCALING | Post-launch TVL + TS activity | Add to position |

### Fast-Path (every 30s)
- Reads from `trustset_signals.json` + `realtime_signals.json`
- Directly checks AMM state for TrustSet-active issuers
- Bypasses 10-min registry discovery lag
- Lights up when new tokens launch with burst activity

---

## 🔄 Pivot Log

| Date | Pivot | Reason | Outcome |
|---|---|---|---|
| Apr 8 | Removed Axiom bot | Operator: "strictly DKTrenchBot v2 only" | Freed ~55MB, no competing processes |
| Apr 8 | Removed all cron jobs | Both failing (timeout + error loops) | Zero scheduled AI costs |
| Apr 8 | Added pre_move_detector | Missing pre-explosion entry window | 256 candidates now flagged |
| Apr 8 | Removed MAX_POSITIONS cap | "Let master build run unconstrained" | Full release mode |
| Apr 8 | Reset stats to clean slate | New build = new baseline | Trade history cleared |
| Apr 8 | Removed fee=100% filter | Brizzly/PRSV/SERPENT all had 100% fee = active | All now evaluable |

---

## ✅ What's Working (Apr 8)

- Bot running, watchdog active, auto-restart enabled
- 422 tokens scanned every cycle
- 256 pre-accumulation candidates active
- All operator tokens flagged in pre-move window
- No position cap, clean stats, full release mode
- Bot log manageable (10k lines)

---

## ⚠️ Known Issues / Open Items

1. **Execution log:** 20+ `tecUNFUNDED_OFFER` failures on Serpent/ROOSEVELT — offer-based AMM sells failing on thin orderbooks. Consider switching to `amm_payment` route for sells (not `offer_ioc`) for better fill rate on low-liquidity tokens.
2. **PHASER size:** $23.92 entry was wrong. Correct pre-move sizing = 5 XRP max.
3. **brizzly entry:** Bot entered @$0.023 after the move already happened. Need faster scanner or lower TVL threshold for fresh issuers.
4. **PRSV:** Still open, no TP exit triggered. ~3.5x from entry but no exit yet.
5. **Fast-path quiet:** Currently 0 fast-path hits — trustset_signals.json is stale/empty. Monitor — fast-path should light up on new launches.

---

## 📁 File Index

| File | Status |
|---|---|
| `DKTrenchBot_v2_FULL_SOURCE.tar.gz` | Created Apr 8 — operator has it |
| Catbox link | https://litter.catbox.moe/1f9wcz.gz (72hr) |
| `MASTER_LOG.md` | This file — living journal |
| `state/active_registry.json` | 606 tokens, updated ~10 min |
| `state/pre_move_state.json` | Pre-move signals, capped |
| `state/pre_move_signals.json` | Injected into bot each cycle |
| `state/execution_log.json` | 309 entries — trade history |

---

*Last updated: 2026-04-08 20:00 UTC*