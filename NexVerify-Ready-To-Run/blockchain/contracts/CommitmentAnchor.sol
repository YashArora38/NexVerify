// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title CommitmentAnchor
/// @notice Stores only 32-byte commitments; source evidence remains off-chain.
/// @dev There is no proxy, delegatecall, selfdestruct, or commitment rewrite.
contract CommitmentAnchor {
    address public immutable owner;
    mapping(address => bool) public writers;
    mapping(address => mapping(bytes32 => bool)) public anchored;
    mapping(address => mapping(bytes32 => uint256)) public anchoredAt;

    event WriterUpdated(address indexed writer, bool allowed);
    event CommitmentAnchored(
        address indexed publisher,
        bytes32 indexed commitment,
        uint256 timestamp
    );

    error OnlyOwner();
    error OnlyWriter();
    error ZeroAddress();
    error ZeroCommitment();
    error AlreadyAnchored();

    constructor() {
        owner = msg.sender;
        writers[msg.sender] = true;
        emit WriterUpdated(msg.sender, true);
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    modifier onlyWriter() {
        if (!writers[msg.sender]) revert OnlyWriter();
        _;
    }

    /// @notice Add or remove a publisher without changing existing commitments.
    /// @dev Writer policy is mutable; anchored commitment records are not.
    function setWriter(address writer, bool allowed) external onlyOwner {
        if (writer == address(0)) revert ZeroAddress();
        writers[writer] = allowed;
        emit WriterUpdated(writer, allowed);
    }

    /// @notice Anchor one commitment under msg.sender's publisher namespace.
    /// @dev Repeating the same publisher/commitment pair always reverts.
    function anchor(bytes32 commitment) external onlyWriter {
        if (commitment == bytes32(0)) revert ZeroCommitment();
        if (anchored[msg.sender][commitment]) revert AlreadyAnchored();

        anchored[msg.sender][commitment] = true;
        anchoredAt[msg.sender][commitment] = block.timestamp;
        emit CommitmentAnchored(msg.sender, commitment, block.timestamp);
    }

    function isAnchored(address publisher, bytes32 commitment)
        external
        view
        returns (bool)
    {
        return anchored[publisher][commitment];
    }
}
