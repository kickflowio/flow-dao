# Fungible Assets - FA12
# Inspired by https://gitlab.com/tzip/tzip/blob/master/A/FA1.2.md

# This template was taken from https://smartpy.io/ide?template=FA1.2.py on 28th June, 2021.
# All changes made to the original template are denoted by CHANGED: <description>

# The contract was inspired by the Kolibri Governance Token contract & streamlined for use
# with Kickflow DAO 
# https://github.com/Hover-Labs/murmuration/blob/main/smart_contracts/token.py

import smartpy as sp

# CHANGED: Importing dummy addresses for testing
Addresses = sp.io.import_script_from_url("file:helpers/addresses.py")

# CHANGED: removed tzip16 metadata helper

# CHANGED: Add custom metadata values
TOKEN_METADATA = {
    "decimals": "18",
    "name": "Kickflow Governance Token",
    "symbol": "KFL",
    "icon": "https://avatars.githubusercontent.com/u/77055111?s=200&v=4",
}
CONTRACT_METADATA = {
    "": "ipfs://QmNaR3WbYeddJvsU5E1BiooEy24ejSMTAFUkppDsyu8rxV",
}

# A collection of error messages used in the contract.
class FA12_Error:
    def make(s):
        return "FA1.2_" + s

    NotAdmin = make("NotAdmin")
    InsufficientBalance = make("InsufficientBalance")
    UnsafeAllowanceChange = make("UnsafeAllowanceChange")
    Paused = make("Paused")
    NotAllowed = make("NotAllowed")

    # CHANGED: added errors
    MintingDisabled = make("MintingDisabled")
    BlockNotFinalized = make("BlockNotFinalized")
    SelfTransferNotAllowed = make('SelfTransferNotAllowed')


## ## Meta-Programming Configuration
##
## The `FA12_config` class holds the meta-programming configuration.
class FA12_config:
    def __init__(
        self,
        support_upgradable_metadata=True,
        use_token_metadata_offchain_view=True,
    ):
        # Whether the contract metadata can be upgradable or not.
        # When True a new entrypoint `change_metadata` will be added.
        self.support_upgradable_metadata = support_upgradable_metadata

        # Include offchain view for accessing the token metadata (requires TZIP-016 contract metadata)
        self.use_token_metadata_offchain_view = use_token_metadata_offchain_view


class FA12_common:
    def normalize_metadata(self, metadata):
        """
        Helper function to build metadata JSON (string => bytes).
        """
        meta = {}
        for key in metadata:
            meta[key] = sp.utils.bytes_of_string(metadata[key])

        return meta


