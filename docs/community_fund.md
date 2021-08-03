# Community Fund

The community fund contract is a DAO controlled treasury that can store and transfer tez, FA1.2 and FA2 tokens. It also has functionality for a delegation of tez.

## Storage

- `admin` : The address having administrative control on the community fund. **This is usually the DAO**.

## Entrypoints

- `transfer_tez` : Transfers the tez stored in the contract to the specified address.
- `transfer_fa12` : Transfers FA1.2 tokens held by the contract to the specified address.
- `transfer_fa2` : Transfers FA2 tokens held by the contract to the specified addresses (batch txns)
- `set_admin` : Sets a new admin for the contract.
- `set_delegation` : Sets a new baker delegate for the contract.
