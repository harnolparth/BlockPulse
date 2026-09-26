#!/usr/bin/env python3
"""
AgriTrace — ESP32 field-node simulator
----------------------------------------
Stands in for the physical node (ESP32 + SHT31 + MPU6050 + MQ-135 + NEO-6M +
DS3231 + SSD1306 OLED + microSD + reed switch + buzzer/LEDs + push buttons)
while you don't have the board plugged into this machine, or to generate a
realistic demo run in seconds. It speaks the *exact same* HTTP API the real
firmware in iot/esp32_firmware.ino uses (POST /api/iot/ingest and
/api/iot/sync with an X-Device-Key header) — so swapping this simulator for
the real board later is a zero-change swap on the backend side.

What it reproduces from the real node's behaviour:
  - periodic sensor reads (temperature, humidity, gas, GPS, shock/tamper)
  - the on-device OLED status readout (printed to the terminal here)
  - offline buffering to a local file when the network is "down" (simulated
    by --offline or randomly), then a bulk /api/iot/sync catch-up
  - LED/buzzer-equivalent console alerts when a reading crosses a threshold

Usage:
    python esp32_simulator.py                     # 12 readings, online
    python esp32_simulator.py --offline 4          # first 4 readings buffered, then synced
    python esp32_simulator.py --tamper-at 6        # force a tamper event on reading #6
    python esp32_simulator.py --server http://127.0.0.1:5000 --device-key demo-device-key-0001
"""

import argparse
import json
import os
import random
import time
import datetime
import urllib.request
import urllib.error

BUFFER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offline_buffer.ndjson")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds") + "Z"


def read_sensors(prev_temp, tamper=False):
    """Simulates SHT31 (temp/humidity), MQ-135 (gas), MPU6050 (shock/tamper),
    NEO-6M (GPS) — small random walk so a run looks like a real cold-chain trace."""
    temp = round(max(2.0, prev_temp + random.uniform(-0.6, 0.9)), 1)
    humidity = round(60 + random.uniform(-8, 8), 1)
    gas = round(300 + random.uniform(-40, 60), 0)
    shock = round(random.uniform(0.02, 0.35), 2) if not tamper else round(random.uniform(2.5, 4.2), 2)
    lat = 25.5788 + random.uniform(-0.01, 0.01)   # Ri-Bhoi, Meghalaya area
    lng = 91.8933 + random.uniform(-0.01, 0.01)
    return {
        "temperature_c": temp, "humidity_pct": humidity, "gas_ppm": gas,
        "shock_g": shock, "tamper": tamper, "lat": round(lat, 5), "lng": round(lng, 5),
        "battery_pct": round(random.uniform(72, 91)), "captured_at": now_iso(), "source": "esp32-simulator",
    }


def render_oled(batch_code, device_id, online, reading, records, synced, pending):
    """Mirrors the physical node's 128x64 OLED status screen, printed as text."""
    status = "ONLINE " if online else "OFFLINE"
    tamper_txt = "TAMPER!" if reading["tamper"] else "NORMAL"
    print("+" + "-" * 48 + "+")
    print(f"|{'BANANA TRACEABILITY':<30}{status:>17} |")
    print(f"| Batch: {batch_code:<16} Device: {device_id:<10}|")
    print("+" + "-" * 48 + "+")
    print(f"| T {reading['temperature_c']:>5.1f}C   H {reading['humidity_pct']:>4.0f}%   GAS {reading['gas_ppm']:>4.0f} ppm".ljust(49) + "|")
    print(f"| Shock: {tamper_txt:<10}   GPS: {reading['lat']},{reading['lng']}".ljust(49) + "|")
    print("+" + "-" * 48 + "+")
    print(f"| Records: {records:<5} Synced: {synced:<5} Pending: {pending:<5}".ljust(49) + "|")
    print("+" + "-" * 48 + "+\n")


def post_json(url, payload, device_key, timeout=5):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Device-Key": device_key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def buffer_locally(reading):
    with open(BUFFER_PATH, "a") as f:
        f.write(json.dumps(reading) + "\n")


def flush_buffer(server, device_key):
    if not os.path.exists(BUFFER_PATH) or os.path.getsize(BUFFER_PATH) == 0:
        return 0
    with open(BUFFER_PATH) as f:
        readings = [json.loads(line) for line in f if line.strip()]
    try:
        result = post_json(f"{server}/api/iot/sync", {"readings": readings}, device_key)
        os.remove(BUFFER_PATH)
        return result.get("stored", len(readings))
    except (urllib.error.URLError, ConnectionError) as exc:
        print(f"  [sync failed, will retry next cycle: {exc}]")
        return 0


def main():
    ap = argparse.ArgumentParser(description="AgriTrace ESP32 field-node simulator")
    ap.add_argument("--server", default="http://127.0.0.1:5000")
    ap.add_argument("--device-key", default="demo-device-key-0001")
    ap.add_argument("--device-id", default="HL-IOT-001")
    ap.add_argument("--batch", default="(auto-linked by node)")
    ap.add_argument("--readings", type=int, default=12)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between readings")
    ap.add_argument("--offline", type=int, default=0, help="buffer this many readings locally before syncing")
    ap.add_argument("--tamper-at", type=int, default=0, help="force a tamper spike on this reading number")
    args = ap.parse_args()

    print(f"AgriTrace field node {args.device_id} booting…")
    print(f"  Sensors online: SHT31, MPU6050, MQ-135, NEO-6M, DS3231, SSD1306, microSD")
    print(f"  Server: {args.server}   (device key: {args.device_key[:8]}…)\n")
    time.sleep(0.4)

    temp = 8.5
    records, synced, pending = 0, 0, 0

    for i in range(1, args.readings + 1):
        tamper = (i == args.tamper_at)
        reading = read_sensors(temp, tamper=tamper)
        temp = reading["temperature_c"]
        records += 1
        is_offline_cycle = i <= args.offline

        if is_offline_cycle:
            buffer_locally(reading)
            pending += 1
            render_oled(args.batch, args.device_id, False, reading, records, synced, pending)
            if reading["tamper"]:
                print("  [BUZZER + RED LED] tamper detected — reed switch / MPU6050 shock threshold exceeded (buffered offline)\n")
            elif reading["temperature_c"] > 12:
                print("  [YELLOW LED] temperature above 12°C cold-chain limit (buffered offline)\n")
        else:
            try:
                post_json(f"{args.server}/api/iot/ingest", reading, args.device_key)
                # catch up anything buffered while we were "offline"
                if pending:
                    flushed = flush_buffer(args.server, args.device_key)
                    synced += flushed
                    pending -= flushed
                synced += 1
                render_oled(args.batch, args.device_id, True, reading, records, synced, pending)
                if reading["tamper"]:
                    print("  [BUZZER + RED LED] tamper detected — reed switch / MPU6050 shock threshold exceeded\n")
                elif reading["temperature_c"] > 12:
                    print("  [YELLOW LED] temperature above 12°C cold-chain limit\n")
                else:
                    print("  [GREEN LED] all readings within range\n")
            except (urllib.error.URLError, ConnectionError) as exc:
                print(f"  [connection failed — buffering to microSD instead: {exc}]")
                buffer_locally(reading)
                pending += 1
                render_oled(args.batch, args.device_id, False, reading, records, synced, pending)

        time.sleep(args.interval)

    if pending:
        flushed = flush_buffer(args.server, args.device_key)
        print(f"Final sync: {flushed} buffered reading(s) uploaded.")

    print("Run complete. Open the batch in AgriTrace to see these readings on its timeline.")


if __name__ == "__main__":
    main()