class FA12_core(sp.Contract, FA12_common):
    def __init__(self, config, **extra_storage):
        self.config = config

        self.init(
            balances=sp.big_map(tvalue=sp.TRecord(approvals=sp.TMap(sp.TAddress, sp.TNat), balance=sp.TNat)),
            totalSupply=0,
            # CHANGED: added snapshots BIGMAP
            snapshots=sp.big_map(
                tkey=sp.TAddress,
                tvalue=sp.TMap(sp.TNat, sp.TRecord(level=sp.TNat, balance=sp.TNat).layout(("level", "balance"))),
            ),
            # CHANGED: added minting_disbaled
            mintingDisabled=False,
            **extra_storage
        )

    @sp.entry_point
    def transfer(self, params):
        sp.set_type(
            params,
            sp.TRecord(from_=sp.TAddress, to_=sp.TAddress, value=sp.TNat).layout(
                ("from_ as from", ("to_ as to", "value"))
            ),
        )
        sp.verify(
            (params.from_ == sp.sender)
            | (self.data.balances[params.from_].approvals[sp.sender] >= params.value),
            FA12_Error.NotAllowed,
        )

        # CHANGED: prohibit self transfers to prevent redundant checkpoint
        sp.verify(params.from_ != params.to_, FA12_Error.SelfTransferNotAllowed)

        self.addAddressIfNecessary(params.from_)
        self.addAddressIfNecessary(params.to_)
        sp.verify(
            self.data.balances[params.from_].balance >= params.value, FA12_Error.InsufficientBalance
        )
        self.data.balances[params.from_].balance = sp.as_nat(
            self.data.balances[params.from_].balance - params.value
        )
        self.data.balances[params.to_].balance += params.value

        # CHANGE: take from_ address snapshot
        self.takeSnapshot(params.from_)

        # CHANGE: take to_ address snapshot
        self.takeSnapshot(params.to_)

        sp.if params.from_ != sp.sender:
            self.data.balances[params.from_].approvals[sp.sender] = sp.as_nat(
                self.data.balances[params.from_].approvals[sp.sender] - params.value
            )

    @sp.entry_point
    def approve(self, params):
        sp.set_type(params, sp.TRecord(spender=sp.TAddress, value=sp.TNat).layout(("spender", "value")))
        self.addAddressIfNecessary(sp.sender)
        alreadyApproved = self.data.balances[sp.sender].approvals.get(params.spender, 0)
        sp.verify((alreadyApproved == 0) | (params.value == 0), FA12_Error.UnsafeAllowanceChange)
        self.data.balances[sp.sender].approvals[params.spender] = params.value

    def addAddressIfNecessary(self, address):
        sp.if ~self.data.balances.contains(address):
            self.data.balances[address] = sp.record(balance=0, approvals={})

    @sp.utils.view(sp.TNat)
    def getBalance(self, params):
        sp.if self.data.balances.contains(params):
            sp.result(self.data.balances[params].balance)
        sp.else:
            sp.result(sp.nat(0))

    @sp.utils.view(sp.TNat)
    def getAllowance(self, params):
        sp.if self.data.balances.contains(params.owner):
            sp.result(self.data.balances[params.owner].approvals.get(params.spender, 0))
        sp.else:
            sp.result(sp.nat(0))

    @sp.utils.view(sp.TNat)
    def getTotalSupply(self, params):
        sp.set_type(params, sp.TUnit)
        sp.result(self.data.totalSupply)

    # CHANGED: removed is_paused & is_administrator function


# CHANGED: Add FA12_snapshot class
class FA12_snapshot(FA12_core):
    # Takes the snapshot of the balance of an address at the current level
    @sp.sub_entry_point
    def takeSnapshot(self, address):
        sp.set_type(address, sp.TAddress)

        # Add a base level balance snapshot if not already present
        sp.if ~self.data.snapshots.contains(address):
            self.data.snapshots[address] = {0: sp.record(level=0, balance=0)}

        snapshots_map = self.data.snapshots[address]
        map_length = sp.len(snapshots_map)

        # If the a snapshot is already taken at the same level, simply overwrite it
        sp.if snapshots_map[sp.as_nat(map_length - 1)].level == sp.level:
            snapshots_map[sp.as_nat(map_length - 1)].balance = self.data.balances[address].balance
        sp.else:
            snapshots_map[map_length] = sp.record(
                level=sp.level, balance=self.data.balances[address].balance
            )

    # Allows viewing of an address's balance at a certain level
    @sp.utils.view(sp.TNat)
    def getBalanceAt(self, params):
        sp.set_type(params, sp.TRecord(address=sp.TAddress, level=sp.TNat))

        sp.verify(params.level < sp.level, FA12_Error.BlockNotFinalized)

        sp.if ~self.data.snapshots.contains(params.address):
            sp.result(sp.nat(0))
        sp.else:
            snapshots_map = self.data.snapshots[params.address]
            
            # If requested level is greater than last level snapshot, return that
            sp.if params.level >= snapshots_map[sp.as_nat(sp.len(snapshots_map) - 1)].level:
                sp.result(snapshots_map[sp.as_nat(sp.len(snapshots_map) - 1)].balance)
            sp.else:
                # Binary search the appropriate snapshot
                low = sp.local("low", sp.nat(0))
                high = sp.local("high", sp.as_nat(sp.len(snapshots_map) - 2))
                mid = sp.local("mid", sp.nat(0))

                sp.while (low.value < high.value) & (snapshots_map[mid.value].level != params.level):
                    mid.value = (low.value + high.value + 1) // 2
                    sp.if snapshots_map[mid.value].level > params.level:
                        high.value = sp.as_nat(mid.value - 1)
                    sp.if snapshots_map[mid.value].level < params.level:
                        low.value = mid.value
                sp.if snapshots_map[mid.value].level == params.level:
                    sp.result(snapshots_map[mid.value].balance)
                sp.else:
                    sp.result(snapshots_map[low.value].balance)


