from decouple import config
LNVENDOR = config("LNVENDOR", cast=str, default="LND")
if LNVENDOR == "LND":
    from api.lightning.lnd import LNDNode
    LNNode = LNDNode
elif LNVENDOR == "CLN":
    from api.lightning.cln import CLNNode
    LNNode = CLNNode
elif LNVENDOR == "XMR":
    from api.lightning.xmr import XMRNode
    LNNode = XMRNode
else:
    raise ValueError(
        f'Invalid vendor: {LNVENDOR}. Must be "LND", "CLN" or "XMR"'
    )
