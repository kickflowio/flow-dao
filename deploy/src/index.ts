import { TezosToolkit } from "@taquito/taquito";
import { InMemorySigner } from "@taquito/signer";
import { DeployParams, deploy } from "./deploy";
import BigNumber from "bignumber.js";

const Tezos = new TezosToolkit("https://granadanet.smartpy.io");

Tezos.setProvider({
  signer: new InMemorySigner(process.env.PRIVATE_KEY as string),
});

// The decimals specified in the token metadata
const DECIMALS = new BigNumber("10").pow(18);

// Admin address of the token
const ADMIN = "tz1ZczbHu1iLWRa88n9CUiCKDGex5ticp19S";

// Voting period in seconds
const VOTING_PERIOD = 900;

// Timelock period in seconds
const TIMELOCK_PERIOD = 300;

// Quorum votes in number of governance tokens
const QUORUM_VOTES = 200_000;

// Proposal threshold in number of governance tokens
const PROPOSAL_THRESHOLD = 50_000;

const deployParams: DeployParams = {
  Tezos: Tezos,
  admin: ADMIN,
  votingPeriod: new BigNumber(VOTING_PERIOD),
  timelockPeriod: new BigNumber(TIMELOCK_PERIOD),
  quorumVotes: new BigNumber(QUORUM_VOTES).multipliedBy(DECIMALS),
  proposalThreshold: new BigNumber(PROPOSAL_THRESHOLD).multipliedBy(DECIMALS),
};

void deploy(deployParams);
