"""
AgriTrace backend.

    Web Portals / IoT
          |
      Flask (this file)
          |
    SQLite (Postgres-portable) + Integrity Service (integrity.py)
          |
    Blockchain Service (blockchain.py)
          |
    Polygon Smart Contract (contracts/AgriTraceRegistry.sol)
          |
    Polygon Network -> PolygonScan

Run:  python app.py   (see README.md)
"""

import os
import datetime

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

import db
import auth
import integrity
import blockchain
import core

app = Flask(__name__)
app.secret_key = auth.SECRET_KEY
chain_service = blockchain.get_blockchain_service()
db.init_db()

STAGE_FLOW = [
    {"key": "farm", "label": "Farm", "icon": "farm", "event": "HARVEST", "role": "farmer"},
    {"key": "collection", "label": "Collection Centre", "icon": "collection", "event": "COLLECTION", "role": "farmer"},
    {"key": "transport", "label": "Transport", "icon": "transport", "event": "TRANSPORT_DISPATCH", "role": "warehouse"},
    {"key": "warehouse", "label": "Warehouse / Ripening", "icon": "warehouse", "event": "WAREHOUSE_IN", "role": "warehouse"},
    {"key": "distributor", "label": "Distributor", "icon": "distributor", "event": "DISTRIBUTOR_RECEIVE", "role": "distributor"},
    {"key": "retail", "label": "Retail", "icon": "retail", "event": "RETAIL_RECEIVE", "role": "distributor"},
    {"key": "consumer", "label": "Consumer", "icon": "consumer", "event": "SOLD", "role": "distributor"},
]
STAGE_KEYS = [s["key"] for s in STAGE_FLOW]
TEMP_LIMIT_C = 12.0


def get_batch_or_404(conn, batch_code):
    b = core.get_batch(conn, batch_code)
    if not b:
        abort(404)
    return b


# ------------------------------------------------------------------ pages

@app.route("/")
def index():
    if auth.current_user():
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("login.html", next_url=request.args.get("next", ""))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    conn = db.get_conn()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not user or not auth.verify_password(password, user["password_hash"]):
        return render_template("login.html", error="Invalid username or password.", next_url=request.form.get("next", "")), 401
    session["token"] = auth.issue_token(user)
    session["role"] = user["role"]
    session["name"] = user["full_name"]
    nxt = request.form.get("next") or url_for("dashboard")
    return redirect(nxt)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@auth.login_required
def dashboard(user):
    conn = db.get_conn()
    if user["role"] == "farmer":
        batches = conn.execute("SELECT * FROM batches WHERE farmer_id = ? ORDER BY id DESC", (user["uid"],)).fetchall()
    else:
        batches = conn.execute("SELECT * FROM batches ORDER BY id DESC").fetchall()
    total = len(batches)
    in_transit = sum(1 for b in batches if b["status"] in ("collection", "transport"))
    open_alerts = conn.execute("SELECT COUNT(*) c FROM alerts WHERE resolved = 0").fetchone()["c"]
    anchors = conn.execute("SELECT COUNT(*) c FROM blockchain_anchors").fetchone()["c"]
    recent_alerts = conn.execute(
        """SELECT alerts.*, batches.batch_code FROM alerts
           JOIN batches ON batches.id = alerts.batch_id
           ORDER BY alerts.id DESC LIMIT 6"""
    ).fetchall()

    trust_scores = []
    for b in batches[:8]:
        bundle = core.batch_bundle(conn, b["batch_code"])
        trust_scores.append(bundle[5]["score"])
    avg_trust = round(sum(trust_scores) / len(trust_scores)) if trust_scores else None

    conn.close()
    return render_template(
        "dashboard.html", user=user, batches=batches[:8], total=total, in_transit=in_transit,
        open_alerts=open_alerts, anchors=anchors, stage_flow=STAGE_FLOW, recent_alerts=recent_alerts,
        avg_trust=avg_trust,
    )


