"""
AgriTrace — Core business logic
----------------------------------
Extracted out of app.py so the demo-data seeder (seed_demo.py) creates
batches through the *exact same* code path a real user action would —
same hash chaining, same anchoring, same alert rules. Nothing here is
seed-only logic; app.py imports these directly.
"""

import db
import integrity


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


def get_batch(conn, batch_code):
    return conn.execute("SELECT * FROM batches WHERE batch_code = ?", (batch_code,)).fetchone()


def batch_bundle(conn, batch_code):
    """Everything needed to render a batch: batch, events, readings, alerts, anchors, trust score."""
    b = get_batch(conn, batch_code)
    if not b:
        return None
    events = conn.execute("SELECT * FROM events WHERE batch_id = ? ORDER BY id ASC", (b["id"],)).fetchall()
    readings = conn.execute("SELECT * FROM sensor_readings WHERE batch_id = ? ORDER BY id ASC", (b["id"],)).fetchall()
    alerts = conn.execute("SELECT * FROM alerts WHERE batch_id = ? ORDER BY id DESC", (b["id"],)).fetchall()
    anchors = conn.execute("SELECT * FROM blockchain_anchors WHERE batch_id = ? ORDER BY id DESC", (b["id"],)).fetchall()
    trust = integrity.compute_trust_score(b, events, readings, alerts, anchors)
    return b, events, readings, alerts, anchors, trust


def create_event(conn, chain_service, batch, event_type, actor_id, location, notes, reading=None, at=None):
    """Writes one hash-chained event and anchors it via the given blockchain service.
    `at` lets the seeder backdate a realistic multi-day timeline; live traffic omits it."""
    prev = conn.execute(
        "SELECT chain_hash FROM events WHERE batch_id = ? ORDER BY id DESC LIMIT 1", (batch["id"],)
    ).fetchone()
    prev_hash = prev["chain_hash"] if prev else batch["genesis_hash"]

    timestamp = at or db.now()
    data = {"batch_id": batch["id"], "event_type": event_type, "created_at": timestamp,
            "location": location, "notes": notes}
    dhash = integrity.data_hash(data)
    chash = integrity.chain_hash(prev_hash, dhash)

    cur = conn.execute(
        """INSERT INTO events (batch_id, event_type, actor_id, location, lat, lng, notes,
                                reading_id, prev_hash, data_hash, chain_hash, anchored, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)""",
        (batch["id"], event_type, actor_id, location, None, None, notes,
         reading["id"] if reading else None, prev_hash, dhash, chash, timestamp),
    )
    conn.commit()
    event_id = cur.lastrowid

    # Selective anchoring: every lifecycle event gets anchored (not every raw sensor reading)
    anchor = chain_service.anchor(dhash, {"batch_code": batch["batch_code"], "event_type": event_type})
    conn.execute(
        """INSERT INTO blockchain_anchors (batch_id, event_id, data_hash, tx_hash, block_number,
                                            network, mode, explorer_url, anchored_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (batch["id"], event_id, dhash, anchor["tx_hash"], anchor["block_number"],
         anchor["network"], anchor["mode"], anchor["explorer_url"], timestamp),
    )
    conn.execute("UPDATE events SET anchored = 1 WHERE id = ?", (event_id,))
    conn.commit()
    return event_id, anchor


def record_reading(conn, node_id, batch_id, temperature_c=None, humidity_pct=None, gas_ppm=None,
                    ethanol_ppm=None, shock_g=None, tamper=False, lat=None, lng=None,
                    at=None, source="manual"):
    timestamp = at or db.now()
    data = {"node_id": node_id, "batch_id": batch_id, "temperature_c": temperature_c,
            "humidity_pct": humidity_pct, "tamper": tamper, "captured_at": timestamp}
    rhash = integrity.data_hash(data)
    cur = conn.execute(
        """INSERT INTO sensor_readings (node_id, batch_id, temperature_c, humidity_pct, gas_ppm, ethanol_ppm,
                                         shock_g, tamper, lat, lng, reading_hash, prev_reading_hash, captured_at, synced_at, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (node_id, batch_id, temperature_c, humidity_pct, gas_ppm, ethanol_ppm, shock_g,
         1 if tamper else 0, lat, lng, rhash, None, timestamp, timestamp, source),
    )
    conn.commit()
    reading_id = cur.lastrowid
    reading = conn.execute("SELECT * FROM sensor_readings WHERE id = ?", (reading_id,)).fetchone()

    raised = []
    if temperature_c is not None and temperature_c > 12.0:
        raised.append(("TEMP_BREACH", "high", f"Temperature {temperature_c:.1f}°C exceeds the 12.0°C cold-chain limit"))
    if tamper:
        raised.append(("TAMPER", "critical", "Tamper / shock event detected by the node"))
    if gas_ppm is not None and gas_ppm > 400:
        raised.append(("GAS_ANOMALY", "medium", f"Gas sensor reading {gas_ppm:.0f} ppm suggests early spoilage"))
    for atype, sev, msg in raised:
        conn.execute(
            "INSERT INTO alerts (batch_id, node_id, alert_type, severity, message, resolved, created_at) VALUES (?,?,?,?,?,0,?)",
            (batch_id, node_id, atype, sev, msg, timestamp),
        )
    if raised:
        conn.commit()
    return reading, raised
