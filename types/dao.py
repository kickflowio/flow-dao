import smartpy as sp

# Params:
#   voting_period       : The length of voting_period in seconds
#   timelock_period     : Length of proposal execution timelock in seconds
#   quorum_votes        : Minimum number of votes required by a proposal to attain quorum
#   proposal_threshold  : Minimum number of governance tokens an address must hold to propose
GOVERNANCE_PARAMETERS_TYPE = sp.TRecord(
    voting_period=sp.TInt,
    timelock_period=sp.TInt,
    quorum_votes=sp.TNat,
    proposal_threshold=sp.TNat,
).layout(
    (
        "voting_period",
        (
            "timelock_period",
            (
                "quorum_votes",
                "proposal_threshold",
            ),
        ),
    ),
)