@app.route("/register", methods=["GET", "POST"])
@auth.roles_required("farmer")
def register_page(user):
    conn = db.get_conn()
    if request.method == "GET":
        nodes = conn.execute("SELECT * FROM nodes WHERE owner_id = ?", (user["uid"],)).fetchall()
        conn.close()
        return render_template("register.html", user=user, nodes=nodes)

    produce_type = request.form.get("produce_type", "Banana").strip()
    variety = request.form.get("variety", "").strip()
    quantity = float(request.form.get("quantity_kg") or 0)
    origin = request.form.get("origin_location", "").strip()
    node_id = request.form.get("node_id") or None

    prefix = "".join(ch for ch in produce_type.upper() if ch.isalpha())[:3] or "AGT"
    year = datetime.datetime.now(datetime.timezone.utc).year
    seq = conn.execute(
        "SELECT COUNT(*) c FROM batches WHERE batch_code LIKE ?", (f"{prefix}-{year}-%",)
    ).fetchone()["c"] + 1
    batch_code = f"{prefix}-{year}-{seq:03d}"
    genesis = integrity.sha256_hex(f"{batch_code}|{produce_type}|{db.now()}")

    cur = conn.execute(
        """INSERT INTO batches (batch_code, produce_type, variety, quantity_kg, farmer_id, origin_location,
                                 node_id, harvest_date, status, current_holder_id, genesis_hash, created_at)
           VALUES (?,?,?,?,?,?,?,?, 'farm', ?, ?, ?)""",
        (batch_code, produce_type, variety, quantity, user["uid"], origin, node_id,
         request.form.get("harvest_date") or db.now()[:10], user["uid"], genesis, db.now()),
    )
    conn.commit()
    batch_id = cur.lastrowid
    batch = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()

    core.create_event(conn, chain_service, batch, "HARVEST", user["uid"], origin, "Batch registered at origin — genesis record created")
    conn.close()
    return redirect(url_for("batch_detail", batch_code=batch_code))


@app.route("/track")
@auth.login_required
def track_page(user):
    conn = db.get_conn()
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    sql = "SELECT * FROM batches WHERE 1=1"
    params = []
    if q:
        sql += " AND (batch_code LIKE ? OR produce_type LIKE ? OR origin_location LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if status_filter:
        sql += " AND status = ?"
        params.append(status_filter)
    sql += " ORDER BY id DESC"
    batches = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("track.html", user=user, batches=batches, q=q, status_filter=status_filter, stage_flow=STAGE_FLOW)


@app.route("/batch/<batch_code>")
@auth.login_required
def batch_detail(user, batch_code):
    conn = db.get_conn()
    bundle = core.batch_bundle(conn, batch_code)
    if not bundle:
        conn.close()
        abort(404)
    b, events, readings, alerts, anchors, trust = bundle
    idx = STAGE_KEYS.index(b["status"])
    next_stage = STAGE_FLOW[idx + 1] if idx + 1 < len(STAGE_FLOW) else None
    can_advance = bool(next_stage) and (user["role"] == "admin" or user["role"] == next_stage["role"])
    conn.close()
    return render_template(
        "batch_detail.html", user=user, batch=b, events=events, readings=readings, alerts=alerts,
        anchors=anchors, trust=trust, stage_flow=STAGE_FLOW, stage_index=idx,
        next_stage=next_stage, can_advance=can_advance, readings_json=core.rows_to_list(readings),
    )


