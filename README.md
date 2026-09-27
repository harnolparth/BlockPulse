🌾 Agri-Trace — Farm-to-Fork Traceability Platform

Developed by BlockPulse

«Every crate, tracked from soil to shelf.»

Agri-Trace is a low-cost IoT and blockchain-assisted agricultural supply-chain traceability platform designed to provide end-to-end visibility of agricultural produce from the farm to the consumer.

The platform records every important stage of a batch — harvesting, collection, transportation, storage, distribution, retail, and sale — while combining IoT sensor data, cryptographic hash chaining, tamper detection, alerts, and blockchain anchoring to create a transparent and verifiable supply-chain history.

---

🚀 Live Demo

🌐 Live Website:
https://blockpulse2026.onrender.com

💻 GitHub Repository:
https://github.com/harnolparth/BlockPulse

---

🎯 Problem Statement

Agricultural supply chains often involve multiple intermediaries between farmers and consumers.

This can make it difficult to answer important questions such as:

- Where was the produce grown?
- When was it harvested?
- Who handled it at each stage?
- Was the produce transported and stored under safe conditions?
- Was the cold chain maintained?
- Was the shipment exposed to tampering or abnormal handling?
- Can the recorded history be trusted?
- Can consumers verify the journey of the product?

Traditional supply-chain systems may rely heavily on centralized records, making transparency and independent verification difficult.

Agri-Trace addresses this problem by creating a digital, tamper-evident journey for every produce batch.

---

💡 Our Solution

Agri-Trace creates a digital identity for every agricultural batch.

Each batch receives a unique batch code and is tracked throughout its journey:

🌱 FARM
   ↓
📦 COLLECTION CENTRE
   ↓
🚚 TRANSPORT
   ↓
🏭 WAREHOUSE / RIPENING
   ↓
🚛 DISTRIBUTOR
   ↓
🏪 RETAIL
   ↓
👤 CONSUMER

At each stage, the platform can record:

- Location
- Timestamp
- Handler
- Supply-chain event
- Temperature
- Humidity
- Gas readings
- Shock
- Tamper status
- GPS coordinates
- Additional notes

The resulting history can be verified through the platform's integrity and blockchain mechanisms.

---

✨ Key Features

1. 📦 End-to-End Batch Tracking

Every produce batch receives a unique identifier such as:

BAN-2026-001

The batch can then be followed through every supply-chain stage.

The backend defines the complete lifecycle from Farm → Collection → Transport → Warehouse → Distributor → Retail → Consumer.

---

2. 🌡️ IoT Environmental Monitoring

Agri-Trace is designed around an IoT field node capable of collecting environmental and handling information.

The planned hardware stack includes:

- ESP32
- SHT31 Temperature & Humidity Sensor
- MPU6050 Accelerometer + Gyroscope
- MQ-135 Gas Sensor
- NEO-6M GPS
- DS3231 RTC
- SSD1306 OLED
- MicroSD card
- Reed switch
- Buzzer
- LEDs
- Battery system

The backend supports ingestion of:

Temperature
Humidity
Gas
Ethanol
Shock
Tamper
Latitude
Longitude
Battery
Timestamp

The IoT API accepts readings from an ESP32 node using a device key.

---

3. 🔐 Tamper-Evident Records

Supply-chain events are protected using cryptographic hash chaining.

Each event contains information such as:

Previous Hash
        ↓
Event Data
        ↓
Data Hash
        ↓
Chain Hash
        ↓
Next Event

This makes unauthorized modification of historical records detectable.

The SQLite database also contains database-level immutability triggers that prevent modification or deletion of hash-chained events, sensor readings, and blockchain anchors after they are recorded.

---

4. ⛓️ Blockchain Anchoring

Important supply-chain records can be anchored through a blockchain service.

The architecture supports two modes:

Simulated Blockchain

The default configuration uses a local append-only ledger.

This allows the complete project to run without:

- Cryptocurrency
- Gas fees
- Blockchain credentials
- External blockchain infrastructure

The simulated chain generates transaction hashes and block information for demonstration purposes.

Polygon Amoy Testnet

The system also supports optional real blockchain anchoring using:

Polygon Amoy Testnet

When properly configured, the backend can anchor record hashes through the "AgriTraceRegistry" smart contract.

The smart contract stores the hash of important lifecycle events rather than storing raw sensor or personal data on-chain.

---

