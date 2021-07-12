import { TezosToolkit } from "@taquito/taquito";
import { InMemorySigner } from "@taquito/signer";
import { DeployParams, deploy } from "./deploy";
import BigNumber from "bignumber.js";

const Tezos = new TezosToolkit("https://testnet-tezos.giganode.io");

Tezos.setProvider({
  signer: new InMemorySigner(process.env.PRIVATE_KEY as string),
});

const DECIMALS = new BigNumber("10").pow(18);

const deployParams: DeployParams = {
  Tezos: Tezos,
  admin: "tz1ZczbHu1iLWRa88n9CUiCKDGex5ticp19S",
  votingPeriod: new BigNumber("900"),
  timelockPeriod: new BigNumber("300"),
  quorumVotes: new BigNumber(50000).multipliedBy(DECIMALS),
  proposalThreshold: new BigNumber(200000).multipliedBy(DECIMALS),
};

void deploy(deployParams);
