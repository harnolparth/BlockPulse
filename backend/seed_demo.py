"""
AgriTrace — Demo data seeder
------------------------------
Runs once, only on a brand-new database, so the app is never opened to an
empty screen for a screening round. Builds three batches through the exact
same functions real user actions use (core.create_event, core.record_reading)
— nothing here is faked data bolted on afterwards; it's a real, backdated
run of the system.

  BAN-2026-001  Banana   — clean cold chain, reaches Retail, trust A (~97)
  PIN-2026-001  Pineapple — one cold-chain breach in transit, reaches
                            Distributor, open alert, trust B (~74)
  GIN-2026-001  Ginger    — a tamper/shock event at the warehouse, reaches
                            Warehouse, open critical alert, trust C (~55)

All three are still moving through the chain (not stuck at the farm), so
the journey view, the alerts page, and analytics all have real data the
moment the app is opened.
"""

import datetime
import integrity

STAGE_FLOW = [
    {"key": "farm", "label": "Farm", "event": "HARVEST"},
    {"key": "collection", "label": "Collection Centre", "event": "COLLECTION"},
    {"key": "transport", "label": "Transport", "event": "TRANSPORT_DISPATCH"},
    {"key": "warehouse", "label": "Warehouse / Ripening", "event": "WAREHOUSE_IN"},
    {"key": "distributor", "label": "Distributor", "event": "DISTRIBUTOR_RECEIVE"},
    {"key": "retail", "label": "Retail", "event": "RETAIL_RECEIVE"},
    {"key": "consumer", "label": "Consumer", "event": "SOLD"},
]


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def make_batch(conn, chain_service, core, cur, produce, variety, qty, origin, node_id,
               farmer_id, holders_by_stage, harvested_days_ago, target_stage_index,
               readings_plan):
    """
    holders_by_stage: dict stage_key -> user_id who performs that stage's handover
    readings_plan: list of (stage_index_after_which_to_record, temp, humidity, gas, tamper, hours_offset)
                   readings are attached once the batch reaches that stage
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    harvest_time = now - datetime.timedelta(days=harvested_days_ago)

    year = harvest_time.year
    prefix = "".join(ch for ch in produce.upper() if ch.isalpha())[:3]
    seq = cur.execute("SELECT COUNT(*) c FROM batches WHERE batch_code LIKE ?", (f"{prefix}-{year}-%",)).fetchone()["c"] + 1
    batch_code = f"{prefix}-{year}-{seq:03d}"
    genesis = integrity.sha256_hex(f"{batch_code}|{produce}|{iso(harvest_time)}")

    insert = conn.execute(
        """INSERT INTO batches (batch_code, produce_type, variety, quantity_kg, farmer_id, origin_location,
                                 node_id, harvest_date, status, current_holder_id, genesis_hash, created_at)
           VALUES (?,?,?,?,?,?,?,?, 'farm', ?, ?, ?)""",
        (batch_code, produce, variety, qty, farmer_id, origin, node_id,
         harvest_time.strftime("%Y-%m-%d"), farmer_id, genesis, iso(harvest_time)),
    )
    conn.commit()
    batch = conn.execute("SELECT * FROM batches WHERE id = ?", (insert.lastrowid,)).fetchone()

    # Walk the batch forward through its stages up to target_stage_index (0 = stays at farm)
    stage_time = harvest_time
    for i in range(0, target_stage_index + 1):
        stage = STAGE_FLOW[i]
        actor = holders_by_stage.get(stage["key"], farmer_id)
        location = origin if i == 0 else f"{stage['label']}, en route from {origin}"

        reading = None
        for plan in readings_plan:
            if plan["after_stage"] == i:
                r, _raised = core.record_reading(
                    conn, node_id, batch["id"],
                    temperature_c=plan.get("temp"), humidity_pct=plan.get("humidity"),
                    gas_ppm=plan.get("gas"), tamper=plan.get("tamper", False),
                    at=iso(stage_time + datetime.timedelta(hours=plan.get("hours_offset", 1))),
                    source="esp32-seed",
                )
                reading = r

        if i == 0:
            notes = "Batch registered at origin — genesis record created"
        else:
            notes = f"Moved to {stage['label']}"
        core.create_event(conn, chain_service, batch, stage["event"], actor, location, notes,
                           reading=reading, at=iso(stage_time))

        conn.execute("UPDATE batches SET status = ?, current_holder_id = ? WHERE id = ?",
                     (stage["key"], actor, batch["id"]))
        conn.commit()
        stage_time += datetime.timedelta(hours=14)

    return conn.execute("SELECT * FROM batches WHERE id = ?", (batch["id"],)).fetchone()


def run(conn, chain_service, core):
    # Only ever seed an empty database
    existing = conn.execute("SELECT COUNT(*) c FROM batches").fetchone()["c"]
    if existing:
        return

    users = {row["username"]: row["id"] for row in conn.execute("SELECT id, username FROM users")}
    node = conn.execute("SELECT * FROM nodes LIMIT 1").fetchone()
    node_id = node["id"] if node else None
    farmer_id = users.get("farmer1")
    holders = {
        "farm": farmer_id, "collection": farmer_id,
        "transport": users.get("warehouse1"), "warehouse": users.get("warehouse1"),
        "distributor": users.get("distributor1"), "retail": users.get("distributor1"), "consumer": users.get("distributor1"),
    }
    cur = conn

    # ---- Batch 1: Banana — clean run, reaches Retail, trust ~A -----------
    make_batch(
        conn, chain_service, core, cur,
        produce="Banana", variety="Malbhog", qty=240, origin="Plot 4, Ri-Bhoi, Meghalaya",
        node_id=node_id, farmer_id=farmer_id, holders_by_stage=holders,
        harvested_days_ago=6, target_stage_index=5,  # through Retail
        readings_plan=[
            {"after_stage": 2, "temp": 9.2, "humidity": 68, "gas": 310, "hours_offset": 2},
            {"after_stage": 3, "temp": 8.7, "humidity": 66, "gas": 295, "hours_offset": 3},
            {"after_stage": 4, "temp": 9.5, "humidity": 70, "gas": 320, "hours_offset": 2},
        ],
    )

    # ---- Batch 2: Pineapple — repeated cold-chain breaches, reaches Distributor, trust ~B
    make_batch(
        conn, chain_service, core, cur,
        produce="Pineapple", variety="Kew", qty=310, origin="Sohra Hills, Meghalaya",
        node_id=node_id, farmer_id=farmer_id, holders_by_stage=holders,
        harvested_days_ago=4, target_stage_index=4,  # through Distributor
        readings_plan=[
            {"after_stage": 2, "temp": 10.1, "humidity": 72, "gas": 330, "hours_offset": 2},
            {"after_stage": 3, "temp": 15.8, "humidity": 74, "gas": 340, "hours_offset": 4},   # breach
            {"after_stage": 3, "temp": 16.4, "humidity": 76, "gas": 345, "hours_offset": 8},   # breach persists
            {"after_stage": 4, "temp": 14.2, "humidity": 71, "gas": 335, "hours_offset": 3},   # breach on arrival
        ],
    )

    # ---- Batch 3: Ginger — repeated tamper events at collection & warehouse, trust ~C
    make_batch(
        conn, chain_service, core, cur,
        produce="Ginger", variety="Nadia", qty=180, origin="Ri-Bhoi District, Meghalaya",
        node_id=node_id, farmer_id=farmer_id, holders_by_stage=holders,
        harvested_days_ago=3, target_stage_index=3,  # through Warehouse
        readings_plan=[
            {"after_stage": 1, "temp": 11.0, "humidity": 63, "gas": 290, "tamper": True, "hours_offset": 1},   # tamper at collection
            {"after_stage": 2, "temp": 11.4, "humidity": 65, "gas": 300, "tamper": True, "hours_offset": 2},   # tamper again in transit
            {"after_stage": 3, "temp": 10.9, "humidity": 64, "gas": 780, "tamper": True, "hours_offset": 3},   # tamper + gas spike at warehouse
        ],
    )

    conn.commit()
    print("  Seeded 3 demo batches: BAN-2026-001, PIN-2026-001, GIN-2026-001")