🧱 System Architecture

                   ┌───────────────────────┐
                   │       IoT Node        │
                   │       ESP32           │
                   │                       │
                   │ SHT31   MPU6050       │
                   │ MQ-135  GPS            │
                   │ RTC     MicroSD        │
                   └───────────┬───────────┘
                               │
                               │ HTTPS / HTTP
                               ▼
                   ┌───────────────────────┐
                   │     Flask Backend     │
                   │                       │
                   │ Authentication        │
                   │ Batch Management      │
                   │ Event Management      │
                   │ IoT API               │
                   │ Alert Engine          │
                   └───────────┬───────────┘
                               │
                 ┌─────────────┼──────────────┐
                 ▼             ▼              ▼
        ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
        │   SQLite    │ │  Integrity  │ │ Blockchain  │
        │  Database   │ │   Service   │ │   Service   │
        └─────────────┘ └─────────────┘ └──────┬──────┘
                                               │
                                  ┌────────────┴────────────┐
                                  │                         │
                                  ▼                         ▼
                         Simulated Chain          Polygon Amoy
                                                    Testnet

The backend architecture directly separates the Flask application, database, integrity service, and blockchain service.

---

👥 User Roles

Agri-Trace supports role-based access for different participants in the supply chain.

Role| Main Responsibility
👨‍🌾 Farmer| Register agricultural batches
🏭 Warehouse| Handle storage and warehouse transitions
🚚 Distributor| Manage distribution and retail stages
👨‍💼 Admin| Platform administration and monitoring
👤 Consumer| Verify product history

The backend implements role-based permissions for supply-chain stage transitions.

---

🔄 Supply-Chain Workflow

Step 1 — Batch Registration

The farmer registers a produce batch by entering information such as:

- Produce type
- Variety
- Quantity
- Origin
- Harvest date
- IoT node

A unique batch code and genesis hash are created.

---

Step 2 — Harvest Record

The initial harvest event becomes the first event in the batch's history.

Example:

Batch: BAN-2026-001
Event: HARVEST
Location: Farm
Status: Farm

---

Step 3 — Collection

The batch moves to the collection centre.

A new event is added to the chain.

HARVEST
   ↓
COLLECTION

---

Step 4 — Transportation

The batch enters transportation.

IoT readings can be associated with the shipment.

For example:

Temperature: 8.7°C
Humidity: 64%
Shock: 0.15g
GPS: Recorded
Tamper: Normal

---

Step 5 — Storage

At the warehouse/ripening facility, the system continues tracking the batch and its environmental conditions.

---

Step 6 — Distribution

The distributor receives the batch and records the next supply-chain event.

---

Step 7 — Retail

The batch reaches the retail stage.

---

Step 8 — Consumer Verification

Consumers can access a public verification page without requiring an account.

The verification page provides the digital history of the batch and its associated verification information.

---

🚨 Real-Time Alerts

Agri-Trace can detect abnormal sensor conditions and generate alerts.

For example:

Temperature > Safe Limit
        ↓
Alert Generated
        ↓
Batch Marked for Attention
        ↓
Supply-chain operator can investigate

The current backend uses a 12°C temperature threshold for the cold-chain monitoring logic.

Tamper events can also be detected through shock/tamper information from the IoT node.

---

📊 Analytics Dashboard

The platform provides analytics related to:

- Total batches
- Batch status
- Temperature trends
- Humidity trends
- Alerts
- Blockchain anchors
- Average trust score
- Trust-grade distribution
- Supply-chain stage durations

The analytics API also calculates stage-transition durations to help identify delays in the supply chain.

---

🔍 Public Verification

One of the important features of Agri-Trace is that consumers do not need an account to verify a batch.

The public verification flow is designed around a digital product passport.

             PRODUCT
                │
                ▼
          Batch / QR Code
                │
                ▼
       Public Verification
                │
       ┌────────┴────────┐
       ▼                 ▼
   Batch Details     Journey History
       │                 │
       └────────┬────────┘
                ▼
        Integrity Status

The backend exposes a public "/verify/<batch_code>" route and public batch verification APIs.

---

📡 IoT Simulator

The repository includes an ESP32 field-node simulator.

It reproduces the behaviour of the planned physical IoT node and can generate:

- Temperature
- Humidity
- Gas readings
- GPS coordinates
- Shock
- Tamper events
- Battery percentage
- Offline buffering
- Synchronization

The simulator communicates with the same "/api/iot/ingest" and "/api/iot/sync" endpoints intended for the physical ESP32 device.

