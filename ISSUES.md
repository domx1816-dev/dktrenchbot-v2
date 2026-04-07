# DKTrenchBot v2 — Issues & Technical Debt

_Audit date: 2026-04-07_
_Based on: 10 real trades, -7.45 XRP total PnL, 20% WR_

---

## 🔴 Critical (Fix Now)

### CRITICAL-1: 100% of trades entered at `chart_state=pre_breakout`
**Impact**: No chart state diversity whatsoever. Bot is essentially pattern-matching a single signal type.
**Root cause**: `PREFERRED_CHART_STATES = {"pre_breakout"}` + other states suppressed. Momentum confirmation gate added but confirmation threshold was +2% which is easy to fake with a single spike.
**Evidence**: All 10 trades: chart_state=pre_breakout. 20% WR.
**Fix**: Require 3 consecutive positive readings (+1.5%/reading) instead of 1 reading of +2%. OR expand preferred states to include burst/momentum/clob_launch signals which have different entry logic.

### CRITICAL-2: ML model called with `predict_probability()` but method may not exist
**Impact**: `sizing.py` integration calls `ml_model_mod.predict_probability()` — this method name must be verified against actual `ml_model.py` API. If method doesn't exist, sizing falls back silently but ML signal is lost.
**File**: `bot.py` lines added during upgrade, `ml_model.py`
**Fix**: Check `ml_model.py` for actual method names and align. Add graceful fallback.

### CRITICAL-3: `cluster_mod.get_cluster_signal()` called but may not exist
**Impact**: `bot.py` confidence sizing calls `cluster_mod.get_cluster_signal(key)` — this is speculative. If method doesn't exist, Python AttributeError would break the entry sizing block.
**Fix**: The call is inside `hasattr()` guard: `cluster_mod.get_cluster_signal(key) if hasattr(cluster_mod, "get_cluster_signal") else False` — this is safe but returns False always. Need to wire actual cluster signal.

---

## 🟡 High Priority

### HIGH-1: Scoring system inversely correlated at high values
**Impact**: Score 80-100 = 0% WR (per config comments). High-TVL, established pools score well but never move. The SCORE_TRADEABLE threshold at 42 still allows too many stale pool entries.
**Evidence**: config.py documents this explicitly: "Score 80-100: 0% WR (WORST)". Yet scoring still gives 30pts for TVL, which still rewards pools in a way that inflates scores for wrong reasons.
**Fix**: Review scoring.py TVL scoring — currently inverted (rewards micro TVL correctly) but chart_state scoring may still be inflating scores for large-pool signals.

### HIGH-2: Position sizing not differentiated before this upgrade
**Impact**: Scores ranged 54-77 but all entries got similar treatment. A score=77 should get 3x the position of score=54.
**Status**: Partially fixed by `sizing.py` — but only wired into `_trade_mode == "hold"` path. Scalp, micro, proven, and TVL-scalp paths still use fixed sizes.
**Fix**: Route all non-special entries through `calculate_position_size()`.

### HIGH-3: Stop cooldown is in-memory only (SKIP_REENTRY_SYMBOLS)
**Impact**: Bot restart loses all cooldown state. A token that hit hard stop 5 min ago will be re-enterable immediately after restart.
**File**: `bot.py` — `SKIP_REENTRY_SYMBOLS` is a module-level set; `stop_cooldown.json` is loaded but the in-memory set is the primary gate.
**Fix**: Write cooldowns to `state/stop_cooldown.json` persistently and read at startup. The file exists but `SKIP_REENTRY_SYMBOLS` set is what's actually checked.

### HIGH-4: Cleanup (trustline removal) runs on every full exit — may fail silently
**Impact**: ~200-line cleanup block in bot.py's exit section performs XRPL transactions (dust sell → burn → TrustSet remove) inside the main cycle. If any step fails, it logs DEBUG and continues, but the trustline stays. Over time this wastes XRP reserves.
**Fix**: Move cleanup to `wallet_hygiene.py`, run async/deferred. Log failures to a cleanup_queue.json for retry.

### HIGH-5: Re-entry loop (section 6b) has scoring variable leak
**Impact**: The re-entry loop at line ~350 of bot.py uses `total_score` from the outer candidates loop scope. `total_score` may be 0 or stale when the loop runs without any candidates being evaluated.
**File**: `bot.py` re-entry section uses `total_score` which is not re-computed inside the re-entry block.
**Fix**: Replace `total_score` reference in re-entry block with `pos.get("score", 50)`.

