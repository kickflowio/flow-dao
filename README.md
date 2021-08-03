# FlowDAO

FlowDAO is a DAO built on Tezos, and is used to govern [Kickflow](https://kickflow.io). It operates on a token voting mechanism using an FA1.2 standard based token. Governance token holders can submit proposals in the DAO, and other token holders can vote on them. Each proposal is associated with a lambda which is executed if the vote passes. It's design was initially inspired by [Murmuration](https://github.com/Hover-Labs/murmuration), but heavily customised to suit the needs of Kickflow.

## $KFL

$KFL is the governance token operating FlowDAO. It is based on the [FA1.2 standard](https://gitlab.com/tezos/tzip/-/blob/master/proposals/tzip-7/tzip-7.md) and is customised to store snapshots of balances at block levels at which the balance of an address changes. This aides in the governance process by preventing the need to lock up the governance tokens at any stage of proposal voting.
These snapshots are used to retrieve the historical balances, which are used for checking the proposal threshold and for recording the vote weight of voters. Usage of historical balances makes the DAO flash loan resistant as the snapshots contain the balance which an address has held for the entirety of a block level.

## Development

FlowDAO is written in SmartPy. To know more, view SmartPy's [documentation](https://docs.smartpy.io/).

### Smart Contracts

- `fa12_token.py` : A customised FA1.2 standard based token to operate the DAO.
- `flow_dao.py` : The DAO contract.
- `community_fund.py` : A community fund managed by the DAO, with the ability to transfer tez, FA1.2 & FA2.

View the smart contract [docs](https://github.com/kickflowio/flow-dao/tree/master/docs) for more context.

### Folders

- `deploy` : Scripts assisting deployment of the contracts.
- `helpers` : Scripts assisting test scenarios in contracts.
- `michelson` : Compiled michelson code of the contracts.
- `types` : Scripts representing the types used in the contracts.

### Compilation

A shell script has been provided to assist compilation of the contracts. The script can be run using-

```shell
$ bash compile.sh
```

The compiled michelson files are stored in the michelson folder.

### Deployment

View the README in the [deploy](https://github.com/kickflowio/flow-dao/tree/master/deploy) folder to know the deployment process.