@app.route("/batch/<batch_code>/advance", methods=["POST"])
@auth.login_required
def batch_advance(user, batch_code):
    conn = db.get_conn()
    b = get_batch_or_404(conn, batch_code)
    idx = STAGE_KEYS.index(b["status"])
    if idx + 1 >= len(STAGE_FLOW):
        conn.close()
        return redirect(url_for("batch_detail", batch_code=batch_code))
    next_stage = STAGE_FLOW[idx + 1]
    if user["role"] != "admin" and user["role"] != next_stage["role"]:
        conn.close()
        abort(403)

    location = request.form.get("location", b["origin_location"])
    notes = request.form.get("notes") or f"Moved to {next_stage['label']}"
    temp = request.form.get("temperature_c")
    humidity = request.form.get("humidity_pct")
    tamper = bool(request.form.get("tamper"))

    reading = None
    if temp or humidity or tamper:
        reading, _raised = core.record_reading(
            conn, b["node_id"], b["id"],
            temperature_c=float(temp) if temp else None,
            humidity_pct=float(humidity) if humidity else None,
            tamper=tamper, source="manual",
        )

    core.create_event(conn, chain_service, b, next_stage["event"], user["uid"], location, notes, reading=reading)
    conn.execute("UPDATE batches SET status = ?, current_holder_id = ? WHERE id = ?",
                 (next_stage["key"], user["uid"], b["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("batch_detail", batch_code=batch_code))


@app.route("/blockchain")
@auth.login_required
def blockchain_page(user):
    conn = db.get_conn()
    anchors = conn.execute(
        """SELECT blockchain_anchors.*, batches.batch_code, batches.produce_type, events.event_type
           FROM blockchain_anchors
           JOIN batches ON batches.id = blockchain_anchors.batch_id
           LEFT JOIN events ON events.id = blockchain_anchors.event_id
           ORDER BY blockchain_anchors.id DESC LIMIT 100"""
    ).fetchall()
    conn.close()
    mode = chain_service.mode
    return render_template("blockchain.html", user=user, anchors=anchors, mode=mode, network=blockchain.NETWORK_NAME)


@app.route("/blockchain/tx/<tx_hash>")
@auth.login_required
def blockchain_tx(user, tx_hash):
    conn = db.get_conn()
    anchor = conn.execute(
        """SELECT blockchain_anchors.*, batches.batch_code, events.event_type, events.location, events.notes
           FROM blockchain_anchors
           JOIN batches ON batches.id = blockchain_anchors.batch_id
           LEFT JOIN events ON events.id = blockchain_anchors.event_id
           WHERE tx_hash = ?""", (tx_hash,)
    ).fetchone()
    conn.close()
    if not anchor:
        abort(404)
    block = chain_service.get_tx(tx_hash) if hasattr(chain_service, "get_tx") else None
    return render_template("blockchain_tx.html", user=user, anchor=anchor, block=block)


@app.route("/verify/<batch_code>")
def verify_page(batch_code):
    """Public digital passport — no login required. This is what the QR code opens."""
    conn = db.get_conn()
    bundle = core.batch_bundle(conn, batch_code)
    if not bundle:
        conn.close()
        abort(404)
    b, events, readings, alerts, anchors, trust = bundle
    farmer = conn.execute("SELECT organisation FROM users WHERE id = ?", (b["farmer_id"],)).fetchone()
    conn.close()
    idx = STAGE_KEYS.index(b["status"])
    verify_url = request.url_root.rstrip("/") + url_for("verify_page", batch_code=batch_code)
    return render_template(
        "verify.html", batch=b, events=events, readings=readings, alerts=alerts, anchors=anchors,
        trust=trust, stage_flow=STAGE_FLOW, stage_index=idx, farmer=farmer, verify_url=verify_url,
    )


@app.route("/consumer")
def consumer_page():
    return render_template("consumer.html")


@app.route("/analytics")
@auth.login_required
def analytics_page(user):
    conn = db.get_conn()
    batches = core.rows_to_list(conn.execute("SELECT batch_code, produce_type, status FROM batches ORDER BY id DESC").fetchall())
    conn.close()
    return render_template("analytics.html", user=user, batches=batches, stage_flow=STAGE_FLOW)


@app.route("/database")
@auth.login_required
def database_page(user):
    conn = db.get_conn()
    events = conn.execute(
        """SELECT events.*, batches.batch_code, users.full_name AS actor_name, users.role AS actor_role
           FROM events
           JOIN batches ON batches.id = events.batch_id
           LEFT JOIN users ON users.id = events.actor_id
           ORDER BY events.id DESC"""
    ).fetchall()
    readings = conn.execute(
        """SELECT sensor_readings.*, batches.batch_code, nodes.node_code
           FROM sensor_readings
           LEFT JOIN batches ON batches.id = sensor_readings.batch_id
           LEFT JOIN nodes ON nodes.id = sensor_readings.node_id
           ORDER BY sensor_readings.id DESC"""
    ).fetchall()
    anchors = conn.execute(
        """SELECT blockchain_anchors.*, batches.batch_code, events.event_type
           FROM blockchain_anchors
           JOIN batches ON batches.id = blockchain_anchors.batch_id
           LEFT JOIN events ON events.id = blockchain_anchors.event_id
           ORDER BY blockchain_anchors.id DESC"""
    ).fetchall()
    alerts = conn.execute(
        """SELECT alerts.*, batches.batch_code FROM alerts
           JOIN batches ON batches.id = alerts.batch_id
           ORDER BY alerts.id DESC"""
    ).fetchall()
    batches = conn.execute("SELECT * FROM batches ORDER BY id DESC").fetchall()
    counts = {
        "events": len(events), "readings": len(readings), "anchors": len(anchors),
        "alerts": len(alerts), "batches": len(batches),
    }
    conn.close()
    return render_template(
        "database.html", user=user, events=events, readings=readings, anchors=anchors,
        alerts=alerts, batches=batches, counts=counts,
    )


@app.route("/alerts")
@auth.login_required
def alerts_page(user):
    conn = db.get_conn()
    alerts = conn.execute(
        """SELECT alerts.*, batches.batch_code, batches.produce_type FROM alerts
           JOIN batches ON batches.id = alerts.batch_id
           ORDER BY alerts.resolved ASC, alerts.id DESC"""
    ).fetchall()
    conn.close()
    return render_template("alerts.html", user=user, alerts=alerts)


@app.route("/alerts/<int:alert_id>/resolve", methods=["POST"])
@auth.login_required
def resolve_alert(user, alert_id):
    conn = db.get_conn()
    conn.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("alerts_page"))


# -------------------------------------------------------------------- API

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    payload = request.get_json(force=True)
    conn = db.get_conn()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (payload.get("username", ""),)).fetchone()
    conn.close()
    if not user or not auth.verify_password(payload.get("password", ""), user["password_hash"]):
        return jsonify({"error": "invalid credentials"}), 401
    return jsonify({"token": auth.issue_token(user), "role": user["role"], "name": user["full_name"]})


@app.route("/api/batches")
@auth.login_required
def api_batches(user):
    conn = db.get_conn()
    batches = core.rows_to_list(conn.execute("SELECT * FROM batches ORDER BY id DESC").fetchall())
    conn.close()
    return jsonify(batches)


@app.route("/api/batches/<batch_code>")
def api_batch_detail(batch_code):
    """Public read — powers both the internal detail view and third-party integrations."""
    conn = db.get_conn()
    bundle = core.batch_bundle(conn, batch_code)
    conn.close()
    if not bundle:
        return jsonify({"error": "not found"}), 404
    b, events, readings, alerts, anchors, trust = bundle
    return jsonify({
        "batch": dict(b), "events": core.rows_to_list(events), "readings": core.rows_to_list(readings),
        "alerts": core.rows_to_list(alerts), "anchors": core.rows_to_list(anchors), "trust": trust,
    })


@app.route("/api/batches/<batch_code>/verify")
def api_batch_verify(batch_code):
    """Recomputes the hash chain fresh from stored data — proves nothing was tampered with."""
    conn = db.get_conn()
    bundle = core.batch_bundle(conn, batch_code)
    conn.close()
    if not bundle:
        return jsonify({"error": "not found"}), 404
    b, events, readings, alerts, anchors, trust = bundle
    return jsonify({"batch_code": batch_code, "chain_valid": trust["chain_valid"], "trust_score": trust["score"],
                     "grade": trust["grade"], "breakdown": trust["breakdown"]})


@app.route("/api/iot/ingest", methods=["POST"])
def api_iot_ingest():
    """A single live reading from an ESP32 node (or the simulator)."""
    device_key = request.headers.get("X-Device-Key", "")
    conn = db.get_conn()
    node = auth.device_key_valid(conn, device_key)
    if not node:
        conn.close()
        return jsonify({"error": "invalid device key"}), 401

    payload = request.get_json(force=True)
    batch = conn.execute(
        "SELECT * FROM batches WHERE node_id = ? AND status NOT IN ('consumer')", (node["id"],)
    ).fetchone()

    reading, raised = core.record_reading(
        conn, node["id"], batch["id"] if batch else None,
        temperature_c=payload.get("temperature_c"), humidity_pct=payload.get("humidity_pct"),
        gas_ppm=payload.get("gas_ppm"), ethanol_ppm=payload.get("ethanol_ppm"), shock_g=payload.get("shock_g"),
        tamper=bool(payload.get("tamper")), lat=payload.get("lat"), lng=payload.get("lng"),
        at=payload.get("captured_at"), source=payload.get("source", "esp32"),
    )
    conn.execute("UPDATE nodes SET last_seen = ?, battery_pct = ? WHERE id = ?",
                 (db.now(), payload.get("battery_pct", node["battery_pct"]), node["id"]))
    conn.commit()
    conn.close()
    return jsonify({"stored": True, "reading_id": reading["id"], "alerts_raised": len(raised)})


@app.route("/api/iot/sync", methods=["POST"])
def api_iot_sync():
    """Bulk sync of an offline-buffered batch of readings (see iot/esp32_simulator.py)."""
    device_key = request.headers.get("X-Device-Key", "")
    conn = db.get_conn()
    node = auth.device_key_valid(conn, device_key)
    if not node:
        conn.close()
        return jsonify({"error": "invalid device key"}), 401
    payload = request.get_json(force=True)
    readings = payload.get("readings", [])
    stored = 0
    for r in readings:
        batch = conn.execute(
            "SELECT * FROM batches WHERE node_id = ? AND status NOT IN ('consumer')", (node["id"],)
        ).fetchone()
        core.record_reading(
            conn, node["id"], batch["id"] if batch else None,
            temperature_c=r.get("temperature_c"), humidity_pct=r.get("humidity_pct"), gas_ppm=r.get("gas_ppm"),
            ethanol_ppm=r.get("ethanol_ppm"), shock_g=r.get("shock_g"), tamper=bool(r.get("tamper")),
            lat=r.get("lat"), lng=r.get("lng"), at=r.get("captured_at"), source="esp32-offline-buffer",
        )
        stored += 1
    conn.execute("UPDATE nodes SET last_seen = ? WHERE id = ?", (db.now(), node["id"]))
    conn.commit()
    conn.close()
    return jsonify({"stored": stored})


@app.route("/api/analytics/summary")
@auth.login_required
def api_analytics_summary(user):
    conn = db.get_conn()
    batches = core.rows_to_list(conn.execute("SELECT * FROM batches").fetchall())
    readings = core.rows_to_list(conn.execute("SELECT * FROM sensor_readings ORDER BY id ASC").fetchall())
    alerts = core.rows_to_list(conn.execute("SELECT * FROM alerts").fetchall())
    all_events = core.rows_to_list(conn.execute("SELECT * FROM events ORDER BY batch_id ASC, id ASC").fetchall())
    anchors_count = conn.execute("SELECT COUNT(*) c FROM blockchain_anchors").fetchone()["c"]

    status_counts = {}
    for b in batches:
        status_counts[b["status"]] = status_counts.get(b["status"], 0) + 1

    temp_series = [{"t": r["captured_at"], "v": r["temperature_c"]} for r in readings if r["temperature_c"] is not None][-40:]
    humidity_series = [{"t": r["captured_at"], "v": r["humidity_pct"]} for r in readings if r["humidity_pct"] is not None][-40:]

    alert_types = {}
    for a in alerts:
        alert_types[a["alert_type"]] = alert_types.get(a["alert_type"], 0) + 1

    scores = []
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for b in batches:
        bundle = core.batch_bundle(conn, b["batch_code"])
        trust = bundle[5]
        scores.append(trust["score"])
        grade_counts[trust["grade"]] = grade_counts.get(trust["grade"], 0) + 1

    # Stage-transition durations: how long, on average, does a batch take to
    # move from one stage into the next? This is the meaningful, operational
    # number a traceability platform should surface — it points straight at
    # where a supply chain is actually losing time.
    by_batch = {}
    for e in all_events:
        by_batch.setdefault(e["batch_id"], []).append(e)
    duration_samples = {}
    for evs in by_batch.values():
        for i in range(1, len(evs)):
            try:
                t0 = datetime.datetime.fromisoformat(evs[i - 1]["created_at"].replace("Z", "+00:00"))
                t1 = datetime.datetime.fromisoformat(evs[i]["created_at"].replace("Z", "+00:00"))
                hours = (t1 - t0).total_seconds() / 3600.0
            except (ValueError, AttributeError):
                continue
            if hours >= 0:
                duration_samples.setdefault(evs[i]["event_type"], []).append(hours)
    stage_durations = {k: round(sum(v) / len(v), 1) for k, v in duration_samples.items() if v}

    conn.close()
    avg_trust = round(sum(scores) / len(scores), 1) if scores else 0

    return jsonify({
        "total_batches": len(batches), "status_counts": status_counts, "temp_series": temp_series,
        "humidity_series": humidity_series, "alert_types": alert_types,
        "open_alerts": sum(1 for a in alerts if not a["resolved"]),
        "total_anchors": anchors_count, "avg_trust_score": avg_trust,
        "stage_durations": stage_durations, "trust_distribution": grade_counts,
    })


@app.route("/api/nodes")
@auth.login_required
def api_nodes(user):
    conn = db.get_conn()
    nodes = core.rows_to_list(conn.execute("SELECT * FROM nodes").fetchall())
    conn.close()
    return jsonify(nodes)


@app.context_processor
def inject_globals():
    return {"stage_flow_global": STAGE_FLOW}


if __name__ == "__main__":
    fresh = not os.path.exists(db.DB_PATH)
    db.init_db()
    if fresh:
        import seed_demo
        conn = db.get_conn()
        seed_demo.run(conn, chain_service, core)
        conn.close()

    port = int(os.environ.get("PORT", 5000))
    print(f"\n  AgriTrace running →  http://127.0.0.1:{port}")
    print("  Demo accounts (also shown on the sign-in page): admin/admin123 · farmer1/farmer123 · warehouse1/warehouse123 · distributor1/distributor123\n")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG", "1") == "1")
