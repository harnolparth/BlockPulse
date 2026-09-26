"""
AgriTrace — Blockchain Service
--------------------------------
Abstraction over "anchor this hash somewhere immutable". Two interchangeable
backends behind the same interface, matching the architecture:

    Backend Integrity Service -> Blockchain Service -> Polygon Smart Contract
                                                      -> Polygon Network
                                                      -> PolygonScan

1. SimulatedChain (default, zero setup, fully offline):
   Appends anchors to an append-only local ledger file
   (backend/simulated_chain.jsonl) and produces a deterministic,
   realistic-looking tx hash / block number, so every demo flow — anchor,
   verify, "view on explorer" — works end-to-end without any internet
   access or gas fees. This is what runs out of the box.

2. PolygonChain (optional, real testnet anchoring):
   If web3.py is installed AND the three env vars below are set, batches
   are genuinely anchored on the Polygon Amoy testnet via the
   AgriTraceRegistry contract in /contracts/AgriTraceRegistry.sol, and the
   returned explorer_url is a real, working PolygonScan link.

     POLYGON_RPC_URL   e.g. https://rpc-amoy.polygon.technology
     POLYGON_PRIVATE_KEY   funded testnet account private key
     POLYGON_CONTRACT_ADDRESS   deployed AgriTraceRegistry address

Switching modes never changes the calling code in app.py — that's the
point of the abstraction.
"""

import os
import json
import time
import hashlib
import datetime
from pathlib import Path

NETWORK_NAME = "Polygon Amoy Testnet"
LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulated_chain.jsonl")


class SimulatedChain:
    """A local, append-only, hash-linked ledger that stands in for Polygon
    when no testnet credentials are configured. Structurally identical to a
    real chain (each block references the previous block's hash), so the
    Trust Engine and the /blockchain explorer page work unmodified either way."""

    mode = "simulated"

    def __init__(self):
        Path(LEDGER_PATH).touch(exist_ok=True)

    def _last_block_hash(self):
        last = None
        if os.path.getsize(LEDGER_PATH) > 0:
            with open(LEDGER_PATH, "r") as f:
                for line in f:
                    if line.strip():
                        last = json.loads(line)
        return last["block_hash"] if last else "0" * 64

    def _block_count(self):
        if not os.path.exists(LEDGER_PATH) or os.path.getsize(LEDGER_PATH) == 0:
            return 0
        with open(LEDGER_PATH, "r") as f:
            return sum(1 for line in f if line.strip())

    def anchor(self, data_hash: str, meta: dict) -> dict:
        prev = self._last_block_hash()
        block_number = 47_312_000 + self._block_count()  # cosmetically realistic Polygon block range
        payload = f"{prev}{data_hash}{block_number}{time.time()}"
        tx_hash = "0x" + hashlib.sha256(payload.encode()).hexdigest()
        block_hash = "0x" + hashlib.sha256((prev + tx_hash).encode()).hexdigest()
        record = {
            "block_number": block_number,
            "block_hash": block_hash,
            "prev_block_hash": prev,
            "tx_hash": tx_hash,
            "data_hash": data_hash,
            "meta": meta,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds") + "Z",
        }
        with open(LEDGER_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
        return {
            "tx_hash": tx_hash,
            "block_number": block_number,
            "network": NETWORK_NAME + " (simulated)",
            "mode": "simulated",
            "explorer_url": f"/blockchain/tx/{tx_hash}",
        }

    def all_blocks(self):
        blocks = []
        if os.path.exists(LEDGER_PATH):
            with open(LEDGER_PATH, "r") as f:
                for line in f:
                    if line.strip():
                        blocks.append(json.loads(line))
        return list(reversed(blocks))

    def get_tx(self, tx_hash):
        for b in self.all_blocks():
            if b["tx_hash"] == tx_hash:
                return b
        return None


class PolygonChain:
    """Real anchoring on Polygon Amoy testnet via web3.py + the deployed
    AgriTraceRegistry contract. Only activates when credentials + web3 are
    both present — see module docstring."""

    mode = "polygon"

    ABI = [
        {
            "inputs": [
                {"internalType": "string", "name": "batchCode", "type": "string"},
                {"internalType": "string", "name": "eventType", "type": "string"},
                {"internalType": "bytes32", "name": "dataHash", "type": "bytes32"},
            ],
            "name": "anchorRecord",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        }
    ]

    def __init__(self):
        from web3 import Web3  # imported lazily so the app runs without web3 installed

        self.w3 = Web3(Web3.HTTPProvider(os.environ["POLYGON_RPC_URL"]))
        self.account = self.w3.eth.account.from_key(os.environ["POLYGON_PRIVATE_KEY"])
        self.contract = self.w3.eth.contract(
            address=os.environ["POLYGON_CONTRACT_ADDRESS"], abi=self.ABI
        )

    def anchor(self, data_hash: str, meta: dict) -> dict:
        tx = self.contract.functions.anchorRecord(
            meta.get("batch_code", ""), meta.get("event_type", ""), bytes.fromhex(data_hash)
        ).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 200_000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return {
            "tx_hash": tx_hash.hex(),
            "block_number": receipt.blockNumber,
            "network": NETWORK_NAME,
            "mode": "polygon",
            "explorer_url": f"https://amoy.polygonscan.com/tx/{tx_hash.hex()}",
        }


def get_blockchain_service():
    """Factory: real Polygon anchoring if fully configured, simulated chain otherwise."""
    required = ["POLYGON_RPC_URL", "POLYGON_PRIVATE_KEY", "POLYGON_CONTRACT_ADDRESS"]
    if all(os.environ.get(k) for k in required):
        try:
            return PolygonChain()
        except Exception as exc:  # missing web3, bad RPC, etc. — fail safe to simulated mode
            print(f"[blockchain] Falling back to simulated chain: {exc}")
    return SimulatedChain()
