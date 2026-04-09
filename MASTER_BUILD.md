# DKTrenchBot v2 — Master Build

**Last Updated:** April 9, 2026  
**Status:** LIVE  
**Wallet:** rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF  
**Balance:** ~199.66 XRP  
**Dashboard:** https://dktrenchbot.pages.dev

---

## Architecture Overview

```
scan → pre_move_detector → classify → memecoin filter → disagree → strategy → size → execute → manage → learn
```

### Core Modules
| Module | Role |
|--------|------|
| `bot.py` | Main loop, orchestration |
| `scanner.py` | Price + TVL fetching, token discovery |
| `trustset_watcher.py` | Real-time TrustSet burst detection |
| `classifier.py` | Strategy classification (burst/clob/pre_breakout/trend/micro_scalp) |
| `disagreement.py` | 6-check veto engine |
| `scoring.py` | Token score 0-100 |
| `execution.py` | Buy/sell via OfferCreate IOC |
| `execution_core.py` | Retry, ghost-fill detection, orphan tracking |
| `dynamic_tp.py` | Per-strategy TP ladders + trailing stops |
| `dynamic_exit.py` | Exit management, stale exits, hard stops |
| `sizing.py` | Position sizing, TVL-safe caps |
| `pre_move_detector.py` | Pre-accumulation scanner ($400-$5k TVL window) |
| `regime.py` | Market regime classification |
| `safety.py` | Safety gate per candidate |
| `smart_money.py` | Tracked wallet monitoring |
| `wallet_cluster.py` | Cluster buy/sell detection |
| `alpha_recycler.py` | Smart wallet exit monitoring |
| `brain.py` | ML predictions, slippage forecasting |

---

## Pipeline Detail

### Pre-Move Detector (pre_move_detector.py)
- Scans AMM TVL $400-$5k window every cycle
- Injects pre_accumulation entries at 5 XRP
- Signals: PRE_ACCUMULATION → WHALE_BUILDING → CONFIRMED_MOVE → SCALING
- TVL doubling (50%+) = whale accumulating
- State file: state/pre_move_state.json (capped 100 signals / 50 entries)

### Classifier (classifier.py)
- BURST: burst_count≥8 TS/hr OR velocity>2.5 OR _burst_mode → FAST PATH
- CLOB_LAUNCH: age<180s + orderbook signal → FAST PATH
- PRE_BREAKOUT: chart_state=pre_breakout any TVL, or TVL>50k + low velocity
- TREND: TVL>200k + rising velocity
- MICRO_SCALP: TVL<2k + velocity>1.5

### Disagreement Engine (disagreement.py)
6 checks — ANY veto = hard skip:
1. Rug fingerprint: issuer seq<5 = veto
2. Fake burst: <3 unique wallets in TrustSets = wash veto
3. Liquidity trap: 95%+ LP one wallet = drain veto
4. Smart money veto: 3+ tracked wallets selling = veto
5. Hard blacklist: rug registry + 3+ hard stops on token = veto
6. Regime veto: DANGER requires 50+ TS/hr or score≥75

### Memecoin Filter (bot.py)
Strictly memecoins only. Blocks:
- Stablecoins / fiat-pegged (USD, USDT, RLUSD, EUR, etc.)
- Real L1/L2 tokens (ETH, BTC, SOL, AVAX, etc.)
- XRPL ecosystem utility (EVR, SOLO, CSC, etc.)
- Wrapped / bridged assets (WXRP, WFLR, etc.)
- Payment / fintech infrastructure (XRPAYNET, PAYNET, etc.)
- Substring filter: PAYNET, BRIDGE, PROTOCOL, FINANCE, NETWORK, EXCHANGE, CUSTODY, WALLET
- Suffix filter: IOU, LP, POOL, VAULT

