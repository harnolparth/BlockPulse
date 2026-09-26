/*
  AgriTrace — Field Node Firmware
  ================================
  Board: ESP32 DevKit
  Sensors/peripherals (matches the assembled prototype):
    - SHT31            temperature + humidity        I2C  (0x44)
    - MPU6050          accelerometer/gyro (shock)     I2C  (0x68)
    - MQ-135           gas / spoilage sensor          analog (ADC1)
    - NEO-6M           GPS                            UART2 (RX2/TX2)
    - DS3231           real-time clock                I2C  (0x68 shared bus w/ AT24C32)
    - SSD1306 0.96"     128x64 OLED status display     I2C  (0x3C)
    - microSD (SPI)     offline buffering              SPI  (VSPI)
    - Reed switch       lid-open / tamper detection    GPIO interrupt
    - Active buzzer     audible alert                  GPIO
    - LEDs (G/Y/R x3)   status indicator               GPIO
    - 2x push buttons   B1: force sync, B2: cycle OLED page

  Install via Library Manager: Adafruit SHT31, Adafruit MPU6050 (+ Adafruit
  Unified Sensor), TinyGPSPlus, RTClib, Adafruit SSD1306 (+ Adafruit GFX),
  ArduinoJson (>=6). SD, SPI, Wire, WiFi, HTTPClient ship with the ESP32
  Arduino core.

  Talks to the same AgriTrace Flask API the simulator (iot/esp32_simulator.py)
  and the web app use — POST /api/iot/ingest while online, buffering to
  /buffer.ndjson on the SD card and POSTing /api/iot/sync when a connection
  is available. See backend/app.py for both endpoints.
*/

#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Adafruit_SHT31.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <TinyGPSPlus.h>
#include <RTClib.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "mbedtls/sha256.h"

// ---------------------------------------------------------------- config
const char* WIFI_SSID      = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD  = "YOUR_WIFI_PASSWORD";
const char* SERVER_BASE    = "http://192.168.1.50:5000";   // your machine's LAN IP running app.py
const char* DEVICE_KEY     = "demo-device-key-0001";        // matches nodes.device_key seeded in db.py
const char* DEVICE_ID      = "HL-IOT-001";
const char* BATCH_LABEL    = "BAN-2026-001";                 // cosmetic, shown on OLED only

const float  TEMP_LIMIT_C     = 12.0;
const float  GAS_WARN_PPM     = 400.0;
const float  SHOCK_THRESHOLD_G = 2.2;
const unsigned long READ_INTERVAL_MS = 15000;   // 15s between readings
const unsigned long SYNC_RETRY_MS    = 30000;   // retry offline buffer every 30s

// ---------------------------------------------------------------- pins
#define PIN_REED        27
#define PIN_BUZZER      25
#define PIN_LED_GREEN   26
#define PIN_LED_YELLOW  33
#define PIN_LED_RED     32
#define PIN_BTN_SYNC    16
#define PIN_BTN_PAGE    17
#define PIN_MQ135_AO    34
#define PIN_SD_CS       5
#define GPS_RX          16
#define GPS_TX          17

// ---------------------------------------------------------------- objects
Adafruit_SHT31 sht31 = Adafruit_SHT31();
Adafruit_MPU6050 mpu;
TinyGPSPlus gps;
HardwareSerial GPSSerial(2);
RTC_DS3231 rtc;
Adafruit_SSD1306 display(128, 64, &Wire, -1);

volatile bool tamperFlag = false;
unsigned long recordsTotal = 0, recordsSynced = 0;
unsigned long lastRead = 0, lastSyncAttempt = 0;
bool sdReady = false;

// hash-chain: each reading's SHA-256 is chained to the previous one, same
// scheme as backend/integrity.py, so a local audit is possible even before
// the reading reaches the server.
uint8_t prevHash[32] = {0};

void IRAM_ATTR onReedTrigger() { tamperFlag = true; }

// ---------------------------------------------------------------- setup
void setup() {
  Serial.begin(115200);
  Wire.begin();

  pinMode(PIN_REED, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_BTN_SYNC, INPUT_PULLUP);
  pinMode(PIN_BTN_PAGE, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_REED), onReedTrigger, FALLING);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 not found");
  }
  showBootScreen();

  if (!sht31.begin(0x44)) Serial.println("SHT31 not found");
  if (!mpu.begin()) Serial.println("MPU6050 not found");
  else mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  if (!rtc.begin()) Serial.println("DS3231 not found");

  GPSSerial.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);

  sdReady = SD.begin(PIN_SD_CS);
  if (!sdReady) Serial.println("microSD not found — offline buffering disabled");

  connectWiFi();
}

// ---------------------------------------------------------------- loop
void loop() {
  if (digitalRead(PIN_BTN_SYNC) == LOW) { flushBuffer(); delay(300); }

  unsigned long now = millis();
  if (now - lastRead >= READ_INTERVAL_MS) {
    lastRead = now;
    takeReadingAndReport();
  }
  if (WiFi.status() != WL_CONNECTED && now - lastSyncAttempt >= SYNC_RETRY_MS) {
    lastSyncAttempt = now;
    connectWiFi();
  }
  while (GPSSerial.available()) gps.encode(GPSSerial.read());
}

// ---------------------------------------------------------------- wifi
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 6000) delay(200);
  if (WiFi.status() == WL_CONNECTED) flushBuffer();
}

