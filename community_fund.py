import smartpy as sp

Addresses = sp.io.import_script_from_url("file:helpers/addresses.py")
Errors = sp.io.import_script_from_url("file:types/errors.py")
DummyStore = sp.io.import_script_from_url("file:helpers/dummy_store.py")
FA12 = sp.io.import_script_from_url("file:helpers/fa12.py")
FA2 = sp.io.import_script_from_url("file:helpers/fa2.py")

########
# Types
########

FA2_TRANSFER_TXS_TYPE = sp.TList(
    sp.TRecord(to_=sp.TAddress, token_id=sp.TNat, amount=sp.TNat).layout(("to_", ("token_id", "amount")))
)

###########
# Contract
###########


class CommunityFund(sp.Contract):
    def __init__(self, admin=Addresses.ADMIN):
        # The admin would typically be the DAO contract, in the case of Kickflow.
        self.init(admin=admin)

    @sp.entry_point
    def transfer_tez(self, params):
        sp.set_type(params, sp.TRecord(value=sp.TMutez, dest=sp.TAddress).layout(("value", "dest")))

        # Verify that sender is the admin
        sp.verify(sp.sender == self.data.admin, Errors.NOT_ALLOWED)

        # Transfer tez to mentioned destination
        sp.send(params.dest, params.value)

    @sp.entry_point
    def transfer_fa12(self, params):
        sp.set_type(
            params,
            sp.TRecord(token_address=sp.TAddress, value=sp.TNat, dest=sp.TAddress).layout(
                ("token_address", ("value", "dest"))
            ),
        )

        # Verify that sender is the admin
        sp.verify(sp.sender == self.data.admin, Errors.NOT_ALLOWED)

        # Transfer tokens
        c = sp.contract(
            sp.TRecord(from_=sp.TAddress, to_=sp.TAddress, value=sp.TNat).layout(
                ("from_ as from", ("to_ as to", "value"))
            ),
            params.token_address,
            "transfer",
        ).open_some(Errors.INVALID_TOKEN_CONTRACT)
        sp.transfer(
            sp.record(from_=sp.self_address, to_=params.dest, value=params.value),
            sp.mutez(0),
            c,
        )

    @sp.entry_point
    def transfer_fa2(self, params):
        sp.set_type(
            params,
            sp.TRecord(token_address=sp.TAddress, txs=FA2_TRANSFER_TXS_TYPE).layout(("token_address", "txs")),
        )

        # Verify that sender is the admin
        sp.verify(sp.sender == self.data.admin, Errors.NOT_ALLOWED)

        # Transfer tokens
        c = sp.contract(
            sp.TList(sp.TRecord(from_=sp.TAddress, txs=FA2_TRANSFER_TXS_TYPE).layout(("from_", "txs"))),
            params.token_address,
            "transfer",
        ).open_some(Errors.INVALID_TOKEN_CONTRACT)
        sp.transfer(
            sp.list([sp.record(from_=sp.self_address, txs=params.txs)]),
            sp.mutez(0),
            c,
        )

    @sp.entry_point
    def set_delegate(self, new_delegate):
        sp.set_type(new_delegate, sp.TOption(sp.TKeyHash))

        # Verify that sender is the admin
        sp.verify(sp.sender == self.data.admin, Errors.NOT_ALLOWED)

        # Set the delegate
        sp.set_delegate(new_delegate)