### Execution (execution.py) — CRITICAL FIX Apr 9
**IOC dust-minimum pattern:**
- BUY: taker_pays = "1" (dust) — fills at any available price
- SELL: taker_pays = "1" drop — fills at any available price
- NO min_tokens or min_xrp floor — eliminates tecKILLED entirely
- Post-trade slippage gate: >15% = immediate recovery sell

### Per-Strategy Exits (dynamic_tp.py)
| Strategy | Trail | Hard | Stale | TP Ladder |
|----------|-------|------|-------|-----------|
| burst | 20% | 10% | 1 hr | 2x→50%, 3x→30%, 6x→100% |
| clob_launch | 15% | 8% | 30 min | 1.4x→40%, 2x→30%, 3x→100% |
| pre_breakout | 25% | 12% | 3 hr | 1.3x→20%, 2x→20%, 5x→30%, 10x→100% |
| trend | 18% | 8% | 2 hr | 1.2x→20%, 1.5x→20%, 2x→30%, 4x→100% |
| micro_scalp | 8% | 6% | 45 min | 1.1x→60%, 1.2x→100% |

### Burst Sizing (sizing.py — slippage-safe)
- TVL <200 XRP → 7 XRP hard cap
- TVL 200-500 XRP → 7-15 XRP linear scale
- TVL ≥500 XRP → full sizing (1.0x flat)
- Burst multiplier: 8+ TS/hr→+20% | 25+→+35% | 50+→+50%

### TrustSet Watcher
- MIN_TRUSTSETS_1H=8 | MIN_TRUSTSETS_ABS=15
- Scans EVERY cycle — catches $400 MC launches

---

## Backtest Results
- Sim 14-day (595 tokens): 9,944 trades | WR=61.4% | profit factor=6.82x
- Best TVL band: micro 500-2k XRP (62% WR, avg +33.81 XRP)
- Burst 50+ TS/hr: 72% WR | 25-50: 64% | 8-25 (DKLEDGER-type): 60%

---

## Live Config Summary

```
Bot wallet:         rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF
Bot path:           /home/agent/workspace/trading-bot-v2/bot.py
Cycle:              1 second
Max positions:      UNLIMITED (removed Apr 8 — full release mode)
Min position:       5.0 XRP
Buy method:         IOC OfferCreate, dust min (taker_pays="1")
Sell method:        IOC OfferCreate, dust min (taker_pays="1" drop)
Post-trade slippage gate: 15% (immediate recovery sell if exceeded)
Dashboard:          https://dktrenchbot.pages.dev
GitHub:             https://github.com/domx1816-dev/dktrenchbot-v2
```

---

## Security
- ALL Telegram code purged Apr 8 — hot wallet air-gapped from external comms
- SetRegularKey: bot wallet rKQACag8... controlled by main wallet
- No external key management — keys generated and stored locally only

---

## Scaling Notes
- At 500 XRP: revisit position sizing floors
- At 1,000+ XRP: revisit MAX_POSITION_XRP ceiling
- At 2,000+ XRP: needs tiered sizing by pool depth

---

## Change Log Summary
| Date | Change |
|------|--------|
| Apr 9, 2026 | **CRITICAL:** tecKILLED fix — IOC dust minimum pattern |
| Apr 9, 2026 | Meme filter: block XRPayNet + utility/payment keywords |
| Apr 9, 2026 | Slippage gate: 2.5% → 15% (post-trade, not pre-trade) |
| Apr 8, 2026 | MAX_POSITIONS removed — full release mode |
| Apr 8, 2026 | Telegram code purged — air-gap security |
| Apr 8, 2026 | Pre-move detector added ($400-$5k TVL window) |
| Apr 7, 2026 | Dynamic TP ladders per strategy |
| Apr 7, 2026 | Burst sizing with slippage-safe TVL caps |
| Apr 6, 2026 | Disagreement engine (6-check veto) |
| Apr 5, 2026 | Execution hardener, orphan tracking |
| Apr 4, 2026 | v2 initial build |

---

*DKTrenchBot v2 — Built on XRPLClaw.com*
