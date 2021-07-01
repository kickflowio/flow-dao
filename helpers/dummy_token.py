import smartpy as sp


class DummyToken(sp.Contract):
    def __init__(self, val):
        self.init(val=val)

    @sp.entry_point
    def set_val(self, param):
        sp.set_type(param, sp.TNat)
        self.data.val = param

    @sp.utils.view(sp.TNat)
    def getBalanceAt(self, params):
        sp.set_type(params, sp.TRecord(address=sp.TAddress, level=sp.TNat))
        sp.result(self.data.val)
