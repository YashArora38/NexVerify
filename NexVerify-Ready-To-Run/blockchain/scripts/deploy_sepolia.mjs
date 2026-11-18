/**
 * NexVerify Sepolia Contract Deployment Script
 *
 * Requirements:
 * - SEPOLIA_RPC_URL (e.g. Alchemy / Infura / public Sepolia RPC)
 * - DEPLOYER_PRIVATE_KEY (Funded with Sepolia testnet ETH; NEVER commit this!)
 *
 * Usage:
 *   node scripts/deploy_sepolia.mjs
 */

import fs from "node:fs";
import path from "node:path";
import { ethers } from "ethers";
import { compileContract } from "./compile.mjs";

console.log("=== NexVerify CommitmentAnchor Sepolia Deployment ===");

const rpcUrl = process.env.SEPOLIA_RPC_URL || process.env.ETHEREUM_RPC_URL;
const privateKey = process.env.DEPLOYER_PRIVATE_KEY;

if (!rpcUrl) {
  console.error("\n[DEPLOYMENT BLOCKED]: SEPOLIA_RPC_URL environment variable is not configured.");
  console.log("To deploy to Sepolia:");
  console.log("1. Get a Sepolia RPC endpoint (e.g. from Alchemy, Infura, or https://rpc.sepolia.org)");
  console.log("2. Set SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/YOUR_API_KEY");
  console.log("3. Set DEPLOYER_PRIVATE_KEY=0xYOUR_TESTNET_PRIVATE_KEY");
  console.log("4. Run: node scripts/deploy_sepolia.mjs\n");
  process.exit(1);
}

if (!privateKey) {
  console.error("\n[DEPLOYMENT BLOCKED]: DEPLOYER_PRIVATE_KEY environment variable is not configured.");
  console.log("Provide a funded Sepolia wallet private key via DEPLOYER_PRIVATE_KEY.");
  console.log("Never share, log, or commit private keys to source control.\n");
  process.exit(1);
}

try {
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const network = await provider.getNetwork();
  console.log(`Connected to RPC. Chain ID: ${network.chainId} (Hex: ${ethers.toQuantity(network.chainId)})`);

  if (network.chainId !== 11155111n) {
    console.warn(`[WARNING]: Connected chain ID is ${network.chainId}, expected Sepolia (11155111).`);
  }

  const wallet = new ethers.Wallet(privateKey, provider);
  const deployerAddress = await wallet.getAddress();
  const balance = await provider.getBalance(deployerAddress);
  console.log(`Deployer Address: ${deployerAddress}`);
  console.log(`Balance:          ${ethers.formatEther(balance)} ETH`);

  if (balance === 0n) {
    console.error("[ERROR]: Deployer balance is 0 ETH. Obtain free Sepolia testnet ETH from a faucet before deploying.");
    process.exit(1);
  }

  console.log("\nCompiling CommitmentAnchor.sol...");
  const compiled = compileContract();
  const abi = compiled.abi;
  const bytecode = compiled.evm.bytecode.object;

  console.log("Estimating gas for deployment...");
  const factory = new ethers.ContractFactory(abi, bytecode, wallet);
  const deployTx = await factory.getDeployTransaction();
  const estimatedGas = await provider.estimateGas(deployTx);
  console.log(`Estimated Gas: ${estimatedGas}`);

  console.log("Broadcasting deployment transaction...");
  const contract = await factory.deploy();
  console.log(`Transaction Hash: ${contract.deploymentTransaction().hash}`);
  console.log("Waiting for confirmation on Sepolia...");

  await contract.waitForDeployment();
  const contractAddress = await contract.getAddress();
  const receipt = await contract.deploymentTransaction().wait(2); // wait 2 confirmations

  console.log("\n=== DEPLOYMENT SUCCESSFUL! ===");
  console.log(`Contract Address: ${contractAddress}`);
  console.log(`Block Number:     ${receipt.blockNumber}`);
  console.log(`Gas Used:         ${receipt.gasUsed}`);
  console.log(`Etherscan Link:   https://sepolia.etherscan.io/address/${contractAddress}`);

  // Verify deployed bytecode on-chain
  const onChainCode = await provider.getCode(contractAddress);
  if (!onChainCode || onChainCode === "0x") {
    throw new Error("On-chain bytecode verification failed: no code at deployed address");
  }
  console.log("On-chain bytecode verified.");

  // Save deployment metadata
  const deploymentDir = path.resolve(import.meta.dirname, "../deployments");
  fs.mkdirSync(deploymentDir, { recursive: true });
  const record = {
    network: "sepolia",
    chainId: Number(network.chainId),
    contractAddress,
    deployerAddress,
    transactionHash: receipt.hash,
    blockNumber: receipt.blockNumber,
    deployedAt: new Date().toISOString(),
    explorerUrl: `https://sepolia.etherscan.io/address/${contractAddress}`,
    abi,
  };
  fs.writeFileSync(path.join(deploymentDir, "sepolia.json"), JSON.stringify(record, null, 2));
  console.log(`Deployment record saved to blockchain/deployments/sepolia.json`);
} catch (err) {
  console.error("\n[DEPLOYMENT FAILED]:", err.message);
  process.exit(1);
}
