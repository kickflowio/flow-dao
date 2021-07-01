import smartpy as sp

GOVERNANCE_PARAMETERS_TYPE = sp.TRecord(
    voting_period=sp.TInt,
    timelock_period=sp.TInt,
    quorum_votes=sp.TNat,
    proposal_threshold=sp.TNat,
)