Example

python iot/esp32_simulator.py

Run an offline-buffer demonstration:

python iot/esp32_simulator.py --offline 4

Generate a tamper event:

python iot/esp32_simulator.py --tamper-at 6

Specify a server:

python iot/esp32_simulator.py \
  --server http://127.0.0.1:5000 \
  --device-key demo-device-key-0001

---

🛠️ Technology Stack

Frontend

- HTML5
- CSS3
- JavaScript

Backend

- Python
- Flask 3.1.3
- PyJWT

Database

- SQLite

The database layer is intentionally designed using portable SQL so that it can later be migrated to PostgreSQL.

IoT

- ESP32
- SHT31
- MPU6050
- MQ-135
- NEO-6M
- DS3231
- SSD1306 OLED
- MicroSD

Blockchain

- Solidity
- Polygon Amoy Testnet
- Web3.py
- SHA-256 hashing

Deployment

- Render

The backend requirements include Flask, PyJWT, optional "requests", and Gunicorn.

---

📁 Project Structure

BlockPulse/
│
├── backend/
│   ├── app.py
│   ├── auth.py
│   ├── blockchain.py
│   ├── core.py
│   ├── db.py
│   ├── integrity.py
│   ├── seed_demo.py
│   ├── requirements.txt
│   └── templates/
│
├── contracts/
│   └── AgriTraceRegistry.sol
│
├── iot/
│   ├── esp32_simulator.py
│   └── esp32_firmware.ino
│
├── static/
│   ├── css/
│   ├── js/
│   └── assets/
│
└── README.md

---

⚙️ Installation

1. Clone the repository

git clone https://github.com/harnolparth/BlockPulse.git

Move into the project:

cd BlockPulse

---

2. Create a virtual environment

Windows

python -m venv venv
venv\Scripts\activate

Linux / macOS

python3 -m venv venv
source venv/bin/activate

---

3. Install dependencies

pip install -r backend/requirements.txt

The default application only requires Flask and PyJWT for the core system; "requests" is used for HTTP-based IoT simulation and Web3 is optional for real Polygon anchoring.

---

4. Run the application

cd backend
python app.py

The application runs on:

http://127.0.0.1:5000

---

🔑 Demo Accounts

The project includes seeded demonstration accounts.

Username| Password| Role
"admin"| "admin123"| Administrator
"farmer1"| "farmer123"| Farmer
"warehouse1"| "warehouse123"| Warehouse
"distributor1"| "distributor123"| Distributor

These accounts are created by the application's database seed process.

«Note: These credentials are for the demonstration environment. Do not use them in a production deployment.»

---

🔗 API Endpoints

Authentication

POST /api/auth/login

Authenticates a user and returns an authentication token.

---

Get Batches

GET /api/batches

Returns authenticated batch information.

---

Get Batch Details

GET /api/batches/<batch_code>

Returns batch information including:

- Events
- Sensor readings
- Alerts
- Blockchain anchors
- Trust information

---

Verify Batch

GET /api/batches/<batch_code>/verify

Recomputes the integrity chain and returns verification information.

Example response structure:

{
  "batch_code": "BAN-2026-001",
  "chain_valid": true,
  "trust_score": 100,
  "grade": "A"
}

---

IoT Data Ingestion

POST /api/iot/ingest

Used by the ESP32 field node to submit a live sensor reading.

The request uses:

X-Device-Key: <device-key>

---

Offline IoT Synchronization

POST /api/iot/sync

Used to upload readings that were buffered while the IoT node was offline.

---

Analytics

GET /api/analytics/summary

Provides supply-chain analytics and sensor data summaries.

The implemented API includes batch counts, status counts, sensor series, alerts, blockchain anchors, trust scores, and stage-duration information.

---

⛓️ Smart Contract

The repository includes:

contracts/AgriTraceRegistry.sol

The smart contract is designed to store selected lifecycle-event hashes rather than raw batch, sensor, or personal information.

Its main anchoring function is:

anchorRecord(
    string calldata batchCode,
    string calldata eventType,
    bytes32 dataHash
)

The contract also supports authorized anchor addresses.

---

🌐 Polygon Amoy Configuration

The default application runs with the simulated blockchain.

For real Polygon Amoy anchoring, configure:

POLYGON_RPC_URL
POLYGON_PRIVATE_KEY
POLYGON_CONTRACT_ADDRESS

