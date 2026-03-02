# RoboSats-XMR

A fork of [RoboSats](https://github.com/RoboSats/robosats) with Monero (XMR) support instead of Bitcoin/Lightning Network.

## What Changed

- Replaced Lightning Network backend with Monero wallet RPC
- Uses Monero subaddresses as escrow (replaces hold invoices)
- 10-block confirmation lock (replaces Lightning HTLC lock)
- All frontend references updated from BTC/Sats to XMR/Piconeros

## How It Works

1. Maker creates order, system generates XMR subaddress for escrow bond
2. Taker takes order, funds locked via 10-block confirmation
3. Fiat exchange happens peer-to-peer via encrypted chat
4. On completion, XMR released to buyer automatically
5. On dispute/cancel, XMR returned to original sender

## Requirements

- monero-wallet-rpc
- Python 3.12+
- PostgreSQL
- Redis

## Setup
```bash
git clone https://github.com/Madmangone/robosats-xmr
cd robosats-xmr
cp .env-sample .env
# Edit .env and set LNVENDOR=XMR and XMR settings
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install monero
python3 manage.py migrate
python3 manage.py runserver
```

## Environment Variables
```
LNVENDOR=XMR
XMR_WALLET_HOST=127.0.0.1
XMR_WALLET_PORT=18083
XMR_WALLET_USER=
XMR_WALLET_PASS=
XMR_CONFIRMATIONS=10
XMR_NETWORK=stagenet
```

## Status

- [x] XMR node implementation
- [x] Subaddress-based escrow
- [x] API running with XMR backend
- [x] Frontend updated for XMR
- [ ] Full end-to-end trade test
- [ ] Docker setup

## Based On

- [RoboSats](https://github.com/RoboSats/robosats) - Original P2P Bitcoin exchange
- [monero-python](https://github.com/monero-ecosystem/monero-python) - Monero Python library
