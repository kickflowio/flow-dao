import smartpy as sp

Addresses = sp.io.import_script_from_url("file:helpers/addresses.py")
Proposal = sp.io.import_script_from_url("file:types/proposal.py")
DAO = sp.io.import_script_from_url("file:types/dao.py")
Errors = sp.io.import_script_from_url("file:types/errors.py")
Token = sp.io.import_script_from_url("file:fa12_token.py")
DummyStore = sp.io.import_script_from_url("file:helpers/dummy_store.py")
DummyToken = sp.io.import_script_from_url("file:helpers/dummy_token.py")

############
# CONSTANTS
############

DAY = 86400  # Seconds in a day
DECIMALS = 1  # Governance token decimals

################
# State Machine
################

STATE_IDLE = 0
STATE_AWAITING_BALANCE_SNAPSHOT = 1

#################
# Default Values
#################

GOVERNANCE_PARAMETERS = sp.record(
    voting_period=sp.int(2 * DAY),
    timelock_period=sp.int(1 * DAY),
    quorum_votes=200_000 * DECIMALS,
    proposal_threshold=50_000 * DECIMALS,
)


# Proposal buffer type to be used during callback execution
PROPOSAL_BUFFER = sp.TRecord(
    sender=sp.TAddress, proposal_metadata=sp.TString, proposal_lambda=Proposal.PROPOSAL_LAMBDA
)

# Voting buffer type to be used during callback execution
VOTING_BUFFER = sp.TRecord(sender=sp.TAddress, proposal_id=sp.TNat, vote_value=sp.TNat)


###########
# Contract
###########


