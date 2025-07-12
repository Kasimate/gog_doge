import time
import logging
import os
from typing import Dict, Any, List, Optional

from web3 import Web3
from web3.contract import Contract
from web3.middleware import geth_poa_middleware
from web3.types import LogReceipt
import requests
from requests.exceptions import RequestException

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# In a real-world application, this would be loaded from environment variables
# or a secure configuration management system (e.g., HashiCorp Vault).

CONFIG = {
    "source_chain": {
        "name": "Ethereum-Sepolia",
        "rpc_url": "https://rpc.sepolia.org", # Example public RPC
        "bridge_contract_address": "0xYourSourceBridgeContractAddress", # Placeholder
        "confirmations_required": 5, # Number of blocks to wait for event finality
    },
    "destination_chain": {
        "name": "Polygon-Mumbai",
        "rpc_url": "https://rpc-mumbai.maticvigil.com", # Example public RPC
        "bridge_contract_address": "0xYourDestinationBridgeContractAddress", # Placeholder
        # In a real scenario, this private key would be securely stored.
        # NEVER hardcode private keys in production code.
        "validator_private_key": "0x'" + "a"*64, # Placeholder for simulation
    },
    "bridge_abi": [
        # A simplified ABI for the event we are listening for on the source chain
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "sender", "type": "address"},
                {"indexed": True, "name": "recipient", "type": "address"},
                {"indexed": False, "name": "amount", "type": "uint256"},
                {"indexed": False, "name": "destinationChainId", "type": "uint256"},
                {"indexed": True, "name": "nonce", "type": "uint256"}
            ],
            "name": "TokensLocked",
            "type": "event"
        },
        # A simplified ABI for the function to call on the destination chain
        {
            "name": "releaseTokens",
            "outputs": [],
            "inputs": [
                {"name": "recipient", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "sourceTxHash", "type": "bytes32"}
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ],
    "polling_interval_seconds": 15,
    "log_file": "bridge_listener.log",
    "max_retries": 3,
    "retry_delay_seconds": 5
}

# ==============================================================================
# LOGGER SETUP
# ==============================================================================