class FA12_mint(FA12_core):
    @sp.entry_point
    def mint(self, params):
        sp.set_type(params, sp.TRecord(address=sp.TAddress, value=sp.TNat))
        sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)
        sp.verify(~self.data.mintingDisabled, FA12_Error.MintingDisabled)
        self.addAddressIfNecessary(params.address)
        self.data.balances[params.address].balance += params.value
        self.data.totalSupply += params.value

        # CHANGED: take snapshot of address balance
        self.takeSnapshot(params.address)

    # CHANGED: added disable_mint entrypoint
    @sp.entry_point
    def disableMint(self):
        sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)
        self.data.mintingDisabled = True

    # CHANGED: removed burn entrypoint


class FA12_administrator(FA12_core):
    def is_administrator(self, sender):
        return sender == self.data.administrator

    @sp.entry_point
    def setAdministrator(self, params):
        sp.set_type(params, sp.TAddress)
        sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)
        self.data.administrator = params

    @sp.utils.view(sp.TAddress)
    def getAdministrator(self, params):
        sp.set_type(params, sp.TUnit)
        sp.result(self.data.administrator)


# CHANGED: Removed FA12_Pause class


class FA12_token_metadata(FA12_core):
    def set_token_metadata(self, metadata):
        """
        Store the token_metadata values in a big-map annotated %token_metadata
        of type (big_map nat (pair (nat %token_id) (map %token_info string bytes))).
        """
        self.update_initial_storage(
            token_metadata=sp.big_map(
                {0: sp.record(token_id=0, token_info=self.normalize_metadata(metadata))},
                tkey=sp.TNat,
                tvalue=sp.TRecord(token_id=sp.TNat, token_info=sp.TMap(sp.TString, sp.TBytes)),
            )
        )


class FA12_contract_metadata(FA12_core):
    # CHANGED: removed tzip16 metadata logging function

    def set_contract_metadata(self, metadata):
        """
        Set contract metadata
        """
        self.update_initial_storage(metadata=sp.big_map(self.normalize_metadata(metadata)))

        if self.config.support_upgradable_metadata:

            def update_metadata(self, key, value):
                """
                An entry-point to allow the contract metadata to be updated.

                Can be removed with `FA12_config(support_upgradable_metadata = False, ...)`
                """
                sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)
                self.data.metadata[key] = value

            self.update_metadata = sp.entry_point(update_metadata)


class FA12(
    FA12_mint,
    FA12_administrator,
    FA12_token_metadata,
    FA12_contract_metadata,
    FA12_snapshot,
    FA12_core,
):
    def __init__(
        self,
        # CHANGED: added default values
        admin=Addresses.ADMIN,
        config=FA12_config(),
        token_metadata=TOKEN_METADATA,
        contract_metadata=CONTRACT_METADATA,
    ):
        # CHANGED: removed paused
        FA12_core.__init__(self, config, administrator=admin)

        # CHANGED: removed not-empty checks for token_metadata & contract_metadata

        self.usingTokenMetadata = True
        self.set_token_metadata(token_metadata)
        self.set_contract_metadata(contract_metadata)

        # CHANGED: removed metadata logger


class Viewer(sp.Contract):
    def __init__(self, t):
        self.init(last=sp.none)
        self.init_type(sp.TRecord(last=sp.TOption(t)))

    @sp.entry_point
    def target(self, params):
        self.data.last = sp.some(params)


# CHANGED: Removed Off-chain view testing class