Example:

POLYGON_RPC_URL=https://rpc-amoy.polygon.technology
POLYGON_PRIVATE_KEY=<YOUR_TESTNET_PRIVATE_KEY>
POLYGON_CONTRACT_ADDRESS=<DEPLOYED_CONTRACT_ADDRESS>

The backend automatically selects the Polygon implementation when the required configuration is available; otherwise, it safely falls back to the simulated chain.

«⚠️ Never commit a real private key, API key, device secret, or production credential to GitHub.»

---

🔐 Security & Integrity Model

Agri-Trace uses multiple layers of protection:

Layer 1 — Authentication

Role-based login controls access to protected portals.

Layer 2 — Device Authentication

IoT nodes authenticate using device keys.

Layer 3 — Hash Chaining

Supply-chain events are linked using cryptographic hashes.

Layer 4 — Database Immutability

Database triggers prevent modification and deletion of historical events, sensor readings, and blockchain anchors.

Layer 5 — Blockchain Anchoring

Selected hashes can be anchored to a blockchain network for an additional independent verification layer.

This creates a layered architecture:

IoT Data
   ↓
Application Record
   ↓
SHA-256 Integrity
   ↓
Hash Chain
   ↓
Blockchain Anchor
   ↓
Public Verification

---

🧪 Demonstration Flow

For a hackathon/demo presentation, the recommended flow is:

1. Open Agri-Trace
        ↓
2. Login as Farmer
        ↓
3. Register Produce Batch
        ↓
4. View Batch Timeline
        ↓
5. Run IoT Simulator
        ↓
6. Generate Sensor Readings
        ↓
7. Demonstrate Temperature/Tamper Alert
        ↓
8. Advance Batch Through Supply Chain
        ↓
9. View Integrity / Blockchain Record
        ↓
10. Open Public Verification
        ↓
11. Show Complete Farm-to-Fork Journey

---

🏆 What Makes Agri-Trace Different?

Agri-Trace combines several technologies into one traceability workflow:

             AGRI-TRACE
                 │
     ┌───────────┼───────────┐
     │           │           │
     ▼           ▼           ▼
    IoT       Integrity   Blockchain
     │           │           │
     ▼           ▼           ▼
 Sensors      Hash Chain   Anchoring
     │           │           │
     └───────────┼───────────┘
                 ▼
        Supply Chain Trust
                 │
                 ▼
          Consumer Verification

Instead of treating IoT, blockchain, and supply-chain tracking as separate systems, Agri-Trace connects them into a single traceability workflow.

---

🌱 Future Scope

The platform can be extended with:

- 📱 Dedicated mobile application
- 🔳 QR-based consumer verification
- ⛓️ Full production blockchain deployment
- 🌐 Decentralized identity for supply-chain participants
- 📡 LoRaWAN / NB-IoT connectivity
- 🔋 Solar-powered IoT nodes
- 🛰️ Improved GPS tracking
- 🤖 AI-based spoilage prediction
- 📈 Advanced supply-chain analytics
- 🌾 Crop-specific sensor configurations
- 🔔 SMS / WhatsApp alert integration
- 🏛️ Government and certification integration
- 🌍 Multi-region supply-chain deployment
- ☁️ Scalable cloud database infrastructure

---

🎓 Project Context

Project Name: Agri-Trace
Team: BlockPulse
Domain: Agriculture + IoT + Blockchain + Supply Chain
Platform: Web Application
Deployment: Render
Blockchain: Polygon Amoy compatible
IoT: ESP32-based field node

---

👨‍💻 Team BlockPulse

Built as a technology solution for improving transparency and traceability in agricultural supply chains.

Core Technologies

Python
Flask
HTML
CSS
JavaScript
SQLite
IoT
ESP32
Cryptography
Solidity
Polygon

---

📜 License

This project is intended for educational, hackathon, research, and prototype purposes.

The smart contract in this repository is released under the MIT License as indicated in the Solidity source.

---

⭐ Support the Project

If you find Agri-Trace interesting:

⭐ Star the repository
🍴 Fork the project
🐛 Report issues
💡 Suggest improvements
🤝 Contribute to the project

---

🔗 Project Links

🌐 Live Demo:
https://blockpulse2026.onrender.com

💻 Source Code:
https://github.com/harnolparth/BlockPulse

---

🌾 Agri-Trace

From Soil → Supply Chain → Shelf → Consumer

Built by BlockPulse