def setup_logger(log_file: str) -> logging.Logger:
    """Configures and returns a standard logger instance."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Create handlers
    c_handler = logging.StreamHandler()
    f_handler = logging.FileHandler(log_file)
    c_handler.setLevel(logging.INFO)
    f_handler.setLevel(logging.INFO)

    # Create formatters and add it to handlers
    log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    c_handler.setFormatter(log_format)
    f_handler.setFormatter(log_format)

    # Add handlers to the logger
    if not logger.handlers:
        logger.addHandler(c_handler)
        logger.addHandler(f_handler)
        
    return logger

logger = setup_logger(CONFIG['log_file'])

# ==============================================================================
# BLOCKCHAIN CONNECTOR CLASS
# ==============================================================================

class BlockchainConnector:
    """Handles connection and data fetching from a specific blockchain."""

    def __init__(self, name: str, rpc_url: str):
        """
        Initializes the connector for a given blockchain.

        Args:
            name (str): The name of the chain (for logging purposes).
            rpc_url (str): The URL of the JSON-RPC endpoint.
        """
        self.name = name
        self.rpc_url = rpc_url
        self.web3: Optional[Web3] = None
        self._connect()

    def _connect(self):
        """Establishes a connection to the blockchain node."""
        for attempt in range(CONFIG['max_retries']):
            try:
                self.web3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={'timeout': 60}))
                # Inject middleware for PoA chains like Polygon or BSC Testnet
                self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
                
                if self.web3.is_connected():
                    logger.info(f"Successfully connected to {self.name} at {self.rpc_url}")
                    return
                else:
                    raise ConnectionError("Web3 provider failed to connect.")
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} to connect to {self.name} failed: {e}")
                if attempt < CONFIG['max_retries'] - 1:
                    time.sleep(CONFIG['retry_delay_seconds'])
                else:
                    logger.critical(f"Could not establish connection to {self.name} after {CONFIG['max_retries']} attempts.")
                    # In a production system, this might trigger an alert.
                    raise

    def get_latest_block_number(self) -> Optional[int]:
        """Fetches the most recent block number from the chain."""
        if not self.web3 or not self.web3.is_connected():
            logger.warning(f"Not connected to {self.name}. Attempting to reconnect.")
            self._connect()
        
        try:
            return self.web3.eth.block_number
        except Exception as e:
            logger.error(f"Failed to get latest block number from {self.name}: {e}")
            return None

    def get_contract(self, address: str, abi: List[Dict]) -> Optional[Contract]:
        """Returns a Web3 contract instance."""
        if not self.web3:
            logger.error(f"Web3 not initialized for {self.name}.")
            return None
        if not self.web3.is_address(address):
            logger.error(f"Invalid contract address provided for {self.name}: {address}")
            return None
        return self.web3.eth.contract(address=self.web3.to_checksum_address(address), abi=abi)

# ==============================================================================
# TRANSACTION MANAGER CLASS
# ==============================================================================

class TransactionManager:
    """Manages the creation, signing, and submission of transactions."""

    def __init__(self, connector: BlockchainConnector, private_key: str, contract_address: str, contract_abi: List[Dict]):
        """
        Initializes the transaction manager.

        Args:
            connector (BlockchainConnector): The connector for the destination chain.
            private_key (str): The private key of the validator/operator account.
            contract_address (str): The address of the destination bridge contract.
            contract_abi (List[Dict]): The ABI of the destination bridge contract.
        """
        self.connector = connector
        if not self.connector.web3:
             raise ValueError("Connector's web3 instance is not initialized.")
        self.web3 = self.connector.web3
        self.account = self.web3.eth.account.from_key(private_key)
        self.contract = self.connector.get_contract(contract_address, contract_abi)
        if not self.contract:
            raise ValueError("Failed to initialize contract in TransactionManager.")

    def submit_release_tokens(self, recipient: str, amount: int, source_tx_hash: bytes) -> bool:
        """
        Builds, signs, and sends the 'releaseTokens' transaction.
        In this simulation, it only logs the action instead of sending.

        Args:
            recipient (str): The address to receive the tokens on the destination chain.
            amount (int): The amount of tokens to be released (in wei).
            source_tx_hash (bytes): The hash of the original 'TokensLocked' transaction.

        Returns:
            bool: True if the simulated submission was successful, False otherwise.
        """
        logger.info(f"Preparing 'releaseTokens' transaction for recipient {recipient} with amount {amount}.")
        try:
            # Build the transaction
            tx_params = {
                'from': self.account.address,
                'nonce': self.web3.eth.get_transaction_count(self.account.address),
                'gas': 200000, # A fixed gas limit for simulation
                'gasPrice': self.web3.eth.gas_price, # Fetch current gas price
            }
            
            # Create the transaction object
            transaction = self.contract.functions.releaseTokens(
                self.web3.to_checksum_address(recipient),
                amount,
                source_tx_hash
            ).build_transaction(tx_params)

            # Sign the transaction
            signed_tx = self.web3.eth.account.sign_transaction(transaction, private_key=self.account.key)
            
            # --- SIMULATION --- #
            # In a real system, you would uncomment the line below:
            # tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            # logger.info(f"Transaction sent to {self.connector.name}. Tx Hash: {tx_hash.hex()}")
            
            simulated_tx_hash = self.web3.keccak(signed_tx.rawTransaction).hex()
            logger.info(f"[SIMULATION] Transaction signed and ready. Would be sent to {self.connector.name}.")
            logger.info(f"[SIMULATION] Recipient: {recipient}, Amount: {amount}")
            logger.info(f"[SIMULATION] Source Tx Hash: {source_tx_hash.hex()}")
            logger.info(f"[SIMULATION] Simulated Tx Hash: {simulated_tx_hash}")
            
            return True

        except Exception as e:
            logger.error(f"Failed to build or sign 'releaseTokens' transaction: {e}")
            # Handle potential issues like invalid nonce, insufficient funds, etc.
            return False

# ==============================================================================
# EVENT PROCESSOR CLASS
# ==============================================================================

class EventProcessor:
    """
    Processes events fetched from the source chain and triggers actions on the destination chain.
    """
    def __init__(self, tx_manager: TransactionManager):
        """
        Initializes the event processor.

        Args:
            tx_manager (TransactionManager): The manager for submitting transactions to the destination chain.
        """
        self.tx_manager = tx_manager
        self.processed_events = set() # A simple cache to prevent reprocessing events

    def process_events(self, events: List[LogReceipt]):
        """
        Iterates through a list of events and processes them.

        Args:
            events (List[LogReceipt]): A list of event logs from web3.py.
        """
        if not events:
            return
            
        logger.info(f"Found {len(events)} new 'TokensLocked' events to process.")
        
        for event in events:
            tx_hash = event['transactionHash'].hex()
            if tx_hash in self.processed_events:
                logger.warning(f"Event with tx_hash {tx_hash} has already been processed. Skipping.")
                continue

            logger.info(f"Processing event from transaction: {tx_hash}")
            
            # --- Event Data Validation --- #
            if not self._is_event_valid(event):
                logger.error(f"Event {tx_hash} has invalid data. Skipping.")
                continue

            # Extract data
            args = event['args']
            recipient = args['recipient']
            amount = args['amount']

            # Trigger action on destination chain
            success = self.tx_manager.submit_release_tokens(
                recipient=recipient,
                amount=amount,
                source_tx_hash=event['transactionHash']
            )

            if success:
                self.processed_events.add(tx_hash)
                logger.info(f"Successfully processed and actioned event for tx {tx_hash}.")
            else:
                logger.error(f"Failed to action event for tx {tx_hash}. Will be retried on next poll.")

    def _is_event_valid(self, event: LogReceipt) -> bool:
        """
        Performs basic validation on the event data.
        In a real system, this would be much more complex, checking against protocol rules.
        """
        try:
            args = event['args']
            if not all(key in args for key in ['recipient', 'amount']):
                return False
            if not Web3.is_address(args['recipient']):
                return False
            if not isinstance(args['amount'], int) or args['amount'] <= 0:
                return False
            return True
        except Exception as e:
            logger.error(f"Exception during event validation: {e}")
            return False

# ==============================================================================
# MAIN ORCHESTRATOR
# ==============================================================================

class BridgeListener:
    """The main orchestrator that runs the listening loop."""

    def __init__(self):
        logger.info("Initializing Cross-Chain Bridge Listener...")
        # --- Setup Source Chain --- #
        self.source_connector = BlockchainConnector(
            name=CONFIG['source_chain']['name'], 
            rpc_url=CONFIG['source_chain']['rpc_url']
        )
        self.source_contract = self.source_connector.get_contract(
            address=CONFIG['source_chain']['bridge_contract_address'],
            abi=CONFIG['bridge_abi']
        )
        if not self.source_contract:
            raise RuntimeError("Failed to initialize source contract.")

        # --- Setup Destination Chain --- #
        dest_connector = BlockchainConnector(
            name=CONFIG['destination_chain']['name'], 
            rpc_url=CONFIG['destination_chain']['rpc_url']
        )
        tx_manager = TransactionManager(
            connector=dest_connector,
            private_key=CONFIG['destination_chain']['validator_private_key'],
            contract_address=CONFIG['destination_chain']['bridge_contract_address'],
            contract_abi=CONFIG['bridge_abi']
        )

        # --- Setup Processor --- #
        self.event_processor = EventProcessor(tx_manager)
        
        self.last_processed_block = self._get_initial_start_block()

    def _get_initial_start_block(self) -> int:
        """
        Determines the starting block for the listener.
        In a real application, this state should be persisted to a database.
        """
        # For simulation, we just start from a few blocks behind the current tip.
        latest_block = self.source_connector.get_latest_block_number()
        if latest_block is None:
            logger.critical("Cannot determine start block. Exiting.")
            exit(1)
        
        start_block = latest_block - 10
        logger.info(f"Setting initial start block to {start_block}")
        return start_block

    def run(self):
        """Starts the main event listening loop."""
        logger.info("Starting event listening loop. Press Ctrl+C to stop.")
        while True:
            try:
                self.poll_for_events()
                logger.info(f"Loop finished. Waiting for {CONFIG['polling_interval_seconds']} seconds...")
                time.sleep(CONFIG['polling_interval_seconds'])
            except KeyboardInterrupt:
                logger.info("Shutdown signal received. Exiting gracefully.")
                break
            except Exception as e:
                logger.critical(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
                time.sleep(CONFIG['polling_interval_seconds'] * 2) # Longer sleep on critical failure

    def poll_for_events(self):
        """The core logic for fetching and processing events in a single poll."""
        latest_block = self.source_connector.get_latest_block_number()
        if latest_block is None:
            logger.error("Could not fetch latest block number. Skipping this poll.")
            return

        # Define the block range to query, respecting confirmation requirements.
        # This prevents processing events from blocks that might get re-org'd.
        from_block = self.last_processed_block + 1
        to_block = latest_block - CONFIG['source_chain']['confirmations_required']

        if from_block > to_block:
            logger.info(f"No new blocks to process. Current tip: {latest_block}, last processed: {self.last_processed_block}")
            return

        logger.info(f"Polling for 'TokensLocked' events from block {from_block} to {to_block}...")

        try:
            # Fetch events from the source chain contract
            event_filter = self.source_contract.events.TokensLocked.create_filter(
                fromBlock=from_block, 
                toBlock=to_block
            )
            events = event_filter.get_all_entries()

            if events:
                self.event_processor.process_events(events)
            else:
                logger.info("No new 'TokensLocked' events found in this range.")

            # --- State Persistence --- #
            # In a real app, this update would be in a transactional database
            # along with the event processing status.
            self.last_processed_block = to_block
            logger.info(f"Advanced last processed block to {self.last_processed_block}")

        except Exception as e:
            logger.error(f"Error while fetching or processing events: {e}", exc_info=True)

if __name__ == "__main__":
    # This check is important to prevent execution on import
    listener = BridgeListener()
    listener.run()