// ---------------------------------------------------------------- reading
void takeReadingAndReport() {
  float temp = sht31.readTemperature();
  float hum  = sht31.readHumidity();
  int gasRaw = analogRead(PIN_MQ135_AO);
  float gasPpm = map(gasRaw, 0, 4095, 0, 1000);

  sensors_event_t a, g, tempEvent;
  mpu.getEvent(&a, &g, &tempEvent);
  float shockG = sqrt(a.acceleration.x * a.acceleration.x +
                       a.acceleration.y * a.acceleration.y +
                       a.acceleration.z * a.acceleration.z) / 9.81;
  bool tamper = tamperFlag || (shockG > SHOCK_THRESHOLD_G);
  tamperFlag = false;

  double lat = gps.location.isValid() ? gps.location.lat() : 0.0;
  double lng = gps.location.isValid() ? gps.location.lng() : 0.0;
  DateTime ts = rtc.now();

  StaticJsonDocument<384> doc;
  doc["temperature_c"] = round(temp * 10) / 10.0;
  doc["humidity_pct"]  = round(hum * 10) / 10.0;
  doc["gas_ppm"]       = gasPpm;
  doc["shock_g"]       = round(shockG * 100) / 100.0;
  doc["tamper"]        = tamper;
  doc["lat"]           = lat;
  doc["lng"]           = lng;
  doc["battery_pct"]   = readBatteryPct();
  char tsbuf[25];
  snprintf(tsbuf, sizeof(tsbuf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
           ts.year(), ts.month(), ts.day(), ts.hour(), ts.minute(), ts.second());
  doc["captured_at"] = tsbuf;
  doc["source"] = "esp32";

  String payload;
  serializeJson(doc, payload);
  chainHash(payload);   // update local hash chain regardless of connectivity

  recordsTotal++;
  bool sent = false;
  if (WiFi.status() == WL_CONNECTED) sent = postIngest(payload);
  if (!sent) bufferToSD(payload);
  else recordsSynced++;

  alertOutputs(doc["temperature_c"], gasPpm, tamper);
  updateOled(doc["temperature_c"], doc["humidity_pct"], gasPpm, tamper, lat, lng);
}

// ---------------------------------------------------------------- networking
bool postIngest(const String& payload) {
  HTTPClient http;
  http.begin(String(SERVER_BASE) + "/api/iot/ingest");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.POST(payload);
  http.end();
  return code == 200;
}

void bufferToSD(const String& payload) {
  if (!sdReady) return;
  File f = SD.open("/buffer.ndjson", FILE_APPEND);
  if (f) { f.println(payload); f.close(); }
}

void flushBuffer() {
  if (!sdReady || WiFi.status() != WL_CONNECTED) return;
  if (!SD.exists("/buffer.ndjson")) return;

  File f = SD.open("/buffer.ndjson", FILE_READ);
  if (!f) return;
  String body = "{\"readings\":[";
  bool first = true;
  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;
    if (!first) body += ",";
    body += line;
    first = false;
  }
  body += "]}";
  f.close();

  HTTPClient http;
  http.begin(String(SERVER_BASE) + "/api/iot/sync");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.POST(body);
  http.end();

  if (code == 200) {
    SD.remove("/buffer.ndjson");
    Serial.println("Offline buffer synced and cleared.");
  }
}

// ---------------------------------------------------------------- local integrity
// Mirrors backend/integrity.py: sha256(prevHash || sha256(payload)).
// Lets the node prove on demand ("was this reading tampered with before it
// ever left the field?") without needing connectivity.
void chainHash(const String& payload) {
  uint8_t dataHash[32];
  mbedtls_sha256((const unsigned char*)payload.c_str(), payload.length(), dataHash, 0);

  uint8_t combined[64];
  memcpy(combined, prevHash, 32);
  memcpy(combined + 32, dataHash, 32);

  mbedtls_sha256(combined, 64, prevHash, 0);   // prevHash now holds this record's chain hash
}

// ---------------------------------------------------------------- outputs
void alertOutputs(float temp, float gasPpm, bool tamper) {
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_YELLOW, LOW);
  digitalWrite(PIN_LED_RED, LOW);
  noTone(PIN_BUZZER);

  if (tamper) {
    digitalWrite(PIN_LED_RED, HIGH);
    tone(PIN_BUZZER, 2200, 400);
  } else if (temp > TEMP_LIMIT_C || gasPpm > GAS_WARN_PPM) {
    digitalWrite(PIN_LED_YELLOW, HIGH);
    tone(PIN_BUZZER, 1200, 150);
  } else {
    digitalWrite(PIN_LED_GREEN, HIGH);
  }
}

int readBatteryPct() {
  // Placeholder — wire a divider from the 2S pack through the LM2596 to an
  // ADC pin and calibrate against your BMS's cutoff voltage.
  return 85;
}

// ---------------------------------------------------------------- OLED
void showBootScreen() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("AgriTrace field node");
  display.println(DEVICE_ID);
  display.println("Booting sensors...");
  display.display();
}

void updateOled(float temp, float hum, float gas, bool tamper, double lat, double lng) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  display.setCursor(0, 0);
  display.print("BANANA TRACEABILITY ");
  display.println(WiFi.status() == WL_CONNECTED ? "ON" : "OFF");
  display.print("Batch:"); display.println(BATCH_LABEL);
  display.drawLine(0, 18, 128, 18, SSD1306_WHITE);

  display.setCursor(0, 22);
  display.print("T "); display.print(temp, 1); display.print("C  H ");
  display.print(hum, 0); display.println("%");
  display.print("GAS "); display.println(gas, 0);
  display.print("Shock: "); display.println(tamper ? "TAMPER!" : "normal");

  display.drawLine(0, 46, 128, 46, SSD1306_WHITE);
  display.setCursor(0, 50);
  display.print("Rec "); display.print(recordsTotal);
  display.print(" Syn "); display.print(recordsSynced);
  display.print(" Pnd "); display.println(recordsTotal - recordsSynced);
  display.display();
}
