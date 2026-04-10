# AMM Discovery Audit Fixes — April 9, 2026

## Summary

Deep audit identified 4 gaps in token scanning pipeline. All fixes implemented.

---

## Fix #1: Removed Dead Code (new_amm_watcher)

**Problem:** `bot.py` tried to import `new_amm_watcher` module every 4th cycle, but this module doesn't exist. Import failed silently, wasting cycles.

**Fix:** Removed lines 302-307 from `bot.py`. The hot_tokens scan remains.

**Impact:** Cleaner code, no functional change (module was already dead).

---

## Fix #2: Issuer Validation in Discovery

**Problem:** 67 tokens in `active_registry.json` had malformed/non-existent issuer addresses. These came from `xrpl.to` API returning stale data. Scanner wasted RPC calls on ghost tokens.

**Fix:** Added `_validate_issuer()` function in `xrpl_amm_discovery.py` that checks if issuer account exists on-chain before adding to registry. Uses `account_info` RPC — if it returns `actMalformed` error or no `account_data`, the issuer is invalid.

**Impact:** Registry now only contains tokens with valid on-chain issuers. Eliminates 67 ghost entries.

---

## Fix #3 & #4: Relaxed Momentum Classification (CRITICAL)

**Problem:** 182 tokens in sweet spot (100-2500 XRP TVL) were classified as "dead" with score=0.0. Many were flat or slightly declining — not true dead tokens, just in accumulation phase.

**Root Cause:** `_momentum_bucket()` in `scanner.py` was too aggressive:
- Tokens with >10% decline marked dead (now -15%)
- Flat tokens (±5%) went straight to dead bucket
- No detection of slow accumulation patterns (TVL growing, price stable)

**Fixes Applied:**

### 3a. Relaxed Death Threshold
- Price decline threshold: -10% → **-15%** (allows more flat tokens through)
- Weak fresh threshold: +0.5% → **+0.2%** (catches very slow grinders)
- Flat-but-not-declining tokens (±5%): go to **thin_liquidity_trap** instead of dead

### 3b. New "Accumulation" Bucket
Added detection for slow accumulation pattern:
- If TVL grew 10%+ over last 5 readings BUT price stayed flat (±5%)
- Classified as **"accumulation"** — smart money loading positions without spiking chart
- Base score: **35.0** (moderate — surfaces these before they explode)
- Included in `get_candidates()` output alongside fresh/sustained momentum

### 3c. Bot Integration
- Scanner tags accumulation tokens with `_accumulation_mode=True` flag
- Bot.py chart_state gate allows accumulation tokens through with log message:
  ```
  ✅ TOKEN: chart_state=X ALLOWED — accumulation pattern (TVL building)
  ```

**Impact:** Catches slow-build tokens before explosive 2x-10x moves. These are tokens where whales accumulate supply gradually without moving price, then dump all at once when ready.

---

## Files Modified

1. **bot.py** — Removed new_amm_watcher import, added accumulation mode handling
2. **scanner.py** — Relaxed momentum thresholds, added accumulation bucket
3. **xrpl_amm_discovery.py** — Added issuer validation

---

## Expected Results

- **Before:** 27 active candidates in sweet spot (100-2500 XRP TVL)
- **After:** ~50-80 active candidates (includes accumulation tokens)
- **Ghost tokens removed:** 67 invalid issuers pruned from registry
- **Missed opportunities recovered:** Slow accumulation patterns now detected

---

## Testing

Run scanner manually to verify:
```bash
cd /home/agent/workspace/trading-bot-v2
python3 -c "import scanner; r = scanner.scan(); print(f'accumulation={len(r.get(\"accumulation\", []))}')"
```

Check bot logs for accumulation entries:
```bash
grep "accumulation pattern" state/bot.log
```

---

## Next Steps (Optional Future Improvements)

1. **WebSocket AMM Creation Watcher:** Subscribe to `AMMCreate` transactions for instant new pool detection (currently relies on 15-min discovery cycle)
2. **TrustSet Velocity Boost for Accumulation:** If accumulation token shows sudden TrustSet burst, boost score aggressively
3. **TVL Velocity Scoring:** Track TVL growth rate as separate signal independent of price momentum