if __name__ == "__main__":

    ###############
    # transfer_tez
    ###############

    @sp.add_test(name="transfer_tez correctly transfers tez")
    def test():
        scenario = sp.test_scenario()

        community_fund = CommunityFund()
        dummy = DummyStore.DummyStore(admin=Addresses.ADMIN)

        community_fund.set_initial_balance(sp.tez(10))

        scenario += community_fund
        scenario += dummy

        # Call transfer_tez
        scenario += community_fund.transfer_tez(
            value=sp.tez(10),
            dest=dummy.address,
        ).run(sender=Addresses.ADMIN)

        scenario.verify(community_fund.balance == sp.tez(0))
        scenario.verify(dummy.balance == sp.tez(10))

    @sp.add_test(name="transfer_tez fails if not called by admin")
    def test():
        scenario = sp.test_scenario()

        community_fund = CommunityFund()
        dummy = DummyStore.DummyStore(admin=Addresses.ADMIN)

        scenario += community_fund
        scenario += dummy

        # Call transfer_tez
        scenario += community_fund.transfer_tez(
            value=sp.tez(10),
            dest=dummy.address,
        ).run(sender=Addresses.ALICE, valid=False, exception=Errors.NOT_ALLOWED)

    ################
    # transfer_fa12
    ################

    @sp.add_test(name="transfer_fa12 correctly transfers tokens")
    def test():
        scenario = sp.test_scenario()

        token_receiver = sp.test_account("receiver")

        fa12 = FA12.FA12(admin=Addresses.ADMIN)
        community_fund = CommunityFund()

        scenario += fa12
        scenario += community_fund

        # Mint for community fund
        scenario += fa12.mint(address=community_fund.address, value=100).run(sender=Addresses.ADMIN)

        scenario.verify(fa12.data.balances[community_fund.address].balance == 100)

        # Transfer to receiver
        scenario += community_fund.transfer_fa12(
            token_address=fa12.address, value=100, dest=token_receiver.address
        ).run(sender=Addresses.ADMIN)

        # Verify correctness of transfer
        scenario.verify(fa12.data.balances[community_fund.address].balance == 0)
        scenario.verify(fa12.data.balances[token_receiver.address].balance == 100)

    @sp.add_test(name="transfer_fa12 fails if not called by admin")
    def test():
        scenario = sp.test_scenario()

        token_receiver = sp.test_account("receiver")

        fa12 = FA12.FA12(admin=Addresses.ADMIN)
        community_fund = CommunityFund()

        scenario += fa12
        scenario += community_fund

        # Mint for community fund
        scenario += fa12.mint(address=community_fund.address, value=100).run(sender=Addresses.ADMIN)

        scenario.verify(fa12.data.balances[community_fund.address].balance == 100)

        # ALICE tries to transfer to receiver
        scenario += community_fund.transfer_fa12(
            token_address=fa12.address, value=100, dest=token_receiver.address
        ).run(sender=Addresses.ALICE, valid=False, exception=Errors.NOT_ALLOWED)

    ###############
    # transfer_fa2
    ###############

    @sp.add_test(name="transfer_fa2 correctly transfer tokens")
    def test():
        scenario = sp.test_scenario()

        token_receiver = sp.test_account("receiver")

        fa2 = FA2.FA2(
            config=FA2.FA2_config(),
            metadata=sp.utils.metadata_of_url("https://example.com"),
            admin=Addresses.ADMIN,
        )
        community_fund = CommunityFund()

        scenario += fa2
        scenario += community_fund

        # Mint for community fund
        scenario += fa2.mint(
            address=community_fund.address,
            amount=100,
            metadata=FA2.FA2.make_metadata(name="NFT", decimals=18, symbol="NFT"),
            token_id=0,
        ).run(sender=Addresses.ADMIN)

        # Transfer fa2 token to receiver
        scenario += community_fund.transfer_fa2(
            token_address=fa2.address,
            txs=sp.list(
                [
                    sp.record(
                        to_=token_receiver.address,
                        token_id=0,
                        amount=100,
                    )
                ]
            ),
        ).run(sender=Addresses.ADMIN)

        # Verify correctness of transfer
        scenario.verify(fa2.data.ledger[(token_receiver.address, 0)].balance == 100)
        scenario.verify(fa2.data.ledger[(community_fund.address, 0)].balance == 0)

    @sp.add_test(name="transfer_fa2 fails if not called by admin")
    def test():
        scenario = sp.test_scenario()

        token_receiver = sp.test_account("receiver")

        fa2 = FA2.FA2(
            config=FA2.FA2_config(),
            metadata=sp.utils.metadata_of_url("https://example.com"),
            admin=Addresses.ADMIN,
        )
        community_fund = CommunityFund()

        scenario += fa2
        scenario += community_fund

        # Mint for community fund
        scenario += fa2.mint(
            address=community_fund.address,
            amount=100,
            metadata=FA2.FA2.make_metadata(name="NFT", decimals=18, symbol="NFT"),
            token_id=0,
        ).run(sender=Addresses.ADMIN)

        # ALICE tries to transfer fa2 token to receiver
        scenario += community_fund.transfer_fa2(
            token_address=fa2.address,
            txs=sp.list(
                [
                    sp.record(
                        to_=token_receiver.address,
                        token_id=0,
                        amount=100,
                    )
                ]
            ),
        ).run(
            sender=Addresses.ALICE,
            valid=False,
            exception=Errors.NOT_ALLOWED,
        )

    ###############
    # set_delegate
    ###############

    @sp.add_test(name="set_delegate sets the delegate correctly")
    def test():
        scenario = sp.test_scenario()

        community_fund = CommunityFund()

        scenario += community_fund

        delegate = sp.some(sp.key_hash("tz1abmz7jiCV2GH2u81LRrGgAFFgvQgiDiaf"))

        # Set delegate
        scenario += community_fund.set_delegate(delegate).run(
            sender=Addresses.ADMIN,
            voting_powers={sp.key_hash("tz1abmz7jiCV2GH2u81LRrGgAFFgvQgiDiaf"): 10},
        )

        # Verify that delegate is set
        scenario.verify(community_fund.baker.open_some() == delegate.open_some())

    @sp.add_test(name="set_delegate fails if not called by admin")
    def test():
        scenario = sp.test_scenario()

        community_fund = CommunityFund()

        scenario += community_fund

        delegate = sp.some(sp.key_hash("tz1abmz7jiCV2GH2u81LRrGgAFFgvQgiDiaf"))

        # ALICE tries to set delegate
        scenario += community_fund.set_delegate(delegate).run(
            sender=Addresses.ALICE,
            voting_powers={sp.key_hash("tz1abmz7jiCV2GH2u81LRrGgAFFgvQgiDiaf"): 10},
            valid=False,
            exception=Errors.NOT_ALLOWED,
        )

    sp.add_compilation_target("community_fund", CommunityFund())
