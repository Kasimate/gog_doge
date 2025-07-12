# {repo_name}

A simulation of a robust event listener component for a cross-chain bridge. This script is designed to act as a backend service that monitors a bridge contract on a source blockchain, processes lock events, and triggers corresponding token release actions on a destination blockchain.

This project is for demonstration purposes and showcases a structured, multi-class architecture for building resilient blockchain services in Python.

## Concept

A cross-chain bridge allows users to transfer assets or data from one blockchain (e.g., Ethereum) to another (e.g., Polygon). A common mechanism for asset transfer is the "lock-and-mint" model:

1.  **Lock**: A user sends tokens to a smart contract on the source chain. The contract locks these tokens and emits an event (`TokensLocked`) containing details of the transaction (recipient, amount, etc.).
2.  **Verify**: Off-chain services, called validators or listeners, monitor the source chain for these `TokensLocked` events.
3.  **Mint/Release**: After verifying the event, the service triggers a function on a corresponding smart contract on the destination chain. This function mints or releases an equivalent amount of pegged tokens to the intended recipient.

This script simulates the critical **Validator/Listener** component (Step 2 and 3).

## Code Architecture

The script is designed with a clear separation of concerns, organized into several key classes:

-   `BlockchainConnector`: Responsible for establishing and maintaining a connection to a blockchain's JSON-RPC endpoint using the `web3.py` library. It handles connection retries and provides basic functionalities like fetching the latest block number.

-   `TransactionManager`: Encapsulates the logic for creating, signing, and submitting transactions to the destination chain. It manages the validator's account and interacts with the destination bridge contract. In this simulation, it logs the transaction details instead of broadcasting them.

-   `EventProcessor`: Contains the core business logic. It takes raw event logs from the source chain, validates their data, ensures they haven't been processed before, and instructs the `TransactionManager` to perform the corresponding action on the destination chain.

-   `BridgeListener`: The main orchestrator class. It initializes all other components, manages the main application state (like the last processed block), and runs the primary polling loop that continuously checks for new events.

-   `CONFIG`: A dictionary that centralizes all configuration parameters, such as RPC URLs, contract addresses, and polling intervals. This makes the system easy to configure and adapt.

### Data Flow Diagram

```
(Source Chain)      (BridgeListener Script)
     |                     |
[Bridge Contract]          |
     | emits               |
     | 'TokensLocked'      |
     | event               |     +-----------------------+
     +-------------------> |     |  BridgeListener       |
                           |     | (Main Loop)           |
                           |     +-----------+-----------+
                           |                 | polls
                           |     +-----------v-----------+
                           |     | BlockchainConnector   |
                           |     | (Fetches Events)      |
                           |     +-----------+-----------+
                           |                 | passes events
                           |     +-----------v-----------+
                           |     |  EventProcessor       | --> (Validates, checks for duplicates)
                           |     | (Business Logic)      |
                           |     +-----------+-----------+
                           |                 | triggers action
                           |     +-----------v-----------+
                           |     | TransactionManager    | --(simulated)--> (Destination Chain)
                           |     | (Signs & Sends Tx)    |
                           |     +-----------------------+
```

## How it Works

1.  **Initialization**: The `BridgeListener` class is instantiated. It sets up two `BlockchainConnector` instances—one for the source chain and one for the destination chain.
2.  **State Management**: It determines a starting block to scan for events. In this simulation, it starts a few blocks behind the current chain tip. In a real-world scenario, this state would be persisted in a database to ensure no events are missed between restarts.
3.  **Polling Loop**: The `run()` method starts an infinite loop.
4.  **Fetch Blocks**: In each iteration, it queries the `BlockchainConnector` for the latest block number on the source chain.
5.  **Define Range**: It calculates a block range to scan (`from_block` to `to_block`), ensuring it leaves a buffer of several blocks (`confirmations_required`) from the chain tip. This is a crucial step to avoid processing events from blocks that might be reverted in a chain re-organization (re-org).
6.  **Filter Events**: It uses `web3.py`'s event filtering to query the source bridge contract for any `TokensLocked` events within the calculated block range.
7.  **Process Events**: If events are found, they are passed to the `EventProcessor`.
8.  **Validate and Action**: The `EventProcessor` validates each event's data, checks a local cache to prevent double-processing, and then calls the `TransactionManager` to prepare and sign the `releaseTokens` transaction for the destination chain.
9.  **Simulate Submission**: The `TransactionManager` builds and signs the transaction but, for safety and demonstration, only logs the details of what *would* have been sent to the network.
10. **Update State**: After successfully scanning a range, the `BridgeListener` updates its `last_processed_block` tracker and waits for the configured polling interval before starting the next cycle.

## Usage Example

### 1. Prerequisites

-   Python 3.8+
-   `pip` package manager

### 2. Installation

Clone the repository and install the required dependencies:

```bash
# Navigate to the repository directory
cd {repo_name}

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install libraries
pip install -r requirements.txt
```

### 3. Configuration

Before running, open `script.py` and modify the `CONFIG` dictionary. You will need to replace the placeholder contract addresses:

-   `CONFIG['source_chain']['bridge_contract_address']`
-   `CONFIG['destination_chain']['bridge_contract_address']`

For a real test, you would also provide valid RPC URLs and a real private key for the validator.

### 4. Running the Script

Execute the script from your terminal:

```bash
python script.py
```

The script will start running and logging its activity to both the console and the `bridge_listener.log` file.

### Example Output

```
2023-10-27 10:30:00,123 - __main__ - INFO - Initializing Cross-Chain Bridge Listener...
2023-10-27 10:30:02,456 - __main__ - INFO - Successfully connected to Ethereum-Sepolia at https://rpc.sepolia.org
2023-10-27 10:30:04,789 - __main__ - INFO - Successfully connected to Polygon-Mumbai at https://rpc-mumbai.maticvigil.com
2023-10-27 10:30:05,111 - __main__ - INFO - Setting initial start block to 4500100
2023-10-27 10:30:05,112 - __main__ - INFO - Starting event listening loop. Press Ctrl+C to stop.
2023-10-27 10:30:05,345 - __main__ - INFO - Polling for 'TokensLocked' events from block 4500101 to 4500105...
2023-10-27 10:30:07,890 - __main__ - INFO - No new 'TokensLocked' events found in this range.
2023-10-27 10:30:07,891 - __main__ - INFO - Advanced last processed block to 4500105
2023-10-27 10:30:07,892 - __main__ - INFO - Loop finished. Waiting for 15 seconds...
...
# (When an event is found)
2023-10-27 10:30:25,123 - __main__ - INFO - Found 1 new 'TokensLocked' events to process.
2023-10-27 10:30:25,124 - __main__ - INFO - Processing event from transaction: 0xabc123...
2023-10-27 10:30:25,567 - __main__ - INFO - Preparing 'releaseTokens' transaction for recipient 0xRecipientAddress... with amount 1000000000000000000.
2023-10-27 10:30:26,111 - __main__ - INFO - [SIMULATION] Transaction signed and ready. Would be sent to Polygon-Mumbai.
2023-10-27 10:30:26,112 - __main__ - INFO - [SIMULATION] Recipient: 0xRecipientAddress..., Amount: 1000000000000000000
2023-10-27 10:30:26,113 - __main__ - INFO - [SIMULATION] Source Tx Hash: 0xabc123...
2023-10-27 10:30:26,114 - __main__ - INFO - [SIMULATION] Simulated Tx Hash: 0xdef456...
2023-10-27 10:30:26,115 - __main__ - INFO - Successfully processed and actioned event for tx 0xabc123...
```
