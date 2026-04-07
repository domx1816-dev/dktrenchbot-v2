# DKTrenchBot v2 — Architecture Map

_Last updated: 2026-04-07_

---

## Module Registry

| Module | Lane | Purpose | Status |
|--------|------|---------|--------|
| `bot.py` | Orchestrator | Main loop, cycle coordination | ✅ Active |
| `config.py` | Config | All constants and thresholds | ✅ Active |
| `state.py` | Data | Legacy state API (routes to data_layer internally) | ✅ Active |
| `data_layer.py` | Data | **NEW** Unified data access layer, single source of truth | ✅ New |
| `scanner.py` | Signal | AMM price/TVL scanner, candidate generation | ✅ Active |
| `scoring.py` | Signal | Composite token scoring (0-100) | ✅ Active |
| `chart_intelligence.py` | Signal | Chart state classification | ✅ Active |
| `breakout.py` | Signal | Breakout quality computation | ✅ Active |
| `regime.py` | Signal | Market regime detection (bull/bear/neutral/danger) | ✅ Active |
| `safety.py` | Risk | Per-token safety gate (TVL, issuer, concentration) | ✅ Active |
| `safety_controller.py` | Risk | **NEW** Emergency stop + pause system (file-based) | ✅ New |
| `sizing.py` | Risk | **NEW** Confidence-based position sizing | ✅ New |
| `execution.py` | Execution | AMM buy/sell via XRPL Payment transactions | ✅ Active |
| `route_engine.py` | Execution | Route evaluation, slippage check | ✅ Active |
| `dynamic_exit.py` | Execution | TP/stop/stale exit logic | ✅ Active |
| `dynamic_tp.py` | Execution | 3-layer dynamic take-profit system (Audit #4) | ✅ Active |
| `shadow_lane.py` | Shadow | **NEW** Paper-trading parallel lane, zero real impact | ✅ New |
| `improve_loop.py` | Intelligence | **NEW** Self-improvement analysis, generates tweaks | ✅ New |
| `learn.py` | Intelligence | Score/size adjustment from trade outcomes | ✅ Active |
| `improve.py` | Intelligence | Periodic improvement pass (called every 2h) | ✅ Active |
| `wallet_cluster.py` | Intelligence | Coordinated wallet entry detection (Audit #2) | ✅ Active |
| `new_wallet_discovery.py` | Intelligence | Smart wallet auto-discovery (Audit #1) | ✅ Active |
| `alpha_recycler.py` | Intelligence | Alpha recycling signal detection (Audit #3) | ✅ Active |
| `smart_money.py` | Intelligence | Smart money signal integration | ✅ Active |
| `smart_wallet_tracker.py` | Intelligence | Tracked wallet scan for token buys | ✅ Active |
| `wallet_intelligence.py` | Intelligence | On-chain holder analysis (Horizon-style) | ✅ Active |
| `ml_features.py` | ML | Feature extraction for ML pipeline | ✅ Active |
| `ml_model.py` | ML | ML model training and inference | ✅ Active |
| `ml_report.py` | ML | ML performance reporting | ✅ Active |
| `winner_dna.py` | Intelligence | Pattern matching against known winners (PHX/ROOS) | ✅ Active |
| `token_intel.py` | Intelligence | Token intel aggregation and formatting | ✅ Active |
| `discovery.py` | Discovery | Token registry management | ✅ Active |
| `xrpl_amm_discovery.py` | Discovery | XRPL-native AMM pool discovery | ✅ Active |
| `new_amm_watcher.py` | Discovery | New AMM launch detection | ✅ Active |
| `amm_launch_watcher.py` | Discovery | AMM launch scoring (DNA) | ✅ Active |
| `trustset_watcher.py` | Discovery | TrustSet velocity signal (PHX-type launches) | ✅ Active |
| `realtime_watcher.py` | Discovery | XRPL WebSocket stream — instant signals | ✅ Active |
| `sniper.py` | Discovery | New token sniper thread | ✅ Active |
| `hot_tokens.py` | Discovery | Hot token momentum detection | ✅ Active |
| `clob_tracker.py` | Discovery | CLOB orderbook tracking | ✅ Active |
| `reconcile.py` | Maintenance | Position reconciliation vs on-chain state | ✅ Active |
| `wallet_hygiene.py` | Maintenance | Trustline cleanup, dust removal | ✅ Active |
| `report.py` | Reporting | Daily trade report generation | ✅ Active |
| `backtest_14d.py` | Analysis | 14-day backtesting tool | ✅ Active |
| `tg_signal_listener.py` | Signal | Telegram signal ingestion | ✅ Active |
| `tg_scanner_listener.py` | Signal | Telegram scanner signal ingestion | ✅ Active |

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SIGNALS                              │
│  XRPL WebSocket Stream    Telegram Signals    Smart Wallets      │
│  (realtime_watcher)       (tg_signal_listener) (wallet_tracker) │
└────────────────┬───────────────┬──────────────────┬─────────────┘
                 │               │                  │
                 ▼               ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SIGNAL LAYER                                 │
│  scanner.py      breakout.py    chart_intelligence.py            │
│  scoring.py      regime.py      winner_dna.py                    │
└──────────────────────────┬──────────────────────────────────────┘
                            │ candidates[]
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SAFETY GATE                                    │
│  safety.py (per-token)   safety_controller.py (bot-level)       │
│  route_engine.py (slippage)   sizing.py (confidence)            │
└──────────────────────────┬──────────────────────────────────────┘
                            │ approved candidates
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  EXECUTION LANE                                  │
│  execution.py → XRPL AMM Payment                                 │
│  dynamic_exit.py + dynamic_tp.py → TP/stop management           │
└──────────────────────────┬──────────────────────────────────────┘
                            │ trade results
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                    │
│  data_layer.py  ←→  state/state.json (atomic writes)            │
│  state.py (legacy API shim)                                      │
└──────────────────────────┬──────────────────────────────────────┘
                            │ historical data
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  INTELLIGENCE LAYER                              │
│  learn.py        improve.py      improve_loop.py                 │
│  ml_features.py  ml_model.py     shadow_lane.py                  │
│  wallet_cluster.py  alpha_recycler.py  new_wallet_discovery.py   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Lane Separation

### Production Lane
Real trades only. All execution flows through `execution.py`. Position state in `state/state.json` via `data_layer.py`.

### Shadow Lane (`shadow_lane.py`)
- Paper trades only — NO real funds touched
- Separate state: `state/shadow_state.json`
- Runs every cycle (non-blocking, wrapped in try/except)
- Tests alternative parameters: `SCORE_THRESHOLD=45`, wider TPs
- CLI: `python3 shadow_lane.py --report`

### Intelligence Lane
Read-only analysis of past trades and on-chain data. Write only to:
- `state/improvement_log.json`
- `state/wallet_scores.json`
- `state/shadow_state.json`

---

## Emergency Controls Reference

| Command | Effect | File created |
|---------|--------|-------------|
| `python3 safety_controller.py status` | Show current state | — |
| `python3 safety_controller.py pause` | Pause new entries, keep exits running | `state/PAUSED` |
| `python3 safety_controller.py resume` | Re-enable new entries | (removes PAUSED) |
| `python3 safety_controller.py emergency-stop` | Halt ALL bot activity | `state/EMERGENCY_STOP` |
| `python3 safety_controller.py reset` | Clear all safety states | (removes both files) |

### Auto-Triggers (drawdown-based)

| Condition | Action |
|-----------|--------|
| Balance < 20 XRP | Emergency stop |
| 3+ consecutive losses > 5 XRP each | Pause |
| Single loss > 10 XRP | Pause + alert |

### Manual Override (from CLI or touch)
```bash
# Emergency stop from bash
touch /home/agent/workspace/trading-bot-v2/state/EMERGENCY_STOP

# Resume from pause
rm /home/agent/workspace/trading-bot-v2/state/PAUSED

# Check status
python3 safety_controller.py status
```

---

## State Files Reference

| File | Purpose | Writer | Reader |
|------|---------|--------|--------|
| `state/state.json` | Positions, trades, performance | data_layer.py / state.py | All modules |
| `state/shadow_state.json` | Shadow lane positions/trades | shadow_lane.py | shadow_lane.py |
| `state/improvement_log.json` | Improvement loop analysis | improve_loop.py | Operator |
| `state/wallet_scores.json` | Tracked wallet performance | data_layer.py | data_layer.py |
| `state/safety_alerts.json` | Safety event log | safety_controller.py | Operator |
| `state/PAUSED` | Pause flag | safety_controller.py | safety_controller.py / bot.py |
| `state/EMERGENCY_STOP` | Kill flag | safety_controller.py | safety_controller.py / bot.py |
| `state/status.json` | Cycle health | bot.py | Dashboard / monitoring |
| `state/execution_log.json` | Trade execution details | execution.py | reconcile.py |
| `state/realtime_signals.json` | Live signal stream | realtime_watcher.py | bot.py |
| `state/trustset_signals.json` | TrustSet velocity signals | trustset_watcher.py | bot.py |

---

## Cycle Flow (simplified)

```
run_cycle():
  1. safety_controller.check_cycle() → ok|paused|stopped
  2. Wallet balance fetch (once per cycle)
  3. New AMM / hot token / TrustSet scans (every Nth cycle)
  4. Shadow lane cycle check (every cycle, non-blocking)
  5. scanner.scan() → candidates
  6. Inject realtime signals (burst, CLOB, momentum)
  7. regime.update_and_get_regime()
  8. For each candidate:
     a. safety gate
     b. chart_intelligence + scoring
     c. sizing.calculate_position_size() (confidence-based)
     d. execution.buy_token()
  9. Exit management (all positions)
     a. dynamic_exit.check_exit()
     b. dynamic_tp.should_exit()
  10. improve_loop (every 50th cycle)
```
