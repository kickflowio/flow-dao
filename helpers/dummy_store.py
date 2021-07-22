import smartpy as sp


class DummyStore(sp.Contract):
    def __init__(self, admin):
        self.init(admin=admin, value=sp.nat(0))

    @sp.entry_point
    def set_admin(self, admin):
        sp.set_type(admin, sp.TAddress)
        self.data.admin = admin

    @sp.entry_point
    def modify_value(self, param):
        sp.set_type(param, sp.TNat)
        sp.verify(sp.sender == self.data.admin, "NOT ALLOWED")
        self.data.value = param

    @sp.entry_point
    def default(self):
        pass