if "templates" not in __name__:

    @sp.add_test(name="getBalanceAt returns 0 when no snapshots are present")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        scenario += token.getBalanceAt(
            (sp.record(level = 5, address = Addresses.ALICE), viewer.typed.target)
        ).run(level = 10)

        scenario.verify(viewer.data.last.open_some() == sp.nat(0))


    @sp.add_test(name="getBalanceAt reverts when unfinalized level is passed")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        currentLevel = 3
        requestLevel = 5

        scenario += token.getBalanceAt(
            (sp.record(level = requestLevel, address = Addresses.ALICE), viewer.typed.target)
        ).run(level = currentLevel, valid = False)
    

    @sp.add_test('getBalance at returns 0 if requested level is before first snapshot')
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        requestLevel = 2
        mintLevel1 = 4
        mintLevel2 = 6
        mintLevel3 = 8
        currentLevel = 10

        # Mint tokens for ALICE at mintLevels
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  10
        ).run(sender = Addresses.ADMIN, level = mintLevel1)
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  10
        ).run(sender = Addresses.ADMIN, level = mintLevel2)
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  10
        ).run(sender = Addresses.ADMIN, level = mintLevel3)

        scenario += token.getBalanceAt(
            (sp.record(level = requestLevel, address = Addresses.ALICE), viewer.typed.target)
        ).run(level = currentLevel)

        scenario.verify(viewer.data.last.open_some() == sp.nat(0))

    @sp.add_test('getBalance returns last balance if requested level is after last snapshot')
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        requestLevel = 4 
        mintLevel = 2
        currentLevel = 6

        # Mint tokens for ALICE at mintLevel
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  10
        ).run(sender = Addresses.ADMIN, level = mintLevel)

        scenario += token.getBalanceAt(
            (sp.record(level = requestLevel, address = Addresses.ALICE), viewer.typed.target)
        ).run(level = currentLevel)

        scenario.verify(viewer.data.last.open_some() == sp.nat(10))


    # Even number of snapshot: BASE SNAPSHOT + 5 TRANSFER SNAPSHOTS
    @sp.add_test('getBalanceAt returns appropriate balance for even number of snapshots')
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # Mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 1)

        # Alice transfers 10 tokens to BOB at 5 levels
        #
        # Level  |  Bob's Balance
        #   2           10
        #   4           20      
        #   6           30
        #   8           40
        #  10           50

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 2)

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 4)

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 6)

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 8)

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 10)

        # Verify number of snapshots taken for Bob (5 + 1 base snapshot)
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 6)

        # Verify balance snapshot from level 1 -> 11
        currentLevel = 12

        # Level 1
        scenario += token.getBalanceAt(
            (sp.record(level = 1, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(0))

        # Level 2
        scenario += token.getBalanceAt(
            (sp.record(level = 2, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(10))

        # Level 3
        scenario += token.getBalanceAt(
            (sp.record(level = 3, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(10))

        # Level 4
        scenario += token.getBalanceAt(
            (sp.record(level = 4, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(20))

        # Level 5
        scenario += token.getBalanceAt(
            (sp.record(level = 5, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(20))

        # Level 6
        scenario += token.getBalanceAt(
            (sp.record(level = 6, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(30))

        # Level 7
        scenario += token.getBalanceAt(
            (sp.record(level = 7, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(30))

        # Level 8
        scenario += token.getBalanceAt(
            (sp.record(level = 8, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(40))

        # Level 9
        scenario += token.getBalanceAt(
            (sp.record(level = 9, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(40))

        # Level 10
        scenario += token.getBalanceAt(
            (sp.record(level = 10, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(50))

        # Level 11
        scenario += token.getBalanceAt(
            (sp.record(level = 11, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(50))
    
    # Odd number of snapshots: BASE SNAPSHOT + 4 TRANSFER SNAPSHOTS
    @sp.add_test('getBalanceAt returns appropriate balance for odd number of snapshots')
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # Mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 1)

        # Alice transfers 10 tokens to BOB at 4 levels
        #
        # Level  |  Bob's Balance
        #   2           10
        #   4           20      
        #   6           30
        #   8           40

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 2)

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 4)

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 6)

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(sender = Addresses.ALICE, level = 8)

        # Verify number of snapshots taken for Bob (5 + 1 base snapshot)
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 5)

        # Verify balance snapshot from level 1 -> 9
        currentLevel = 12

        # Level 1
        scenario += token.getBalanceAt(
            (sp.record(level = 1, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(0))

        # Level 2
        scenario += token.getBalanceAt(
            (sp.record(level = 2, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(10))

        # Level 3
        scenario += token.getBalanceAt(
            (sp.record(level = 3, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(10))

        # Level 4
        scenario += token.getBalanceAt(
            (sp.record(level = 4, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(20))

        # Level 5
        scenario += token.getBalanceAt(
            (sp.record(level = 5, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(20))

        # Level 6
        scenario += token.getBalanceAt(
            (sp.record(level = 6, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(30))

        # Level 7
        scenario += token.getBalanceAt(
            (sp.record(level = 7, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(30))

        # Level 8
        scenario += token.getBalanceAt(
            (sp.record(level = 8, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(40))

        # Level 9
        scenario += token.getBalanceAt(
            (sp.record(level = 9, address = Addresses.BOB), viewer.typed.target)
        ).run(level = currentLevel)
        scenario.verify(viewer.data.last.open_some() == sp.nat(40))

    ##############################
    # Transfer tests for snapshots
    ##############################

    @sp.add_test(name = "transfer takes the correct number of snapshots")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # Mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 1)

        # ALICE transfers to BOB
        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(
            sender = Addresses.ALICE,
            level = 2
        )

        # Verify number of snapshots for ALICE, BOB & JOHN
        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 3) # Base + mint + transfer
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 2) # Base + transfer
        scenario.verify(~token.data.snapshots.contains(Addresses.JOHN)) # No snapshots

        # ALICE transfers to JOHN
        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.JOHN,
            value = 10
        ).run(
            sender = Addresses.ALICE,
            level = 3
        )

        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 4) # Base + mint + 2 transfers
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 2) # Base + transfer
        scenario.verify(sp.len(token.data.snapshots[Addresses.JOHN]) == 2) # Base + transfer

        # BOB transfers to JOHN
        scenario += token.transfer(
            from_ = Addresses.BOB,
            to_ = Addresses.JOHN,
            value = 10
        ).run(
            sender = Addresses.BOB,
            level = 4
        )

        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 4) # Base + mint + 2 transfers
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 3) # Base + 2 transfers
        scenario.verify(sp.len(token.data.snapshots[Addresses.JOHN]) == 3) # Base + 2 transfers

        # Correct history is recorded for ALICE
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.ALICE][1].balance == 100)
        scenario.verify(token.data.snapshots[Addresses.ALICE][1].level == 1)

        scenario.verify(token.data.snapshots[Addresses.ALICE][2].balance == 90)
        scenario.verify(token.data.snapshots[Addresses.ALICE][2].level == 2)

        scenario.verify(token.data.snapshots[Addresses.ALICE][3].balance == 80)
        scenario.verify(token.data.snapshots[Addresses.ALICE][3].level == 3)

        # Correct history is recorded for BOB
        scenario.verify(token.data.snapshots[Addresses.BOB][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.BOB][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.BOB][1].balance == 10)
        scenario.verify(token.data.snapshots[Addresses.BOB][1].level == 2)

        scenario.verify(token.data.snapshots[Addresses.BOB][2].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.BOB][2].level == 4)

        # Correct history is recorded for JOHN
        scenario.verify(token.data.snapshots[Addresses.JOHN][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.JOHN][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.JOHN][1].balance == 10)
        scenario.verify(token.data.snapshots[Addresses.JOHN][1].level == 3)

        scenario.verify(token.data.snapshots[Addresses.JOHN][2].balance == 20)
        scenario.verify(token.data.snapshots[Addresses.JOHN][2].level == 4)
    
    @sp.add_test(name = "transfer via approval takes the correct number of snapshots")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # Mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 1)

        # Alice approves BOB
        scenario += token.approve(
            spender = Addresses.BOB,
            value = 100
        ).run(
            sender = Addresses.ALICE
        )

        # BOB approves JOHN
        scenario += token.approve(
            spender = Addresses.JOHN,
            value = 100
        ).run(
            sender = Addresses.BOB
        )

        # BOB transfer from ALICE to himself
        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 10
        ).run(
            sender = Addresses.BOB,
            level = 2
        )

        # Verify number of snapshots for ALICE, BOB & JOHN
        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 3) # Base + mint + transfer
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 2) # Base + transfer
        scenario.verify(~token.data.snapshots.contains(Addresses.JOHN)) # No snapshots

        # BOB transfers from ALICE to JOHN
        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.JOHN,
            value = 10
        ).run(
            sender = Addresses.BOB,
            level = 3
        )

        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 4) # Base + mint + 2 transfers
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 2) # Base + transfer
        scenario.verify(sp.len(token.data.snapshots[Addresses.JOHN]) == 2) # Base + transfer

        # JOHN transfer from BOB to himself
        scenario += token.transfer(
            from_ = Addresses.BOB,
            to_ = Addresses.JOHN,
            value = 10
        ).run(
            sender = Addresses.JOHN,
            level = 4
        )

        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 4) # Base + mint + 2 transfers
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 3) # Base + 2 transfers
        scenario.verify(sp.len(token.data.snapshots[Addresses.JOHN]) == 3) # Base + 2 transfers

        # Correct history is recorded for ALICE
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.ALICE][1].balance == 100)
        scenario.verify(token.data.snapshots[Addresses.ALICE][1].level == 1)

        scenario.verify(token.data.snapshots[Addresses.ALICE][2].balance == 90)
        scenario.verify(token.data.snapshots[Addresses.ALICE][2].level == 2)

        scenario.verify(token.data.snapshots[Addresses.ALICE][3].balance == 80)
        scenario.verify(token.data.snapshots[Addresses.ALICE][3].level == 3)

        # Correct history is recorded for BOB
        scenario.verify(token.data.snapshots[Addresses.BOB][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.BOB][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.BOB][1].balance == 10)
        scenario.verify(token.data.snapshots[Addresses.BOB][1].level == 2)

        scenario.verify(token.data.snapshots[Addresses.BOB][2].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.BOB][2].level == 4)

        # Correct history is recorded for JOHN
        scenario.verify(token.data.snapshots[Addresses.JOHN][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.JOHN][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.JOHN][1].balance == 10)
        scenario.verify(token.data.snapshots[Addresses.JOHN][1].level == 3)

        scenario.verify(token.data.snapshots[Addresses.JOHN][2].balance == 20)
        scenario.verify(token.data.snapshots[Addresses.JOHN][2].level == 4)

    @sp.add_test(name = "transfer does not take 2 snapshots for same level")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # Mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 1)

        # ALICE transfers to BOB twice and same level
        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 20
        ).run(
            sender = Addresses.ALICE,
            level = 2
        )

        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.BOB,
            value = 30
        ).run(
            sender = Addresses.ALICE,
            level = 2
        )

        # ALICE transfers to JOHN at same level
        scenario += token.transfer(
            from_ = Addresses.ALICE,
            to_ = Addresses.JOHN,
            value = 50
        ).run(
            sender = Addresses.ALICE,
            level = 2
        )

        # Verify number of snapshots
        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 3) # Base + Mint + transfer 
        scenario.verify(sp.len(token.data.snapshots[Addresses.BOB]) == 2) # Base + transfer
        scenario.verify(sp.len(token.data.snapshots[Addresses.JOHN]) == 2) # Base + transfer

        # ALICE has the correct history
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.ALICE][1].balance == 100)
        scenario.verify(token.data.snapshots[Addresses.ALICE][1].level == 1)

        scenario.verify(token.data.snapshots[Addresses.ALICE][2].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.ALICE][2].level == 2)


        # BOB has correct history
        scenario.verify(token.data.snapshots[Addresses.BOB][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.BOB][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.BOB][1].balance == 50)
        scenario.verify(token.data.snapshots[Addresses.BOB][1].level == 2)

        # JOHN has correct history
        scenario.verify(token.data.snapshots[Addresses.JOHN][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.JOHN][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.JOHN][1].balance == 50)
        scenario.verify(token.data.snapshots[Addresses.JOHN][1].level == 2)

    ################
    # Minting tests 
    ################
    @sp.add_test(name = "snapshots are taken correctly for multiple mints")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # Mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 1)

        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 3)

        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN, level = 5)

        # Verify number of snapshots
        scenario.verify(sp.len(token.data.snapshots[Addresses.ALICE]) == 4) # Base + 3 mints

        # ALICE has correct history
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].balance == 0)
        scenario.verify(token.data.snapshots[Addresses.ALICE][0].level == 0)

        scenario.verify(token.data.snapshots[Addresses.ALICE][1].balance == 100)
        scenario.verify(token.data.snapshots[Addresses.ALICE][1].level == 1)

        scenario.verify(token.data.snapshots[Addresses.ALICE][2].balance == 200)
        scenario.verify(token.data.snapshots[Addresses.ALICE][2].level == 3)

        scenario.verify(token.data.snapshots[Addresses.ALICE][3].balance == 300)
        scenario.verify(token.data.snapshots[Addresses.ALICE][3].level == 5)

    @sp.add_test(name = "not allowed to mint when minting is disabled")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # Mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(sender = Addresses.ADMIN)

        # Disable mint
        scenario += token.disableMint().run(sender = Addresses.ADMIN)

        # Mint after disabling
        scenario += token.mint(
            address = Addresses.ALICE,
            value = 100
        ).run(
            sender = Addresses.ADMIN,
            valid = False
        )
    
    @sp.add_test(name = "only admin can mint and disable minting")
    def test():
        scenario = sp.test_scenario()

        token = FA12()
        viewer = Viewer(sp.TNat)

        scenario += token
        scenario += viewer

        # BOB tries to mint tokens for ALICE
        scenario += token.mint(
            address = Addresses.ALICE, 
            value =  100
        ).run(
            sender = Addresses.BOB,
            valid = False
        )

        # BOB tries to disable minting
        scenario += token.disableMint().run(sender = Addresses.BOB, valid = False)

    # Original SmartPy test suite
    @sp.add_test(name="Smartpy tests")
    def test():
        scenario = sp.test_scenario()
        scenario.h1("FA1.2 template - Fungible assets")

        scenario.table_of_contents()

        # sp.test_account generates ED25519 key-pairs deterministically:
        admin = sp.test_account("Administrator")
        alice = sp.test_account("Alice")
        bob   = sp.test_account("Robert")

        # Let's display the accounts:
        scenario.h1("Accounts")
        scenario.show([admin, alice, bob])
        
        # CHANGED: removed existing token and contract metadata
        c1 = FA12(
            admin.address,
        )
        scenario += c1

        # CHANGED: removed metadata viewing test

        scenario.h1("Attempt to update metadata")
        scenario.verify(
            c1.data.metadata[""] == sp.utils.bytes_of_string("ipfs://QmNaR3WbYeddJvsU5E1BiooEy24ejSMTAFUkppDsyu8rxV")
        )
        c1.update_metadata(key = "", value = sp.bytes("0x00")).run(sender = admin)
        scenario.verify(c1.data.metadata[""] == sp.bytes("0x00"))

        scenario.h1("Entry points")
        scenario.h2("Admin mints a few coins")
        c1.mint(address = alice.address, value = 12).run(sender = admin)
        c1.mint(address = alice.address, value = 3).run(sender = admin)
        c1.mint(address = alice.address, value = 3).run(sender = admin)
        scenario.h2("Alice transfers to Bob")
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4).run(sender = alice)
        scenario.verify(c1.data.balances[alice.address].balance == 14)
        scenario.h2("Bob tries to transfer from Alice but he doesn't have her approval")
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4).run(sender = bob, valid = False)
        scenario.h2("Alice approves Bob and Bob transfers")
        c1.approve(spender = bob.address, value = 5).run(sender = alice)
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4).run(sender = bob)
        scenario.h2("Bob tries to over-transfer from Alice")
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4).run(sender = bob, valid = False)
        
        # CHANGED: removed burning & pause test

        # CHANGED: modified equality values accordingly
        scenario.verify(c1.data.totalSupply == 18)
        scenario.verify(c1.data.balances[alice.address].balance == 10)
        scenario.verify(c1.data.balances[bob.address].balance == 8)

        scenario.h1("Views")
        scenario.h2("Balance")
        view_balance = Viewer(sp.TNat)
        scenario += view_balance
        c1.getBalance((alice.address, view_balance.typed.target))
        scenario.verify_equal(view_balance.data.last, sp.some(10))

        scenario.h2("Administrator")
        view_administrator = Viewer(sp.TAddress)
        scenario += view_administrator
        c1.getAdministrator((sp.unit, view_administrator.typed.target))
        scenario.verify_equal(view_administrator.data.last, sp.some(admin.address))

        scenario.h2("Total Supply")
        view_totalSupply = Viewer(sp.TNat)
        scenario += view_totalSupply
        c1.getTotalSupply((sp.unit, view_totalSupply.typed.target))
        scenario.verify_equal(view_totalSupply.data.last, sp.some(18))

        scenario.h2("Allowance")
        view_allowance = Viewer(sp.TNat)
        scenario += view_allowance
        c1.getAllowance((sp.record(owner = alice.address, spender = bob.address), view_allowance.typed.target))
        scenario.verify_equal(view_allowance.data.last, sp.some(1))

    sp.add_compilation_target("fa12_token", FA12())