class FlowDAO(sp.Contract):
    def __init__(
        self,
        governance_parameters=GOVERNANCE_PARAMETERS,
        proposals=sp.big_map(
            l={},
            tkey=sp.TNat,
            tvalue=Proposal.PROPOSAL_TYPE,
        ),
        token_address=Addresses.TOKEN,
        state=STATE_IDLE,
        proposal_buffer=sp.none,
        voting_buffer=sp.none,
    ):

        # TZIP16 based metadata
        metadata = sp.big_map(
            l={
                "": sp.utils.bytes_of_string(
                    "ipfs://QmWsnPbQfpKusSoPm6wpbBnAKarPhsG6uWiueaGgUdKhMZ"
                )
            },
            tkey=sp.TString,
            tvalue=sp.TBytes,
        )

        self.init_type(
            sp.TRecord(
                governance_parameters=DAO.GOVERNANCE_PARAMETERS_TYPE,
                uuid=sp.TNat,
                proposals=sp.TBigMap(sp.TNat, Proposal.PROPOSAL_TYPE),
                token_address=sp.TAddress,
                state=sp.TNat,
                proposal_buffer=sp.TOption(PROPOSAL_BUFFER),
                voting_buffer=sp.TOption(VOTING_BUFFER),
                metadata=sp.TBigMap(sp.TString, sp.TBytes),
            )
        )

        self.init(
            governance_parameters=governance_parameters,
            uuid=sp.nat(0),
            proposals=proposals,
            token_address=token_address,
            state=state,
            proposal_buffer=proposal_buffer,
            voting_buffer=voting_buffer,
            metadata=metadata,
        )

    @sp.entry_point
    def register_proposal(self, params):
        sp.set_type(
            params,
            sp.TRecord(proposal_metadata=sp.TString, proposal_lambda=Proposal.PROPOSAL_LAMBDA),
        )

        # Update proposal buffer
        self.data.proposal_buffer = sp.some(
            sp.record(
                proposal_metadata=params.proposal_metadata,
                proposal_lambda=params.proposal_lambda,
                sender=sp.sender,
            )
        )

        # Set state machine to awaiting balance snapshot
        self.data.state = STATE_AWAITING_BALANCE_SNAPSHOT

        # Call token contract
        c = sp.contract(
            sp.TPair(sp.TRecord(address=sp.TAddress, level=sp.TNat), sp.TContract(sp.TNat)),
            self.data.token_address,
            "getBalanceAt",
        ).open_some()

        # Check balance snapshot of previous level to avoid flash loan usage
        sp.transfer(
            (
                sp.record(address=sp.sender, level=sp.as_nat(sp.level - 1)),
                sp.self_entry_point("register_proposal_callback"),
            ),
            sp.mutez(0),
            c,
        )

    @sp.entry_point
    def register_proposal_callback(self, balance):
        sp.set_type(balance, sp.TNat)
        # Verify state and proposal buffer values
        sp.verify(self.data.state == STATE_AWAITING_BALANCE_SNAPSHOT, Errors.INCORRECT_STATE)
        sp.verify(self.data.proposal_buffer.is_some(), Errors.PROPOSAL_BUFFER_EMPTY)

        # Other sanity checks
        sp.verify(
            balance >= self.data.governance_parameters.proposal_threshold,
            Errors.NOT_ENOUGH_TOKENS,
        )
        sp.verify(sp.sender == self.data.token_address, Errors.NOT_ALLOWED)

        # value stored in proposal buffer
        buffer_value = self.data.proposal_buffer.open_some()

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata=buffer_value.proposal_metadata,
            proposal_lambda=buffer_value.proposal_lambda,
            proposal_timelock=sp.record(ending=sp.timestamp(0), activated=False),
            voting_end=sp.now.add_seconds(self.data.governance_parameters.voting_period),
            creator=buffer_value.sender,
            origin_level=sp.level,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        # Increment uuid and insert proposal in the storage
        self.data.uuid += 1
        self.data.proposals[self.data.uuid] = proposal

        # Reset state and buffer
        self.data.state = STATE_IDLE
        self.data.proposal_buffer = sp.none

    @sp.entry_point
    def end_voting(self, proposal_id):
        sp.set_type(proposal_id, sp.TNat)

        # Confirm that proposal exists
        sp.verify(self.data.proposals.contains(proposal_id), Errors.INVALID_PROPOSAL_ID)

        proposal = self.data.proposals[proposal_id]

        # Proposal sanity checks
        sp.verify(sp.now > proposal.voting_end, Errors.VOTING_ONGOING)
        sp.verify(proposal.status == Proposal.PROPOSAL_STATUS_VOTING, Errors.VOTING_ALREADY_ENDED)

        # Verify voting thresholds
        total_votes = proposal.up_votes + proposal.down_votes
        quorum_attained = total_votes >= self.data.governance_parameters.quorum_votes
        majority_vote = proposal.up_votes > proposal.down_votes

        sp.if majority_vote & quorum_attained:
            # Activate proposal timelock
            proposal.proposal_timelock.activated = True
            proposal.proposal_timelock.ending = sp.now.add_seconds(
                self.data.governance_parameters.timelock_period
            )

            # Change proposal status to timelocked
            proposal.status = Proposal.PROPOSAL_STATUS_TIMELOCKED
        sp.else:
            # Set proposal status to rejected
            proposal.status = Proposal.PROPOSAL_STATUS_REJECTED

    @sp.entry_point
    def vote(self, params):
        sp.set_type(params, sp.TRecord(proposal_id=sp.TNat, vote_value=sp.TNat))
        sp.verify(self.data.proposals.contains(params.proposal_id), Errors.INVALID_PROPOSAL_ID)

        proposal = self.data.proposals[params.proposal_id]

        # Sanity checks
        sp.verify(proposal.status == Proposal.PROPOSAL_STATUS_VOTING, Errors.VOTING_ALREADY_ENDED)
        sp.verify(sp.now < proposal.voting_end, Errors.VOTING_ALREADY_ENDED)
        sp.verify(~proposal.voters.contains(sp.sender), Errors.ALREADY_VOTED)

        # Put params in voting buffer
        self.data.voting_buffer = sp.some(
            sp.record(
                proposal_id=params.proposal_id, vote_value=params.vote_value, sender=sp.sender
            )
        )

        # Update the state machine
        self.data.state = STATE_AWAITING_BALANCE_SNAPSHOT

        # Call token contract
        c = sp.contract(
            sp.TPair(sp.TRecord(address=sp.TAddress, level=sp.TNat), sp.TContract(sp.TNat)),
            self.data.token_address,
            "getBalanceAt",
        ).open_some()

        # Check balance snapshot of previous level to avoid flash loan usage
        sp.transfer(
            (
                sp.record(address=sp.sender, level=proposal.origin_level),
                sp.self_entry_point("vote_callback"),
            ),
            sp.mutez(0),
            c,
        )

    @sp.entry_point
    def vote_callback(self, balance):
        sp.set_type(balance, sp.TNat)

        # Verify state and voting buffer
        sp.verify(self.data.state == STATE_AWAITING_BALANCE_SNAPSHOT, Errors.INCORRECT_STATE)
        sp.verify(self.data.voting_buffer.is_some(), Errors.VOTING_BUFFER_EMPTY)

        # Other sanity checks
        sp.verify(balance > 0, Errors.INVALID_VOTE)
        sp.verify(sp.sender == self.data.token_address, Errors.NOT_ALLOWED)

        buffer_value = self.data.voting_buffer.open_some()

        proposal = self.data.proposals[buffer_value.proposal_id]

        # Add voter to proposal's voters map
        proposal.voters[buffer_value.sender] = sp.record(
            votes=balance, value=buffer_value.vote_value
        )

        # Update proposal fields
        sp.if buffer_value.vote_value == Proposal.VOTE_VALUE_UPVOTE:
            proposal.up_votes += balance
        sp.else:
            sp.if buffer_value.vote_value == Proposal.VOTE_VALUE_DOWNVOTE:
                proposal.down_votes += balance
            sp.else:
                sp.failwith(Errors.INVALID_VOTE_VALUE)

        # Reset state and voting buffer
        self.data.state = STATE_IDLE
        self.data.voting_buffer = sp.none

    # Executes the proposal_lambda of a proposal with timelock activated
    @sp.entry_point
    def execute_proposal(self, proposal_id):
        sp.set_type(proposal_id, sp.TNat)

        # Verify if proposal exists
        sp.verify(self.data.proposals.contains(proposal_id), Errors.INVALID_PROPOSAL_ID)

        proposal = self.data.proposals[proposal_id]

        # Other sanity checks
        sp.verify(proposal.status == Proposal.PROPOSAL_STATUS_TIMELOCKED, Errors.TIMELOCK_INACTIVE)
        sp.verify(sp.now > proposal.proposal_timelock.ending, Errors.EXECUTING_TOO_SOON)

        # Execute proposal lambda
        operations = proposal.proposal_lambda(sp.unit)
        sp.set_type(operations, sp.TList(sp.TOperation))
        sp.add_operations(operations)

        # Update proposal status
        proposal.status = Proposal.PROPOSAL_STATUS_EXECUTED

    @sp.entry_point
    def set_governance_parameters(self, params):
        sp.set_type(params, DAO.GOVERNANCE_PARAMETERS_TYPE)

        # Confirm if the sender is the DAO itself
        sp.verify(sp.sender == sp.self_address, Errors.NOT_ALLOWED)

        self.data.governance_parameters = params



