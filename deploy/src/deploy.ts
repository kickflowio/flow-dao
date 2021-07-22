import { TezosToolkit } from "@taquito/taquito";
import { loadContract, deployContract } from "./utils";
import BigNumber from "bignumber.js";

export interface DeployParams {
  // Tezos interface
  Tezos: TezosToolkit;

  // Admin for the FA1.2 token
  admin: string;

  // Initial voting period for proposals in the DAO
  votingPeriod: BigNumber;

  // Intial timelock period for proposals in the DAO
  timelockPeriod: BigNumber;

  // Number of votes required to attain quorum in DAO
  quorumVotes: BigNumber;

  // Number of tokens required to register a new proposal
  proposalThreshold: BigNumber;
}

export const deploy = async (deployParams: DeployParams): Promise<void> => {
  try {
    // Load FA1.2 token code
    const tokenCode = loadContract(`${__dirname}/../../michelson/fa12_token.tz`);

    // Prepare storage for FA1.2 token
    const tokenStorage = `(Pair (Pair (Pair "${deployParams.admin}" {}) (Pair {Elt "" 0x697066733a2f2f516d54683548646a6766735277357a73665136483776616a566f396356706e6258757872747679765451684a5450} False)) (Pair (Pair {} {}) (Pair {Elt 0 (Pair 0 {Elt "decimals" 0x3138; Elt "icon" 0x697066733a2f2f516d5436625843483343377348703867524a377638376e52687155544732753962664c45464c4a33684a457a4341; Elt "name" 0x4b69636b666c6f7720476f7665726e616e636520546f6b656e; Elt "symbol" 0x4b464c})} 0)))`;

    console.log(">>Deploying Token Contract\n\n");

    // Deploy token
    const tokenAddress = await deployContract(tokenCode, tokenStorage, deployParams.Tezos);

    console.log(`Token Deployed at: ${tokenAddress}\n\n`);

    // Load DAO code
    const daoCode = loadContract(`${__dirname}/../../michelson/flow_dao.tz`);

    // Prepare storage for DAO
    const daoStorage = `(Pair (Pair (Pair (Pair ${deployParams.votingPeriod.toFixed()} (Pair ${deployParams.timelockPeriod.toFixed()} (Pair ${deployParams.quorumVotes.toFixed()} ${deployParams.proposalThreshold.toFixed()}))) {Elt "" 0x697066733a2f2f516d57736e50625166704b7573536f506d36777062426e414b61725068734736755769756561476755644b684d5a}) (Pair None {})) (Pair (Pair 0 "${tokenAddress}") (Pair 0 (Pair {} None))));`;

    console.log(">>Deploying DAO Contract\n\n");

    // Deploy  DAO
    const daoAddress = await deployContract(daoCode, daoStorage, deployParams.Tezos);

    console.log(`DAO Deployed at: ${daoAddress}\n\n`);

    // Load Community Fund code
    const communityFundCode = loadContract(`${__dirname}/../../michelson/community_fund.tz`);

    // Prepare Community Fund storage
    const communityFundStorage = `"${daoAddress}"`;

    console.log(">>Deploying Community Fund Contract\n\n");

    // Deploy  DAO
    const communityFundAddress = await deployContract(
      communityFundCode,
      communityFundStorage,
      deployParams.Tezos
    );

    console.log(`Community Fund Deployed at: ${communityFundAddress}\n\n`);
  } catch (err) {
    console.log(err);
  }
};