---

## 🟠 Medium Priority

### MED-1: Shadow lane scanner dependency
**Impact**: `shadow_lane.py`'s `run_cycle_check()` calls `scanner.get_token_price_and_tvl()` for exit evaluation. If scanner is unavailable or returns None, exit evaluations silently skip. This is acceptable but means shadow positions can become stale.
**Fix**: Add age-based auto-exit for shadow positions > 4h old (belt and suspenders).

### MED-2: `improve_loop.py` vs `improve.py` — duplicate functionality
**Impact**: Two improvement systems now exist: `improve.py` (called every 2h in bot.py main loop) and `improve_loop.py` (called every 50 cycles). Both analyze trades and generate suggestions. There is overlap.
**Fix**: Consolidate — `improve.py` handles score overrides written to state; `improve_loop.py` handles pattern analysis and logging. Make them complementary not redundant.

### MED-3: data_layer.py not yet wired to state.py
**Impact**: `state.py` and `data_layer.py` both exist as independent implementations. The task spec called for routing state.py through data_layer internally — this wiring was not completed to avoid breaking changes.
**Fix**: Add `_dl = get_data_layer()` to state.py and route load/save/record_trade/add_position/remove_position through it. Keep state.py API unchanged.

### MED-4: Wallet balance stored in bot_state as `_cycle_wallet_xrp`
**Impact**: The underscore-prefixed key gets serialized to state.json on every save. On reload it persists as a stale balance from the last cycle. Not harmful but noisy.
**Fix**: Don't store transient cycle data in persistent state dict. Use a separate cycle-local variable passed down as needed.

### MED-5: Relay bridge URL is hardcoded
**Impact**: `relay_bridge.set_url("https://together-lawyer-arrivals-bargains.trycloudflare.com")` — Cloudflare tunnel URLs change frequently. When it changes, relay silently fails.
**Fix**: Load from config or state, with graceful no-op if URL is unreachable.

---

## 🔵 Low / Backlog

### LOW-1: bot.py is 600+ lines — single file complexity
**Impact**: The main cycle is doing too much: signal injection, safety, scoring, sizing, execution, exit management, cleanup. Hard to test individual components.
**Fix**: Extract into: `entry_manager.py` (entry logic), `exit_manager.py` (exit logic), keep bot.py as thin orchestrator.

### LOW-2: No unit tests
**Impact**: Any config/threshold change can silently break scoring, sizing, or exit logic.
**Fix**: Add `tests/` directory with at least: test_scoring.py, test_sizing.py, test_safety_controller.py.

### LOW-3: Stablecoin/non-meme skip lists duplicated
**Impact**: `STABLECOIN_SKIP` defined in both `config.py` and `bot.py` (inline). If one is updated, the other lags.
**Fix**: Single canonical definition in config.py, import everywhere.

### LOW-4: `_paused_mode` variable initialized in run_cycle but not set if safety check is skipped
**Impact**: If safety_controller check raises an exception, `_paused_mode` would be undefined. Bot would crash on the entry gate.
**Status**: Mitigated — safety check runs before any exception-prone code and safety_controller is designed to be safe. But defensive init would be cleaner.
**Fix**: Initialize `_paused_mode = False` at top of run_cycle before the safety check.

### LOW-5: Improvement log grows unbounded over time
**Impact**: `state/improvement_log.json` kept to last 500 entries, but each entry contains full win/loss analysis (potentially large). On a busy bot, this could grow.
**Fix**: Add size check and trim to 100 entries. Already partially addressed (500 entry cap) but each entry can be 5-10KB.

---

## Summary

| Priority | Count | Blocking? |
|----------|-------|-----------|
| 🔴 Critical | 3 | Potential runtime errors |
| 🟡 High | 5 | Performance/correctness issues |
| 🟠 Medium | 5 | Technical debt |
| 🔵 Low/Backlog | 5 | Quality improvements |

**Immediate actions needed:**
1. Verify `ml_model.py` API surface (CRITICAL-2)
2. Fix `_paused_mode` init before safety check (LOW-4 → should be CRITICAL)
3. Fix re-entry `total_score` variable leak (HIGH-5)