# Helper viewer class
class Viewer(sp.Contract):
    def __init__(self, t):
        self.init(last=sp.none)
        self.init_type(sp.TRecord(last=sp.TOption(t)))

    @sp.entry_point
    def target(self, params):
        self.data.last = sp.some(params)


if __name__ == "__main__":

    ####################
    # register_proposal
    ####################

    @sp.add_test(name="register_proposal can register a proposal")
    def test():
        scenario = sp.test_scenario()

        token = Token.FA12()
        dao = FlowDAO(token_address=token.address)

        # Create dummy store with DAO as admin
        dummy_store = DummyStore.DummyStore(dao.address)

        scenario += token
        scenario += dao
        scenario += dummy_store

        # Mint token for ALICE
        scenario += token.mint(address=Addresses.ALICE, value=50_000 * DECIMALS).run(
            sender=Addresses.ADMIN, level=1
        )

        # The lambda for the proposal
        def proposal_lambda(unit_param):
            sp.set_type(unit_param, sp.TUnit)
            c = sp.contract(sp.TNat, dummy_store.address, "modify_value").open_some()
            sp.result([sp.transfer_operation(sp.nat(5), sp.mutez(0), c)])

        proposal_metadata = "ipfs://xyz"

        # ALICE registers a proposal at level 2
        scenario += dao.register_proposal(
            proposal_metadata=proposal_metadata, proposal_lambda=proposal_lambda
        ).run(sender=Addresses.ALICE, level=2, now=sp.timestamp(0))

        # Verify if a proposal got registered
        scenario.verify(dao.data.uuid == 1)

        proposal = dao.data.proposals[1]

        # Verify if the proposal has correct fields
        scenario.verify(proposal.up_votes == 0)
        scenario.verify(proposal.down_votes == 0)
        scenario.verify(sp.len(proposal.voters) == 0)
        scenario.verify(proposal.proposal_metadata == proposal_metadata)
        scenario.verify(proposal.creator == Addresses.ALICE)
        scenario.verify(proposal.origin_level == 2)
        scenario.verify(proposal.status == Proposal.PROPOSAL_STATUS_VOTING)
        scenario.verify(proposal.voting_end == sp.timestamp(DAY * 2))
        scenario.verify(
            proposal.proposal_timelock == sp.record(ending=sp.timestamp(0), activated=False)
        )

        # Confirm that state is reset
        scenario.verify(dao.data.state == STATE_IDLE)

    @sp.add_test(name="register_proposal cannot register if balance is insufficient")
    def test():
        scenario = sp.test_scenario()

        token = Token.FA12()
        dao = FlowDAO(token_address=token.address)

        # Create dummy store with DAO as admin
        dummy_store = DummyStore.DummyStore(dao.address)

        scenario += token
        scenario += dao
        scenario += dummy_store

        # Mint tokens for ALICE (1 less than proposal threshold)
        scenario += token.mint(address=Addresses.ALICE, value=49_999 * DECIMALS).run(
            sender=Addresses.ADMIN, level=1
        )

        # The lambda for the proposal
        def proposal_lambda(unit_param):
            sp.set_type(unit_param, sp.TUnit)
            c = sp.contract(sp.TNat, dummy_store.address, "modify_value").open_some()
            sp.result([sp.transfer_operation(sp.nat(5), sp.mutez(0), c)])

        proposal_metadata = "ipfs://xyz"

        # ALICE registers a proposal at level 2
        scenario += dao.register_proposal(
            proposal_metadata=proposal_metadata, proposal_lambda=proposal_lambda
        ).run(
            sender=Addresses.ALICE,
            level=2,
            now=sp.timestamp(0),
            valid=False,
            exception=Errors.NOT_ENOUGH_TOKENS,
        )

    @sp.add_test(name="register_proposal requires proposer to hold balance for at least 1 level")
    def test():
        scenario = sp.test_scenario()

        token = Token.FA12()
        dao = FlowDAO(token_address=token.address)

        # Create dummy store with DAO as admin
        dummy_store = DummyStore.DummyStore(dao.address)

        scenario += token
        scenario += dao
        scenario += dummy_store

        # Mint tokens for ALICE (1 less than proposal threshold)
        scenario += token.mint(address=Addresses.ALICE, value=50_000 * DECIMALS).run(
            sender=Addresses.ADMIN, level=1
        )

        # The lambda for the proposal
        def proposal_lambda(unit_param):
            sp.set_type(unit_param, sp.TUnit)
            c = sp.contract(sp.TNat, dummy_store.address, "modify_value").open_some()
            sp.result([sp.transfer_operation(sp.nat(5), sp.mutez(0), c)])

        proposal_metadata = "ipfs://xyz"

        # ALICE registers a proposal at the same level (Like in a flash loan attack)
        scenario += dao.register_proposal(
            proposal_metadata=proposal_metadata, proposal_lambda=proposal_lambda
        ).run(
            sender=Addresses.ALICE,
            level=1,
            now=sp.timestamp(0),
            valid=False,
            exception=Errors.NOT_ENOUGH_TOKENS,
        )

    #############################
    # register_proposal_callback
    #############################

    @sp.add_test(name="register_proposal_callback fails for invalid state")
    def test():
        scenario = sp.test_scenario()

        dao = FlowDAO()

        scenario += dao

        scenario += dao.register_proposal_callback(50_000 * DECIMALS).run(
            sender=Addresses.ALICE, valid=False, exception=Errors.INCORRECT_STATE
        )

    # NOTE: With Tezos changing its inter-contract call convention to DFS, a 'call injection' test on register_proposal_callback would be trivial

    #############
    # end_voting
    #############

    @sp.add_test("end_voting activates timelock for a proposal passing the vote")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=100_001 * DECIMALS,
            down_votes=100_000 * DECIMALS,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao

        # End the vote
        scenario += dao.end_voting(1).run(now=sp.timestamp(1))

        # Fetch proposal timelock
        timelock = dao.data.proposals[1].proposal_timelock

        # Verify if timelock was activate
        scenario.verify(timelock.activated)
        scenario.verify(timelock.ending == sp.timestamp(1 * DAY + 1))
        scenario.verify(dao.data.proposals[1].status == Proposal.PROPOSAL_STATUS_TIMELOCKED)

    @sp.add_test("end_voting rejects a proposal not passing the vote")
    def test():
        scenario = sp.test_scenario()

        # Did not attain quorum
        proposal_1 = sp.record(
            up_votes=99_999 * DECIMALS,
            down_votes=100_000 * DECIMALS,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        # Did not receive up votes in majority
        proposal_2 = sp.record(
            up_votes=100_000 * DECIMALS,
            down_votes=100_001 * DECIMALS,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal_1, 2: proposal_2}))

        scenario += dao

        # End the votes
        scenario += dao.end_voting(1).run(now=sp.timestamp(1))
        scenario += dao.end_voting(2).run(now=sp.timestamp(1))

        DEFAULT_TIMELOCK = sp.record(ending=sp.timestamp(0), activated=False)

        # Verify  if fields are correctly set for proposal 1
        scenario.verify(dao.data.proposals[1].status == Proposal.PROPOSAL_STATUS_REJECTED)
        scenario.verify(dao.data.proposals[1].proposal_timelock == DEFAULT_TIMELOCK)

        # Verify  if fields are correctly set for proposal 2
        scenario.verify(dao.data.proposals[2].status == Proposal.PROPOSAL_STATUS_REJECTED)
        scenario.verify(dao.data.proposals[2].proposal_timelock == DEFAULT_TIMELOCK)

    @sp.add_test(name="end_voting fails for invalid proposal id")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=100_001 * DECIMALS,
            down_votes=100_000 * DECIMALS,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao

        # End the vote by supplying invalid id
        scenario += dao.end_voting(2).run(
            now=sp.timestamp(1), valid=False, exception=Errors.INVALID_PROPOSAL_ID
        )

    @sp.add_test(name="end_voting fails if proposal is still under vote")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=100_001 * DECIMALS,
            down_votes=100_000 * DECIMALS,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(2),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao

        # End the vote 1 second before ending of voting
        scenario += dao.end_voting(1).run(
            now=sp.timestamp(1), valid=False, exception=Errors.VOTING_ONGOING
        )

    @sp.add_test(name="end_voting fails if proposal has already ended")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=100_001 * DECIMALS,
            down_votes=100_000 * DECIMALS,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_REJECTED,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao

        # End the vote 1 second before ending of voting
        scenario += dao.end_voting(1).run(
            now=sp.timestamp(1), valid=False, exception=Errors.VOTING_ALREADY_ENDED
        )

    #######
    # vote
    #######

    @sp.add_test(name="vote records the correct number of votes and vote_value")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(1),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        token = DummyToken.DummyToken(20_000 * DECIMALS)

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}), token_address=token.address)

        scenario += dao
        scenario += token

        # ALICE up votes for proposal (20,000 tokens)
        scenario += dao.vote(proposal_id=1, vote_value=Proposal.VOTE_VALUE_UPVOTE).run(
            sender=Addresses.ALICE, level=2, now=sp.timestamp(0)
        )

        scenario += token.set_val(10_000 * DECIMALS)

        # BOB down votes for proposal (10,000 tokens)
        scenario += dao.vote(proposal_id=1, vote_value=Proposal.VOTE_VALUE_DOWNVOTE).run(
            sender=Addresses.BOB, level=3, now=sp.timestamp(0)
        )

        voters = dao.data.proposals[1].voters

        # Verify number of voters
        scenario.verify(sp.len(voters) == 2)

        # Verify proposal field values
        scenario.verify(dao.data.proposals[1].up_votes == 20_000 * DECIMALS)
        scenario.verify(dao.data.proposals[1].down_votes == 10_000 * DECIMALS)
        scenario.verify(
            voters[Addresses.ALICE]
            == sp.record(votes=20_000 * DECIMALS, value=Proposal.VOTE_VALUE_UPVOTE)
        )
        scenario.verify(
            voters[Addresses.BOB]
            == sp.record(votes=10_000 * DECIMALS, value=Proposal.VOTE_VALUE_DOWNVOTE)
        )

        # Verify state machine value
        scenario.verify(dao.data.state == STATE_IDLE)

    @sp.add_test(name="vote fails if the voting is over for a proposal")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(1),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_REJECTED,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao

        # Vote 1 second after voting ends
        scenario += dao.vote(proposal_id=1, vote_value=Proposal.VOTE_VALUE_UPVOTE).run(
            sender=Addresses.ALICE,
            level=2,
            now=sp.timestamp(2),
            valid=False,
            exception=Errors.VOTING_ALREADY_ENDED,
        )

    @sp.add_test(name="vote fails if sender has already voted")
    def test():
        scenario = sp.test_scenario()

        # Record ALICE's vote
        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={Addresses.ALICE: sp.record(votes=1, value=Proposal.VOTE_VALUE_UPVOTE)},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(1),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao

        # ALICE votes even though she has voted before
        scenario += dao.vote(proposal_id=1, vote_value=Proposal.VOTE_VALUE_UPVOTE).run(
            sender=Addresses.ALICE, now=sp.timestamp(0), valid=False, exception=Errors.ALREADY_VOTED
        )

    @sp.add_test("vote fails if voter has 0 balance")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(1),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        token = DummyToken.DummyToken(0)

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}), token_address=token.address)

        scenario += dao
        scenario += token

        # ALICE up votes for proposal with 0 balance snapshot
        scenario += dao.vote(proposal_id=1, vote_value=Proposal.VOTE_VALUE_UPVOTE).run(
            sender=Addresses.ALICE,
            level=2,
            now=sp.timestamp(0),
            valid=False,
            exception=Errors.INVALID_VOTE,
        )

    @sp.add_test("vote fails if invalid vote_value is given")
    def test():
        scenario = sp.test_scenario()

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=sp.build_lambda(lambda x: sp.list(l=[], t=sp.TOperation)),
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(1),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_VOTING,
        )

        token = DummyToken.DummyToken(10_000 * DECIMALS)

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}), token_address=token.address)

        scenario += dao
        scenario += token

        # ALICE up votes for proposal with invalid vote_value
        scenario += dao.vote(proposal_id=1, vote_value=2).run(
            sender=Addresses.ALICE,
            level=2,
            now=sp.timestamp(0),
            valid=False,
            exception=Errors.INVALID_VOTE_VALUE,
        )

    ################
    # vote_callback
    ################

    @sp.add_test(name="vote_callback fails for invalid state")
    def test():
        scenario = sp.test_scenario()

        dao = FlowDAO()
        scenario += dao

        scenario += dao.vote_callback(50_000 * DECIMALS).run(
            sender=Addresses.ALICE, valid=False, exception=Errors.INCORRECT_STATE
        )

    ###################
    # execute_proposal
    ###################

    @sp.add_test(name="execute_proposal executes the proposal_lambda")
    def test():
        scenario = sp.test_scenario()

        dummy_store = DummyStore.DummyStore(Addresses.ADMIN)

        def proposal_lambda(unit_param):
            sp.set_type(unit_param, sp.TUnit)
            c = sp.contract(sp.TNat, dummy_store.address, "modify_value").open_some()
            sp.result([sp.transfer_operation(sp.nat(5), sp.mutez(0), c)])

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=proposal_lambda,
            proposal_timelock=sp.record(activated=True, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_TIMELOCKED,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao
        scenario += dummy_store

        scenario += dummy_store.set_admin(dao.address)

        # Verify initial value of dummy_store
        scenario.verify(dummy_store.data.value == 0)

        # Execute the timelocked proposal
        scenario += dao.execute_proposal(1).run(now=sp.timestamp(1))

        # Verify value of dummy_store after proposal execution
        scenario.verify(dummy_store.data.value == 5)

        # Verify proposal status
        scenario.verify(dao.data.proposals[1].status == Proposal.PROPOSAL_STATUS_EXECUTED)

    @sp.add_test(name="execute_proposal fails if execution is performed too soon")
    def test():
        scenario = sp.test_scenario()

        dummy_store = DummyStore.DummyStore(Addresses.ADMIN)

        def proposal_lambda(unit_param):
            sp.set_type(unit_param, sp.TUnit)
            c = sp.contract(sp.TNat, dummy_store.address, "modify_value").open_some()
            sp.result([sp.transfer_operation(sp.nat(5), sp.mutez(0), c)])

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=proposal_lambda,
            proposal_timelock=sp.record(activated=True, ending=sp.timestamp(2)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_TIMELOCKED,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao
        scenario += dummy_store

        # Execute the timelocked proposal 1 second before timelock ending
        scenario += dao.execute_proposal(1).run(
            now=sp.timestamp(1), valid=False, exception=Errors.EXECUTING_TOO_SOON
        )

    @sp.add_test(name="execute_proposal fails if non timelocked proposal is executed")
    def test():
        scenario = sp.test_scenario()

        dummy_store = DummyStore.DummyStore(Addresses.ADMIN)

        def proposal_lambda(unit_param):
            sp.set_type(unit_param, sp.TUnit)
            c = sp.contract(sp.TNat, dummy_store.address, "modify_value").open_some()
            sp.result([sp.transfer_operation(sp.nat(5), sp.mutez(0), c)])

        proposal = sp.record(
            up_votes=0,
            down_votes=0,
            voters={},
            proposal_metadata="ipfs://xyz",
            proposal_lambda=proposal_lambda,
            proposal_timelock=sp.record(activated=False, ending=sp.timestamp(0)),
            voting_end=sp.timestamp(0),
            creator=Addresses.ALICE,
            origin_level=1,
            status=Proposal.PROPOSAL_STATUS_REJECTED,
        )

        dao = FlowDAO(proposals=sp.big_map(l={1: proposal}))

        scenario += dao
        scenario += dummy_store

        # Execute the timelocked proposal 1 second before timelock ending
        scenario += dao.execute_proposal(1).run(
            now=sp.timestamp(1), valid=False, exception=Errors.TIMELOCK_INACTIVE
        )

    ############################
    # set_governance_parameters
    ############################

    @sp.add_test(name="set_governance_parameters sets new values for the parameters")
    def test():
        scenario = sp.test_scenario()

        dao = FlowDAO()

        scenario += dao

        # Verify initial values for main governance parameters
        scenario.verify(dao.data.governance_parameters == GOVERNANCE_PARAMETERS)

        # Call the set_governance_parameters method
        scenario += dao.set_governance_parameters(
            sp.record(
                voting_period=sp.int(3 * DAY),
                timelock_period=sp.int(1 * DAY),
                quorum_votes=200_000 * DECIMALS,
                proposal_threshold=100_000 * DECIMALS,
            )
        ).run(sender=dao.address)

        # Verify the values for the parameters
        scenario.verify(
            dao.data.governance_parameters
            == sp.record(
                voting_period=sp.int(3 * DAY),
                timelock_period=sp.int(1 * DAY),
                quorum_votes=200_000 * DECIMALS,
                proposal_threshold=100_000 * DECIMALS,
            )
        )

    @sp.add_test(name="set_governance_parameters fails if sender is not DAO address")
    def test():
        scenario = sp.test_scenario()

        dao = FlowDAO()

        scenario += dao

        # Verify initial values for main governance parameters
        scenario.verify(dao.data.governance_parameters == GOVERNANCE_PARAMETERS)

        # Call the set_governance_parameters method
        scenario += dao.set_governance_parameters(
            sp.record(
                voting_period=sp.int(3 * DAY),
                timelock_period=sp.int(1 * DAY),
                quorum_votes=200_000 * DECIMALS,
                proposal_threshold=100_000 * DECIMALS,
            )
        ).run(sender=Addresses.ALICE, valid=False, exception=Errors.NOT_ALLOWED)

sp.add_compilation_target("flow_dao", FlowDAO())
