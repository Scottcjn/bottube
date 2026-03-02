// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title Wrapped RustChain Token (wRTC) on Base L2
/// @notice Custodial bridge token — minted on deposit, burned on withdrawal.
///         6 decimals to match Solana wRTC and native RTC.
contract WrappedRTC is ERC20, Ownable {
    address public bridge;

    modifier onlyBridge() {
        require(msg.sender == bridge, "not bridge");
        _;
    }

    constructor(address _bridge)
        ERC20("Wrapped RustChain Token", "wRTC")
        Ownable(msg.sender)
    {
        bridge = _bridge;
    }

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external onlyBridge {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external onlyBridge {
        _burn(from, amount);
    }

    function setBridge(address _b) external onlyOwner {
        bridge = _b;
    }
}
