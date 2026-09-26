// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgriTraceRegistry
/// @notice Minimal, gas-efficient anchoring contract for the AgriTrace
///         farm-to-fork traceability platform. The chain never stores raw
///         batch, sensor or personal data — only the SHA-256 hash of each
///         key lifecycle event (selective anchoring), computed off-chain by
///         the Backend Integrity Service. Anyone can verify a batch's
///         history by recomputing the hash from the public record and
///         comparing it against what is stored here.
contract AgriTraceRegistry {
    struct Record {
        string batchCode;
        string eventType;
        bytes32 dataHash;
        address anchoredBy;
        uint256 timestamp;
    }

    address public owner;
    mapping(address => bool) public authorizedAnchors;
    Record[] private records;

    // batchCode => indices into `records`, for fast per-batch lookup
    mapping(string => uint256[]) private batchRecordIndices;

    event RecordAnchored(
        uint256 indexed recordId,
        string indexed batchCodeIndexed,
        string batchCode,
        string eventType,
        bytes32 dataHash,
        address anchoredBy,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "AgriTrace: not owner");
        _;
    }

    modifier onlyAuthorized() {
        require(authorizedAnchors[msg.sender] || msg.sender == owner, "AgriTrace: not authorized");
        _;
    }

    constructor() {
        owner = msg.sender;
        authorizedAnchors[msg.sender] = true;
    }

    function authorizeAnchor(address anchor) external onlyOwner {
        authorizedAnchors[anchor] = true;
    }

    function revokeAnchor(address anchor) external onlyOwner {
        authorizedAnchors[anchor] = false;
    }

    /// @notice Anchor one lifecycle event's hash on-chain.
    function anchorRecord(
        string calldata batchCode,
        string calldata eventType,
        bytes32 dataHash
    ) external onlyAuthorized {
        records.push(Record({
            batchCode: batchCode,
            eventType: eventType,
            dataHash: dataHash,
            anchoredBy: msg.sender,
            timestamp: block.timestamp
        }));
        uint256 recordId = records.length - 1;
        batchRecordIndices[batchCode].push(recordId);

        emit RecordAnchored(recordId, batchCode, batchCode, eventType, dataHash, msg.sender, block.timestamp);
    }

    function getRecord(uint256 recordId) external view returns (Record memory) {
        return records[recordId];
    }

    function getRecordCount() external view returns (uint256) {
        return records.length;
    }

    function getBatchRecordIds(string calldata batchCode) external view returns (uint256[] memory) {
        return batchRecordIndices[batchCode];
    }

    /// @notice Verify a hash the caller computed off-chain against what is
    ///         actually anchored for a given record.
    function verify(uint256 recordId, bytes32 dataHash) external view returns (bool) {
        return records[recordId].dataHash == dataHash;
    }
}

/*
Deployment (Polygon Amoy testnet), once you have a funded test wallet:

    npm install --save-dev hardhat
    npx hardhat init
    # copy this file into contracts/, then:
    npx hardhat run scripts/deploy.js --network amoy

Set the deployed address, your RPC URL and your account's private key as
POLYGON_CONTRACT_ADDRESS / POLYGON_RPC_URL / POLYGON_PRIVATE_KEY (see
backend/.env.example) and AgriTrace's Blockchain Service will switch from
simulated anchoring to real on-chain anchoring automatically — no other
code changes needed.
*/
