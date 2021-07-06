import smartpy as sp

PROPOSAL_LAMBDA = sp.TLambda(sp.TUnit, sp.TList(sp.TOperation))

# params:
#   ending    : The timestamp at which the timelock ends. Set to 0 when timelock is not activated
#   activated : True when the timelock is activated after proposal passed voting phase
PROPOSAL_TIMELOCK = sp.TRecord(
    ending=sp.TTimestamp,
    activated=sp.TBool,
).layout(("ending", "activated"))

# params:
#   up_votes           : Number of votes in favour of the proposal
#   down_votes         : Number of votes against the proposal
#   voters             : mapping of voter address => number of votes
#   proposal_metadata  : IPFS hash of metadata for the proposal
#   proposal_lambda    : The lambda to be executed if proposal vote goes through
#   proposal_timelock  : The timelock on the proposal execution
#   voting_end         : The timestamp at which voting ends for the proposal
#   creator            : Address of the creator of the proposal
#   origin_level       : The block level at which proposal was initiated
#   status             : The current status of the proposal
PROPOSAL_TYPE = sp.TRecord(
    up_votes=sp.TNat,
    down_votes=sp.TNat,
    voters=sp.TMap(sp.TAddress, sp.TRecord(votes=sp.TNat, value=sp.TNat)),
    proposal_metadata=sp.TString,
    proposal_lambda=PROPOSAL_LAMBDA,
    proposal_timelock=PROPOSAL_TIMELOCK,
    voting_end=sp.TTimestamp,
    creator=sp.TAddress,
    origin_level=sp.TNat,
    status=sp.TNat,
).layout(
    (
        "up_votes",
        (
            "down_votes",
            (
                "voters",
                (
                    "proposal_metadata",
                    (
                        "proposal_lambda",
                        (
                            "proposal_timelock",
                            (
                                "voting_end",
                                (
                                    "creator",
                                    (
                                        "origin_level",
                                        "status",
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
)

#########
# Status
#########

# Proposal is being voted upon
PROPOSAL_STATUS_VOTING = 0
# Proposal has passed the vote, and the timelock on its execution is activated
PROPOSAL_STATUS_TIMELOCKED = 1
# The proposal is executed after timelock period is over
PROPOSAL_STATUS_EXECUTED = 2
# The proposal did not pass the vote
PROPOSAL_STATUS_REJECTED = 3

##############
# Vote values
##############

VOTE_VALUE_UPVOTE = 0
VOTE_VALUE_DOWNVOTE = 1
