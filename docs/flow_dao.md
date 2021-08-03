# Flow DAO

Flow DAO contract is the primary DAO contract of Kickflow. Proposals can be submitted in the DAO and voted upon using our customised fa12 token. Each proposal has an associated lambda that is executed if the proposal passes the vote.

## Storage

- `governance_parameters` : Parameters which define the governance model of the DAO. It is of the type GOVERNANCE_PARAMETERS_TYPE as specified in [types/dao.py](https://github.com/kickflowio/flow-dao/blob/master/types/dao.py)
- `proposals` : A BIGMAP mapping from a unique id to PROPOSAL_TYPE as specified in [types/proposal.py](https://github.com/kickflowio/flow-dao/blob/master/types/proposal.py)
- `token_address` : Tezos address of the governance token contract.
- `state` : State machine variable to prevent [call authorization by-pass](https://forum.tezosagora.org/t/smart-contract-vulnerabilities-due-to-tezos-message-passing-architecture/2045)
- `voters` : A BIGMAP mapping from a PAIR of voter address and proposal id to a PAIR of number of votes and vote value (i.e up-vote or a down-vote)
- `proposal_buffer` : A helper buffer to store the value of sender's address, `proposal_metadata` and `proposal_lambda` while waiting for `register_proposal_callback entrypoint` to be called by the token contract.
- `voting_buffer` : A helper buffer to store the value of sender's address, `proposal_id` and `vote_value` while waiting for `vote_callback` to be called by the token contract.
- `uuid` : A unique incrementing id for the proposals.

## Entrypoints

- `register_proposal` : Registers a new proposal in the DAO. Each proposal has an associated metadata and a lambda function.
- `register_proposal_callback` : Called by the governance token contract along with the token balance of the sender who called the `register_proposal` entrypoint.
- `end_voting` : Ends the voting phase for a proposal and activates the timelock on the proposal if the vote passes.
- `vote` : Allows governance token holders to vote on the active proposals
- `vote_callback` : Called by the governance token contract along with the token balance of the sender who called the `vote` entrypoint.
- `execute_proposal` : Executes the proposal lambda of a certain proposal if the timelock period is over.
- `set_governance_parameters` : Called by the DAO contract itself through a proposal. This changes the governance parameters of the DAO contract.

## Proposal Execution Timeline

| Events in order of occurences | Description                                                                                                                                                                                                                                                                                                                                         |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Proposal submission           | A proposal is submitted in the DAO calling the `register_proposal` entrypoint. It takes in parameters- `proposal_metadata` i.e the an IPFS hash of proposal's metadata, and `proposal_lambda` i.e a lambda function accepting a `UNIT` type as parameter and returning a list of operations that would be executed if the proposal passes the vote. |
| Voting on submitted proposal  | The submitted proposal is voted upon by calling the `vote` entrypoint that takes in the `proposal_id` i.e the uuid of the proposal being voted on and `vote_value` i.e the indicator whether it is an up-vote (0) or a down-vote (1). Voting continues for the span of the `voting_period`.                                                         |
| Ending the vote               | The voting phase is ended by calling the `end_voting` entrypoint that checks if the proposal votes has met the `quorum_votes` threshold and that the number of `up_votes` is greater than the `down_votes`. If the proposal passes the checks, the timelock on it is activated.                                                                     |
| Executing the proposal        | A proposal can be executed if and only if it has cleared the vote and the timelock period on it is over. When the `execute_proposal` entrypoint is called, the lambda associated to the proposal is executed.                                                                                                                                       |

## Preferred Proposal Metadata Format

For proposals on Kickflow, we suggest the following metadata format-

```JSON
{
  "title" : "<A suitable title for the proposal>",
  "briefDescription" : "<A brief description of the proposal>",
  "longDescription" : "<An elaborate description of the proposal>"
}
```

## How Voting System Works?

As mentioned earlier, Flow DAO functions on a token voting mechanism. Voting in Flow DAO does not require voters to lock up their tokens, instead we use historical balance snapshots stored in the storage of our customised FA1.2 goverance token contract.
Every proposal entity has a field `origin_level` associated with it. This is the level at which the proposal was submitted in the DAO. Whenever a proposal is voted upon by calling the `vote` entrypoint, a subsequent call is made to the `getBalanceAt` view entrypoint of the token contract. This view fetches the hisrotical balance at a certain block-level as asked for, here i.e `origin_level` - 1 (The -1 prevents a flash loan attack scenario wherein the proposer submits the proposal and simultaneously votes on it in the same block). Thereafter, the view entrypoint calls the `vote_callback` entrypoint of the DAO contract, passing in the balance. This balance value is then recorded as the voting weight (or the number of votes given) for a proposal by a voter.
