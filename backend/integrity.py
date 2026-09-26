"""
AgriTrace — Integrity Service
------------------------------
Every event and every sensor reading is linked into a per-batch / per-node
hash chain: each new record's hash is a function of its own data AND the
previous record's hash (like a git commit or a blockchain block header).
Changing or deleting any past record breaks every hash after it, so
tampering is detectable even before — or without — anchoring to Polygon.

This is the "Backend Integrity Service" the architecture calls for. The
Blockchain Service (blockchain.py) anchors a *summary* of this chain
on-chain for the key lifecycle events, rather than every single reading,
which keeps on-chain costs low (selective anchoring).
"""

import hashlib
import json


def canonical(data: dict) -> str:
    """Deterministic JSON encoding so the same data always hashes the same way."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def data_hash(data: dict) -> str:
    return sha256_hex(canonical(data))


def chain_hash(prev_hash: str, this_data_hash: str) -> str:
    return sha256_hex(prev_hash + this_data_hash)


GENESIS = "0" * 64


def verify_chain(records: list, genesis: str = GENESIS) -> dict:
    """
    records: ordered list of dicts each with keys
             {data (dict used to build data_hash), prev_hash, data_hash, chain_hash}
    genesis: the hash the first record's prev_hash must equal (each batch has
             its own genesis_hash, seeded at registration — NOT a shared constant).
    Returns {"valid": bool, "broken_at": int|None, "checked": int}
    """
    prev = genesis
    for i, rec in enumerate(records):
        expected_data_hash = data_hash(rec["data"])
        if expected_data_hash != rec["data_hash"]:
            return {"valid": False, "broken_at": i, "reason": "data modified", "checked": i}
        if rec["prev_hash"] != prev:
            return {"valid": False, "broken_at": i, "reason": "chain link broken", "checked": i}
        expected_chain_hash = chain_hash(rec["prev_hash"], rec["data_hash"])
        if expected_chain_hash != rec["chain_hash"]:
            return {"valid": False, "broken_at": i, "reason": "chain hash mismatch", "checked": i}
        prev = rec["chain_hash"]
    return {"valid": True, "broken_at": None, "checked": len(records)}


# --- Trust Engine -----------------------------------------------------

def compute_trust_score(batch, events, readings, alerts, anchors):
    """
    Produces a 0-100 trust score + letter grade + explainable breakdown.
    Pure function of data already in the database — no external calls.
    """
    score = 100.0
    breakdown = []

    # 1. Chain integrity (heaviest weight — this is the whole point)
    chain_records = [
        {
            "data": {"event_type": e["event_type"], "batch_id": e["batch_id"], "created_at": e["created_at"],
                      "location": e["location"], "notes": e["notes"]},
            "prev_hash": e["prev_hash"], "data_hash": e["data_hash"], "chain_hash": e["chain_hash"],
        }
        for e in events
    ]
    integrity = verify_chain(chain_records, genesis=batch["genesis_hash"])
    if not integrity["valid"]:
        score -= 45
        breakdown.append({"factor": "Event chain integrity", "impact": -45,
                           "detail": f"Chain broken at record {integrity['broken_at']} ({integrity['reason']})"})
    else:
        breakdown.append({"factor": "Event chain integrity", "impact": 0, "detail": "All events verified intact"})

    # 2. Cold-chain / sensor threshold breaches
    breach_count = sum(1 for r in readings if r["temperature_c"] is not None and r["temperature_c"] > 12)
    if breach_count:
        penalty = min(25, breach_count * 4)
        score -= penalty
        breakdown.append({"factor": "Temperature threshold breaches", "impact": -penalty,
                           "detail": f"{breach_count} reading(s) above 12°C cold-chain limit"})
    else:
        breakdown.append({"factor": "Temperature threshold breaches", "impact": 0, "detail": "Cold chain held throughout"})

    # 3. Tamper / shock events
    tamper_count = sum(1 for r in readings if r["tamper"])
    if tamper_count:
        penalty = min(30, tamper_count * 10)
        score -= penalty
        breakdown.append({"factor": "Tamper / shock detections", "impact": -penalty,
                           "detail": f"{tamper_count} tamper event(s) flagged by the node"})
    else:
        breakdown.append({"factor": "Tamper / shock detections", "impact": 0, "detail": "No tamper events"})

    # 4. Unresolved alerts
    open_alerts = [a for a in alerts if not a["resolved"]]
    if open_alerts:
        penalty = min(15, len(open_alerts) * 3)
        score -= penalty
        breakdown.append({"factor": "Unresolved alerts", "impact": -penalty,
                           "detail": f"{len(open_alerts)} open alert(s)"})
    else:
        breakdown.append({"factor": "Unresolved alerts", "impact": 0, "detail": "No open alerts"})

    # 5. Blockchain anchoring coverage
    key_events = [e for e in events if e["event_type"] in
                  ("HARVEST", "WAREHOUSE_IN", "WAREHOUSE_OUT", "DISTRIBUTOR_RECEIVE", "RETAIL_RECEIVE")]
    anchored_count = sum(1 for e in key_events if e["anchored"])
    if key_events and anchored_count < len(key_events):
        penalty = 10
        score -= penalty
        breakdown.append({"factor": "Blockchain anchoring", "impact": -penalty,
                           "detail": f"{anchored_count}/{len(key_events)} key events anchored on-chain"})
    else:
        breakdown.append({"factor": "Blockchain anchoring", "impact": 0,
                           "detail": f"{anchored_count}/{max(len(key_events),1)} key events anchored on-chain"})

    score = max(0, round(score))
    grade = "A" if score >= 85 else "B" if score >= 65 else "C" if score >= 40 else "D"
    return {"score": score, "grade": grade, "breakdown": breakdown, "chain_valid": integrity["valid"]}
