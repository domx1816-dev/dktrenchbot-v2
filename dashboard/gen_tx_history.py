"""
gen_tx_history.py — Generate tx_history.json for the dashboard.
Combines DKBot (XRPL DEX trades) + Axiom Bot (prediction market bets).
"""
import json, time, os, sys

EXEC_LOG   = "/home/agent/workspace/trading-bot-v2/state/execution_log.json"
AXIOM_POS  = "/home/agent/workspace/axiom-bot/bot/state/state_data/positions.json"
AXIOM_JRNL = "/home/agent/workspace/axiom-bot/trade_journal.jsonl"
OUT_FILE   = "/home/agent/workspace/trading-bot-v2/dashboard/tx_history.json"

STATE_FILE = "/home/agent/workspace/trading-bot-v2/state/state.json"

def load_dkbot_trades():
    """
    Read from state.json trade_history — each entry is a COMPLETE position
    with total P&L already calculated (buy + all partial/full sells combined).
    This avoids the partial-sell WIN bug from execution_log.json.
    """
    trades = []
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except:
        return []

    # Closed trade history
    for t in state.get('trade_history', []):
        sym     = t.get('symbol', '?')
        pnl     = float(t.get('pnl_xrp', 0) or 0)
        spent   = float(t.get('xrp_spent', 0) or 0)
        ret     = round(spent + pnl, 4)
        pnl_pct = round((pnl / spent * 100) if spent else 0, 2)
        ts      = t.get('closed_at') or t.get('opened_at') or time.time()
        reason  = t.get('exit_reason', 'exit')
        score   = t.get('score', 0)
        chart   = t.get('chart_state', '?')

        # Correct result based on full position P&L
        if pnl > 0.05:
            result = 'WIN'
        elif pnl < -0.05:
            result = 'LOSS'
        else:
            result = 'FLAT'

        trades.append({
            'bot':     'DKTrenchBot',
            'type':    'XRPL DEX',
            'symbol':  sym,
            'action':  f'BUY→{reason}',
            'stake':   round(spent, 4),
            'return':  ret,
            'pnl_xrp': round(pnl, 4),
            'pnl_pct': pnl_pct,
            'result':  result,
            'ts':      ts,
            'tx_hash': '',
            'detail':  f"Score {score} | {chart}",
        })

    # Open positions
    for pos_key, p in state.get('positions', {}).items():
        sym = pos_key.split(':')[0]
        trades.append({
            'bot':     'DKTrenchBot',
            'type':    'XRPL DEX',
            'symbol':  sym,
            'action':  'OPEN',
            'stake':   round(float(p.get('xrp_spent', 0) or 0), 4),
            'return':  None,
            'pnl_xrp': None,
            'pnl_pct': 0,
            'result':  'OPEN',
            'ts':      p.get('entry_time', time.time()),
            'tx_hash': '',
            'detail':  f"Score {p.get('score',0)} | {p.get('chart_state','?')}",
        })

    return trades

def load_axiom_trades():
    trades = []

    # Load resolved positions
    try:
        with open(AXIOM_POS) as f:
            positions = json.load(f)
    except:
        positions = []

    # Build a stake lookup from journal
    journal_stakes = {}
    try:
        with open(AXIOM_JRNL) as f:
            for line in f:
                e = json.loads(line.strip())
                if e.get('event') == 'bet_placed':
                    journal_stakes[e['market_id']] = e
    except:
        pass

    for p in positions:
        status = p.get('status', 'open')
        mid    = p.get('market_id') or p.get('market_address', '')
        j      = journal_stakes.get(mid, {})
        stake  = p.get('stake_xrp') or j.get('stake_xrp', 0)
        pnl    = p.get('pnl_xrp')
        ts     = p.get('opened_at') or j.get('ts', time.time())

        if status in ('won', 'closed') and pnl is not None and pnl > 0:
            result = 'WIN'
        elif status == 'lost' or (pnl is not None and pnl < 0):
            result = 'LOSS'
        elif status == 'open':
            result = 'OPEN'
        else:
            result = 'PENDING'

        direction = p.get('direction', '?').upper()
        family    = p.get('family', '?')

        trades.append({
            'bot':     'Axiom Bot',
            'type':    family.replace('_', ' ').title(),
            'symbol':  p.get('title', '?')[:50],
            'action':  direction,
            'stake':   round(stake, 4) if stake else 0,
            'return':  round(stake + pnl, 4) if (stake and pnl is not None) else None,
            'pnl_xrp': round(pnl, 4) if pnl is not None else None,
            'pnl_pct': round((pnl / stake * 100) if (stake and pnl) else 0, 2),
            'result':  result,
            'ts':      ts,
            'tx_hash': p.get('tx', ''),
            'detail':  f"Prob {p.get('prob',0):.0%} | Edge {p.get('edge',0):.3f}"
        })

    return trades

def generate():
    dk_trades    = load_dkbot_trades()
    axiom_trades = load_axiom_trades()
    def _ts_key(x):
        v = x.get('ts', 0)
        if isinstance(v, str):
            try:
                from datetime import datetime, timezone
                return datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()
            except:
                return 0
        return float(v or 0)
    all_trades = sorted(dk_trades + axiom_trades, key=_ts_key, reverse=True)

    # Stats
    closed = [t for t in all_trades if t['result'] in ('WIN','LOSS')]
    wins   = [t for t in closed if t['result'] == 'WIN']
    total_pnl = sum(t['pnl_xrp'] or 0 for t in closed)

    output = {
        'generated_at': time.time(),
        'stats': {
            'total_trades':  len(closed),
            'wins':          len(wins),
            'losses':        len(closed) - len(wins),
            'win_rate':      round(len(wins) / len(closed) * 100, 1) if closed else 0,
            'total_pnl_xrp': round(total_pnl, 4),
            'open_count':    len([t for t in all_trades if t['result'] == 'OPEN']),
        },
        'trades': all_trades
    }

    with open(OUT_FILE, 'w') as f:
        json.dump(output, f)

    print(f"Generated {len(all_trades)} trades → {OUT_FILE}")
    print(f"Stats: {output['stats']}")

if __name__ == '__main__':
    generate()
