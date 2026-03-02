# RoboSats-XMR

A fork of [RoboSats](https://github.com/RoboSats/robosats) with Monero (XMR) support instead of Bitcoin/Lightning Network.

## What Changed

- Replaced Lightning Network backend with Monero wallet RPC
- Uses Monero subaddresses as escrow (replaces Lightning hold invoices)
- 10-block confirmation lock (replaces Lightning HTLC lock)
- Subaddress index stored in database (persistent, not /tmp)
- XMR price feeds via cryptocompare API
- All frontend references updated from BTC/Sats to XMR/Piconeros

## How The Escrow Works

Lightning hold invoices allow funds to be locked but not settled until a preimage is revealed. Monero has no native equivalent, so we use:

1. **Lock** → Generate unique subaddress per trade, wait for 10-block confirmation
2. **Settle** → Send funds from subaddress to buyer address
3. **Cancel** → Send funds from subaddress back to original sender

## Quick Start (Docker)
```bash
git clone https://github.com/Madmangone/robosats-xmr
cd robosats-xmr
cp .env-sample .env
# Edit .env: set SECRET_KEY, LNVENDOR=XMR
docker compose -f docker-compose-xmr.yml up
```

## Manual Setup
```bash
git clone https://github.com/Madmangone/robosats-xmr
cd robosats-xmr
cp .env-sample .env
# Edit .env with your settings (see below)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install monero
python3 manage.py migrate
python3 manage.py runserver
```

## Required .env Settings
```
LNVENDOR=XMR
XMR_WALLET_HOST=127.0.0.1
XMR_WALLET_PORT=18083
XMR_WALLET_USER=
XMR_WALLET_PASS=
XMR_CONFIRMATIONS=10
XMR_NETWORK=stagenet
DEVELOPMENT=True
USE_TOR=False
MARKET_PRICE_APIS=https://min-api.cryptocompare.com/data/price?fsym=XMR&tsyms=USD
```

## Start Monero Wallet RPC
```bash
# Create wallet first
monero-wallet-cli --stagenet \
  --daemon-address stagenet.community.rino.io:38081 \
  --generate-new-wallet /tmp/robosats_wallet \
  --password ""

# Then start RPC
monero-wallet-rpc --stagenet \
  --daemon-address stagenet.community.rino.io:38081 \
  --rpc-bind-port 18083 \
  --disable-rpc-login \
  --wallet-file /tmp/robosats_wallet \
  --password "" \
  --detach
```

## Implementation Details

### Key File: api/lightning/xmr.py

The `XMRNode` class implements the same interface as `LNDNode` and `CLNNode`:

| Lightning Method | XMR Equivalent |
|-----------------|----------------|
| gen_hold_invoice | Create subaddress |
| validate_hold_invoice_locked | Check 10 confirmations |
| settle_hold_invoice | Send to buyer |
| cancel_return_hold_invoice | Refund sender |
| pay_invoice | Transfer XMR |
| wallet_balance | get_balance RPC |

### Trade Flow

1. Maker creates order → subaddress generated as maker bond
2. Taker takes order → subaddress generated as taker bond  
3. Both lock funds → 10 confirmations required
4. Fiat exchange via encrypted chat
5. Seller confirms → funds released to buyer subaddress
6. Dispute → coordinator manually resolves

## Status

- [x] XMRNode class implementing full LNNode interface
- [x] Subaddress-based escrow replacing hold invoices
- [x] Subaddress index persisted in database
- [x] API running with XMR backend on stagenet
- [x] XMR price feeds working for all currencies
- [x] Frontend updated (BTC/Sats → XMR/Piconeros)
- [x] Docker Compose setup
- [x] Database migration for subaddress_index field
- [ ] Full end-to-end trade test on stagenet
- [ ] Mainnet deployment

## Based On

- [RoboSats](https://github.com/RoboSats/robosats) - Original P2P exchange
- [monero-python](https://github.com/monero-ecosystem/monero-python) - Monero Python library
- [monero-wallet-rpc](https://www.getmonero.org/resources/developer-guides/wallet-rpc.html) - Official Monero wallet RPC
