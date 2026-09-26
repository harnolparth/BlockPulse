"""
AgriTrace — Data layer
-----------------------
Ships with SQLite so the whole system runs with zero external services
(no Postgres server to install, no internet needed). The schema below is
written in plain, portable SQL (explicit types, no SQLite-only tricks) so
moving to PostgreSQL in production is a drop-in swap — see README.md
"Moving to PostgreSQL" for the one-file change required.
"""

import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agritrace.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','farmer','warehouse','distributor','consumer')),
    full_name TEXT NOT NULL,
    organisation TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_code TEXT UNIQUE NOT NULL,
    device_key TEXT UNIQUE NOT NULL,
    label TEXT NOT NULL,
    hardware TEXT DEFAULT 'ESP32 + SHT31 + MPU6050 + MQ135 + NEO-6M + DS3231',
    owner_id INTEGER REFERENCES users(id),
    last_seen TEXT,
    battery_pct INTEGER DEFAULT 100,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_code TEXT UNIQUE NOT NULL,
    produce_type TEXT NOT NULL,
    variety TEXT,
    quantity_kg REAL NOT NULL,
    farmer_id INTEGER REFERENCES users(id),
    origin_location TEXT NOT NULL,
    origin_lat REAL,
    origin_lng REAL,
    node_id INTEGER REFERENCES nodes(id),
    harvest_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'farm',
    current_holder_id INTEGER REFERENCES users(id),
    genesis_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    event_type TEXT NOT NULL,
    actor_id INTEGER REFERENCES users(id),
    location TEXT,
    lat REAL,
    lng REAL,
    notes TEXT,
    reading_id INTEGER,
    prev_hash TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    chain_hash TEXT NOT NULL,
    anchored INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER REFERENCES nodes(id),
    batch_id INTEGER REFERENCES batches(id),
    temperature_c REAL,
    humidity_pct REAL,
    gas_ppm REAL,
    ethanol_ppm REAL,
    shock_g REAL,
    tamper INTEGER DEFAULT 0,
    lat REAL,
    lng REAL,
    reading_hash TEXT NOT NULL,
    prev_reading_hash TEXT,
    captured_at TEXT NOT NULL,
    synced_at TEXT,
    source TEXT DEFAULT 'esp32'
);

CREATE TABLE IF NOT EXISTS blockchain_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    event_id INTEGER REFERENCES events(id),
    data_hash TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    block_number INTEGER,
    network TEXT NOT NULL,
    mode TEXT NOT NULL,
    explorer_url TEXT,
    anchored_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER REFERENCES batches(id),
    node_id INTEGER REFERENCES nodes(id),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    resolved INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Immutability triggers.
--
-- These are enforced by SQLite itself, not by application code — they
-- fire no matter what talks to the database (the Flask app, the sqlite3
-- CLI, a GUI DB browser, a rogue script). Once a hash-chained record or
-- a blockchain anchor is written, nothing can rewrite or erase it; the
-- write is rejected with a SQL error. This is what actually backs the
-- "tamper-evident" claim, rather than just an app-layer convention.
-- ---------------------------------------------------------------------

-- Events: the "anchored" flag is the only column allowed to change after
-- insert (create_event() sets it once anchoring succeeds). Any attempt to
-- alter the event's content or its hash-chain fields is rejected outright.
CREATE TRIGGER IF NOT EXISTS trg_events_immutable_update
BEFORE UPDATE ON events
WHEN NEW.batch_id      != OLD.batch_id      OR NEW.event_type != OLD.event_type
  OR NEW.actor_id       IS NOT OLD.actor_id  OR NEW.location   IS NOT OLD.location
  OR NEW.notes          IS NOT OLD.notes     OR NEW.reading_id IS NOT OLD.reading_id
  OR NEW.prev_hash      != OLD.prev_hash     OR NEW.data_hash  != OLD.data_hash
  OR NEW.chain_hash     != OLD.chain_hash    OR NEW.created_at != OLD.created_at
BEGIN
  SELECT RAISE(ABORT, 'AgriTrace: hash-chained events are immutable — only the anchored flag may be set');
END;

CREATE TRIGGER IF NOT EXISTS trg_events_immutable_delete
BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'AgriTrace: hash-chained events cannot be deleted');
END;

-- Sensor readings: never updated or deleted after insert, anywhere in the app.
CREATE TRIGGER IF NOT EXISTS trg_readings_immutable_update
BEFORE UPDATE ON sensor_readings
BEGIN
  SELECT RAISE(ABORT, 'AgriTrace: sensor readings are immutable once recorded');
END;

CREATE TRIGGER IF NOT EXISTS trg_readings_immutable_delete
BEFORE DELETE ON sensor_readings
BEGIN
  SELECT RAISE(ABORT, 'AgriTrace: sensor readings cannot be deleted');
END;

-- Blockchain anchors: a tx hash / data hash / block number, once written,
-- can never be edited or removed — this is the "no one can change an
-- anchored hash address" guarantee.
CREATE TRIGGER IF NOT EXISTS trg_anchors_immutable_update
BEFORE UPDATE ON blockchain_anchors
BEGIN
  SELECT RAISE(ABORT, 'AgriTrace: blockchain anchors are immutable once written');
END;

CREATE TRIGGER IF NOT EXISTS trg_anchors_immutable_delete
BEFORE DELETE ON blockchain_anchors
BEGIN
  SELECT RAISE(ABORT, 'AgriTrace: blockchain anchors cannot be deleted');
END;
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds") + "Z"


def init_db(seed=True):
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    if fresh and seed:
        _seed(conn)
    conn.close()


def _seed(conn):
    from auth import hash_password

    users = [
        ("admin", "admin123", "admin", "System Administrator", "AgriTrace Platform"),
        ("farmer1", "farmer123", "farmer", "Farmer Account", "Ri-Bhoi Farm Cooperative, Meghalaya"),
        ("warehouse1", "warehouse123", "warehouse", "Warehouse Operator", "NE Regional Cold Storage Facility"),
        ("distributor1", "distributor123", "distributor", "Distributor & Retail Partner", "Meghalaya Distribution Network"),
    ]
    cur = conn.cursor()
    ids = {}
    for username, pw, role, name, org in users:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name, organisation, created_at) VALUES (?,?,?,?,?,?)",
            (username, hash_password(pw), role, name, org, now()),
        )
        ids[username] = cur.lastrowid

    cur.execute(
        "INSERT INTO nodes (node_code, device_key, label, owner_id, last_seen, battery_pct, status) VALUES (?,?,?,?,?,?,?)",
        ("HL-IOT-001", "demo-device-key-0001", "Field node — Plot 4, Ri-Bhoi, Meghalaya", ids["farmer1"], now(), 87, "active"),
    )
    conn.commit()
    return ids

