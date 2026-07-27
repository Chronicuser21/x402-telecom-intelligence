// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20PermitBurnable.sol";

contract MockUSDC is ERC20, ERC20Permit {
    uint8 private immutable _decimals;

    constructor() ERC20("USD Coin", "USDC") ERC20Permit("USD Coin") {
        _decimals = 6;
        _mint(msg.sender, 1000000 * 10**_decimals); // 1M USDC
    }

    function decimals() public view override returns (uint8) {
        return _decimals;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
