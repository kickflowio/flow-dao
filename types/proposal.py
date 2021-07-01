import smartpy as sp

PROPOSAL_LAMBDA = sp.TLambda(sp.TUnit, sp.TList(sp.TOperation))

PROPOSAL_TIMELOCK = sp.TRecord(ending=sp.TTimestamp, activated=sp.TBool)

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
)

#########
# Status
#########
PROPOSAL_STATUS_VOTING = 0
PROPOSAL_STATUS_TIMELOCKED = 1
PROPOSAL_STATUS_EXECUTED = 2
PROPOSAL_STATUS_REJECTED = 3

##############
# Vote values
##############

VOTE_VALUE_UPVOTE = 0
VOTE_VALUE_DOWNVOTE = 1
