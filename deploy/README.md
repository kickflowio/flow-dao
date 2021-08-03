# Deploy

The scripts provided in this folder assist the deployment of FlowDAO contracts. We have used [Taquito](https://tezostaquito.io/) library to simplify the process.

## Installing Dependencies

To install the dependencies run:

```
$ npm install
```

## Preparing Storage

The storage fields which are required to mentioned pre-deployment can be set in the `index.ts` file in the `src` folder. The fields to be set are

- `ADMIN` : Admin address of the governance token
- `DECIMALS` : The decimals value provided in token metadata
- `VOTING_PERIOD` : Voting period in the DAO (in seconds)
- `TIMELOCK_PERIOD` : Timelock period in the DAO (in seconds)
- `QUORUM_VOTES` : Number of votes required to reach quorum (number of governance tokens)
- `PROPOSAL_THRESHOLD` : Number of tokens required to submit a proposal

## Deployment

Once the storage is prepared, the deployment can be done by providing a private key as an environment variable and running `index.ts`:

```
$ PRIVATE_KEY=<Your private key> npx ts-node ./src/
```
