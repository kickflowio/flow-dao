# FA1.2 Token

We have built a custom FA1.2 token that records historical balances of an address. This assists the token voting mechanism by ruling out the requirement of locking up the tokens and additionally making the token flash loan resistant, since the historical balances are the ones which the address has held for the entirety of a block.

**NOTE:** Below we have only specified the storage elements and entrypoints which deviate from the standard implementation of an FA1.2 token.

## Storage

- `snapshots` : A `BIGMAP` mapping from a `PAIR` of address and snapshot serial number, to a `PAIR` of block-level and the balance at that level.
- `numSnapshots` : A `BIGMAP` that records the number of balance snapshots stored for a specific address. This helps in registering the serial number of each new snapshot.
- `mintingDisabled` : Set to True when minting is disabled for the token.

## Entrypoints

- `takeSnaphot` : Records the balance of the given address at the current block-level. If multiple calls are made at the same level, the balance at the last call is the actual snapshot.
- `getBalanceAt` : A view entrypoint that returns the balance of an address at a given block-level. This is done by binary searching through the snapshots `BIGMAP` with the serial numbers of a particular address as the index.
- `disableMint` : Disables the minting for the token permanently when called by the admin of the token contract.
