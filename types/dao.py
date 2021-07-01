import smartpy as sp

MAIN_GOVERNANCE_PARAMETERS_TYPE = sp.TRecord(
    voting_period=sp.TInt,
    timelock_period=sp.TInt,
    quorum_votes=sp.TNat,
    proposal_threshold=sp.TNat,
)

ROUND_GOVERNANCE_PARAMETERS_TYPE = sp.TRecord(
    round_address=sp.TOption(sp.TAddress),
    donation_handler_address=sp.TOption(sp.TAddress),
)
