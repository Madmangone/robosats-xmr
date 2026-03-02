import secrets
import hashlib
import time
from datetime import datetime, timedelta
from decouple import config
from django.utils import timezone
from monero.wallet import Wallet
from monero.backends.jsonrpc import JSONRPCWallet
from monero.numbers import to_atomic
import requests

# Monero wallet RPC connection
XMR_WALLET_HOST = config("XMR_WALLET_HOST", default="127.0.0.1")
XMR_WALLET_PORT = config("XMR_WALLET_PORT", cast=int, default=18083)
XMR_WALLET_USER = config("XMR_WALLET_USER", default="")
XMR_WALLET_PASS = config("XMR_WALLET_PASS", default="")
XMR_CONFIRMATIONS = config("XMR_CONFIRMATIONS", cast=int, default=10)  # 10-block lock
XMR_NETWORK = config("XMR_NETWORK", default="mainnet")  # mainnet, stagenet, testnet


def log(name, request, response):
    if not config("LOG_XMR", cast=bool, default=False):
        return
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = (
        f"######################################\n"
        f"Event: {name}\nTime: {current_time}\n"
        f"Request:\n{request}\nResponse:\n{response}\n"
    )
    with open("xmr_log.txt", "a") as file:
        file.write(log_message)


def rpc_call(method, params={}):
    """Raw JSON-RPC call to monero-wallet-rpc"""
    url = f"http://{XMR_WALLET_HOST}:{XMR_WALLET_PORT}/json_rpc"
    payload = {
        "jsonrpc": "2.0",
        "id": "0",
        "method": method,
        "params": params,
    }
    auth = None
    if XMR_WALLET_USER:
        auth = (XMR_WALLET_USER, XMR_WALLET_PASS)
    response = requests.post(url, json=payload, auth=auth, timeout=30)
    result = response.json()
    log(method, params, result)
    if "error" in result:
        raise Exception(f"XMR RPC error: {result['error']}")
    return result.get("result", {})


class XMRNode:
    """
    Monero node implementation matching the LNDNode interface.
    Replaces Lightning hold invoices with Monero subaddresses + confirmations.
    
    Trade flow:
    1. gen_hold_invoice() -> creates a subaddress for the trade escrow
    2. validate_hold_invoice_locked() -> checks if XMR arrived (10 blocks = locked)
    3. settle_hold_invoice() -> releases funds to buyer
    4. cancel_return_hold_invoice() -> refunds maker if trade fails
    """

    payment_failure_context = {
        0: "Payment not failed yet",
        1: "Timeout exceeded",
        2: "No route found",
        3: "Non-recoverable error",
        4: "Incorrect payment details",
        5: "Insufficient balance",
    }

    @classmethod
    def get_version(cls):
        """Get monero-wallet-rpc version"""
        try:
            result = rpc_call("get_version")
            version = result.get("version", 0)
            # Version is encoded as (major * 65536 + minor)
            major = version >> 16
            minor = version & 0xFFFF
            return f"v{major}.{minor}"
        except Exception as e:
            print(f"Cannot get XMR version: {e}")
            return "Not installed"

    @classmethod
    def decode_payreq(cls, address):
        """
        In Monero, 'invoices' are just addresses/subaddresses.
        Validate and return info about an XMR address.
        """
        try:
            result = rpc_call("validate_address", {
                "address": address,
                "any_net_type": False,
                "allow_openalias": False,
            })
            return {
                "address": address,
                "valid": result.get("valid", False),
                "integrated": result.get("integrated", False),
                "subaddress": result.get("subaddress", False),
                "nettype": result.get("nettype", "mainnet"),
            }
        except Exception as e:
            print(f"Cannot decode XMR address: {e}")
            return {"valid": False}

    @classmethod
    def estimate_fee(cls, amount_xmr, **kwargs):
        """Estimate XMR transaction fee"""
        try:
            # Convert XMR to piconero (atomic units)
            amount_pico = int(float(amount_xmr) * 1e12)
            result = rpc_call("get_fee_estimate", {})
            # fee_multiplier is in piconero per byte
            fee_per_kb = result.get("fee", 20000)
            # Typical XMR tx is ~2kb
            estimated_fee = fee_per_kb * 2
            return {
                "mining_fee_sats": estimated_fee,  # in piconero
                "mining_fee_rate": fee_per_kb,
            }
        except Exception as e:
            print(f"Cannot estimate XMR fee: {e}")
            return {"mining_fee_sats": 40000, "mining_fee_rate": 20000}

    @classmethod
    def wallet_balance(cls):
        """Returns XMR wallet balance"""
        try:
            result = rpc_call("get_balance", {"account_index": 0})
            return {
                "total_balance": result.get("balance", 0),
                "confirmed_balance": result.get("unlocked_balance", 0),
                "unconfirmed_balance": result.get("balance", 0) - result.get("unlocked_balance", 0),
            }
        except Exception as e:
            print(f"Cannot get XMR balance: {e}")
            return {"total_balance": 0, "confirmed_balance": 0, "unconfirmed_balance": 0}

    @classmethod
    def channel_balance(cls):
        """
        XMR has no payment channels. Return wallet balance in same format.
        """
        balance = cls.wallet_balance()
        return {
            "local_balance": balance["confirmed_balance"],
            "remote_balance": 0,
            "unsettled_local_balance": balance["unconfirmed_balance"],
            "unsettled_remote_balance": 0,
        }

    @classmethod
    def pay_onchain(cls, onchainpayment, queue_code=5, on_mempool_code=2):
        """Send XMR transaction for buyer payouts"""
        try:
            if onchainpayment.status == queue_code:
                onchainpayment.status = on_mempool_code
                onchainpayment.save(update_fields=["status"])

                amount_pico = int(float(onchainpayment.sent_satoshis) * 1e12)

                result = rpc_call("transfer", {
                    "destinations": [{
                        "amount": amount_pico,
                        "address": onchainpayment.address,
                    }],
                    "account_index": 0,
                    "priority": 2,  # normal priority
                    "get_tx_key": True,
                })

                txid = result.get("tx_hash", "")
                if txid:
                    onchainpayment.txid = txid
                    onchainpayment.broadcasted = True
                onchainpayment.save(update_fields=["txid", "broadcasted"])
                log("pay_onchain", onchainpayment.address, result)
                return True

            elif onchainpayment.status == on_mempool_code:
                # Double payment attempted
                return True

        except Exception as e:
            print(f"Cannot send XMR onchain: {e}")
            return False

    @classmethod
    def cancel_return_hold_invoice(cls, payment_hash):
        """
        In XMR: if funds arrived at subaddress, send them back.
        payment_hash stores the subaddress index for Monero.
        """
        try:
            # Get the subaddress associated with this trade
            subaddress_index = cls._get_subaddress_index(payment_hash)
            if subaddress_index is None:
                return True  # Nothing to return

            # Check if any funds arrived
            result = rpc_call("get_balance", {
                "account_index": 0,
                "address_indices": [subaddress_index],
            })

            balance = result.get("per_subaddress", [])
            if not balance or balance[0].get("unlocked_balance", 0) == 0:
                return True  # Nothing to refund

            # Get the original sender address from transfers
            transfers = rpc_call("get_transfers", {
                "in": True,
                "account_index": 0,
                "subaddr_indices": [subaddress_index],
            })

            incoming = transfers.get("in", [])
            if not incoming:
                return True

            # Send back to original sender
            sender_address = incoming[0].get("address", "")
            if not sender_address:
                return False

            amount = balance[0].get("unlocked_balance", 0)
            rpc_call("transfer", {
                "destinations": [{"amount": amount, "address": sender_address}],
                "account_index": 0,
                "subaddr_indices": [subaddress_index],
                "priority": 2,
            })
            log("cancel_return_hold_invoice", payment_hash, "refunded")
            return True

        except Exception as e:
            print(f"Cannot cancel/return XMR: {e}")
            return False

    @classmethod
    def settle_hold_invoice(cls, preimage):
        """
        In XMR: release escrowed funds to buyer.
        preimage stores 'subaddress_index:buyer_address'
        """
        try:
            parts = preimage.split(":")
            subaddress_index = int(parts[0])
            buyer_address = parts[1]

            # Get balance at escrow subaddress
            result = rpc_call("get_balance", {
                "account_index": 0,
                "address_indices": [subaddress_index],
            })

            balance = result.get("per_subaddress", [])
            if not balance:
                return False

            amount = balance[0].get("unlocked_balance", 0)
            if amount == 0:
                return False

            # Send to buyer
            rpc_call("transfer", {
                "destinations": [{"amount": amount, "address": buyer_address}],
                "account_index": 0,
                "subaddr_indices": [subaddress_index],
                "priority": 2,
            })
            log("settle_hold_invoice", preimage, "settled")
            return True

        except Exception as e:
            print(f"Cannot settle XMR invoice: {e}")
            return False

    @classmethod
    def gen_hold_invoice(
        cls,
        num_satoshis,
        description,
        invoice_expiry,
        cltv_expiry_blocks,
        order_id,
        lnpayment_concept,
        time,
    ):
        """
        Generates a Monero subaddress to act as escrow (hold invoice equivalent).
        The subaddress index is stored as payment_hash for later lookup.
        """
        hold_payment = {}

        try:
            # Create a new subaddress for this specific trade
            result = rpc_call("create_address", {
                "account_index": 0,
                "label": f"order_{order_id}_{lnpayment_concept}",
            })

            subaddress = result.get("address", "")
            subaddress_index = result.get("address_index", 0)

            # Use subaddress_index as our "payment_hash" equivalent
            payment_hash = hashlib.sha256(
                f"{order_id}_{subaddress_index}_{secrets.token_hex(16)}".encode()
            ).hexdigest()

            now = timezone.now()
            hold_payment["invoice"] = subaddress  # XMR address IS the invoice
            hold_payment["preimage"] = f"{subaddress_index}:"  # buyer address added later
            hold_payment["subaddress_index"] = subaddress_index  # stored in DB after LNPayment created
            hold_payment["payment_hash"] = payment_hash
            hold_payment["created_at"] = now
            hold_payment["expires_at"] = now + timedelta(seconds=invoice_expiry)
            hold_payment["cltv_expiry"] = cltv_expiry_blocks

            log("gen_hold_invoice", description, hold_payment)
            return hold_payment

        except Exception as e:
            print(f"Cannot generate XMR hold invoice: {e}")
            return {}

    @classmethod
    def validate_hold_invoice_locked(cls, lnpayment):
        """
        Checks if XMR has arrived at the escrow subaddress
        and has enough confirmations (10 blocks = locked).
        """
        from api.models import LNPayment

        try:
            subaddress_index = cls._get_subaddress_index(lnpayment.payment_hash)
            if subaddress_index is None:
                return False

            # Check balance at subaddress
            result = rpc_call("get_balance", {
                "account_index": 0,
                "address_indices": [subaddress_index],
            })

            per_sub = result.get("per_subaddress", [])
            if not per_sub:
                return False

            unlocked = per_sub[0].get("unlocked_balance", 0)
            total = per_sub[0].get("balance", 0)

            # Has funds arrived?
            if total == 0:
                return False

            # Check confirmations via incoming transfers
            transfers = rpc_call("get_transfers", {
                "in": True,
                "account_index": 0,
                "subaddr_indices": [subaddress_index],
            })

            incoming = transfers.get("in", [])
            if not incoming:
                return False

            # Get current block height
            height_result = rpc_call("get_height", {})
            current_height = height_result.get("height", 0)

            # Check if oldest unconfirmed tx has enough confirmations
            for tx in incoming:
                tx_height = tx.get("height", 0)
                confirmations = current_height - tx_height
                if confirmations >= XMR_CONFIRMATIONS:
                    # Funds are locked! Update lnpayment
                    lnpayment.expiry_height = tx_height + XMR_CONFIRMATIONS
                    lnpayment.status = LNPayment.Status.LOCKED
                    lnpayment.save(update_fields=["expiry_height", "status"])
                    log("validate_hold_invoice_locked", lnpayment.payment_hash, "LOCKED")
                    return True

            return False

        except Exception as e:
            print(f"Cannot validate XMR hold invoice: {e}")
            return False

    @classmethod
    def lookup_invoice_status(cls, lnpayment):
        """
        Returns current status of a Monero escrow subaddress.
        Maps XMR confirmation state to LNPayment.Status.
        """
        from api.models import LNPayment

        status = lnpayment.status
        expiry_height = 0

        try:
            subaddress_index = cls._get_subaddress_index(lnpayment.payment_hash)
            if subaddress_index is None:
                return LNPayment.Status.CANCEL, expiry_height

            result = rpc_call("get_balance", {
                "account_index": 0,
                "address_indices": [subaddress_index],
            })

            per_sub = result.get("per_subaddress", [])
            if not per_sub:
                return status, expiry_height

            total = per_sub[0].get("balance", 0)
            unlocked = per_sub[0].get("unlocked_balance", 0)

            if total == 0:
                # No funds = open/waiting
                status = LNPayment.Status.INVGEN
            elif unlocked == 0 and total > 0:
                # Funds arrived but not yet confirmed
                status = LNPayment.Status.LOCKED
            elif unlocked > 0:
                # Funds confirmed and unlocked
                status = LNPayment.Status.LOCKED

            # Get expiry height from transfers
            transfers = rpc_call("get_transfers", {
                "in": True,
                "account_index": 0,
                "subaddr_indices": [subaddress_index],
            })
            incoming = transfers.get("in", [])
            if incoming:
                expiry_height = max(
                    tx.get("height", 0) + XMR_CONFIRMATIONS
                    for tx in incoming
                )

            log("lookup_invoice_status", lnpayment.payment_hash, status)

        except Exception as e:
            print(f"Cannot lookup XMR invoice status: {e}")

        return status, expiry_height

    @classmethod
    def validate_ln_invoice(cls, address, num_satoshis, routing_budget_ppm):
        """
        Validates a Monero address (equivalent of validating LN invoice).
        num_satoshis here is in piconero.
        """
        payout = {
            "valid": False,
            "context": None,
            "description": None,
            "payment_hash": address,
            "created_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(days=1),
        }

        try:
            result = rpc_call("validate_address", {
                "address": address,
                "any_net_type": False,
                "allow_openalias": False,
            })

            if not result.get("valid", False):
                payout["context"] = {"bad_invoice": "Invalid Monero address"}
                return payout

            payout["valid"] = True
            payout["description"] = f"XMR payment to {address[:16]}..."
            return payout

        except Exception as e:
            payout["context"] = {"bad_invoice": f"Could not validate address: {e}"}
            return payout

    @classmethod
    def pay_invoice(cls, lnpayment):
        """Sends XMR. Used for rewards payouts."""
        from api.models import LNPayment

        try:
            amount_pico = int(lnpayment.num_satoshis)  # stored as piconero

            result = rpc_call("transfer", {
                "destinations": [{
                    "amount": amount_pico,
                    "address": lnpayment.invoice,
                }],
                "account_index": 0,
                "priority": 2,
                "get_tx_key": True,
            })

            txid = result.get("tx_hash", "")
            if txid:
                lnpayment.status = LNPayment.Status.SUCCED
                lnpayment.fee = result.get("fee", 0) / 1e12
                lnpayment.preimage = result.get("tx_key", "")
                lnpayment.save(update_fields=["fee", "status", "preimage"])
                log("pay_invoice", lnpayment.invoice, result)
                return True, None

            lnpayment.status = LNPayment.Status.FAILRO
            lnpayment.save(update_fields=["status"])
            return False, "No txid returned"

        except Exception as e:
            print(f"Cannot pay XMR invoice: {e}")
            lnpayment.status = LNPayment.Status.FAILRO
            lnpayment.save(update_fields=["status"])
            return False, str(e)

    @classmethod
    def follow_send_payment(cls, lnpayment, fee_limit_sat, timeout_seconds):
        """
        Sends XMR to buyer with monitoring.
        XMR transactions are simpler - no routing needed.
        """
        from api.models import LNPayment, Order

        try:
            lnpayment.status = LNPayment.Status.FLIGHT
            lnpayment.in_flight = True
            lnpayment.save(update_fields=["in_flight", "status"])

            order = lnpayment.order_paid_LN
            order.update_status(Order.Status.PAY)
            order.save(update_fields=["status"])

            amount_pico = int(lnpayment.num_satoshis)

            result = rpc_call("transfer", {
                "destinations": [{
                    "amount": amount_pico,
                    "address": lnpayment.invoice,
                }],
                "account_index": 0,
                "priority": 2,
                "get_tx_key": True,
            })

            txid = result.get("tx_hash", "")
            if txid:
                lnpayment.status = LNPayment.Status.SUCCED
                lnpayment.fee = result.get("fee", 0) / 1e12
                lnpayment.preimage = result.get("tx_key", "")
                lnpayment.in_flight = False
                lnpayment.save(update_fields=["status", "fee", "preimage", "in_flight"])

                order.update_status(Order.Status.SUC)
                order.expires_at = timezone.now() + timedelta(
                    seconds=order.t_to_expire(Order.Status.SUC)
                )
                order.save(update_fields=["expires_at"])
                order.log(f"XMR payment succeeded. TXID: {txid}")
                log("follow_send_payment", lnpayment.invoice, result)
                return {"succeded": True}

            # Payment failed
            lnpayment.status = LNPayment.Status.FAILRO
            lnpayment.in_flight = False
            lnpayment.routing_attempts += 1
            lnpayment.save(update_fields=["status", "in_flight", "routing_attempts"])
            order.update_status(Order.Status.FAI)
            order.save(update_fields=["status"])
            return {"succeded": False, "context": "No txid returned"}

        except Exception as e:
            print(f"Cannot follow XMR payment: {e}")
            return {"succeded": False, "context": str(e)}

    @classmethod
    def send_keysend(cls, target_pubkey, message, num_satoshis, routing_budget_sats, timeout, sign):
        """
        XMR has no keysend equivalent.
        We send a regular XMR transfer with a note instead.
        target_pubkey here is treated as an XMR address.
        """
        from api.models import LNPayment

        keysend_payment = {
            "created_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(hours=1),
            "status": LNPayment.Status.SUCCED,
        }

        try:
            amount_pico = int(num_satoshis)
            result = rpc_call("transfer", {
                "destinations": [{
                    "amount": amount_pico,
                    "address": target_pubkey,
                }],
                "account_index": 0,
                "priority": 2,
                "get_tx_key": True,
            })

            keysend_payment["preimage"] = result.get("tx_key", "")
            keysend_payment["payment_hash"] = result.get("tx_hash", "")
            keysend_payment["fee"] = result.get("fee", 0) / 1e12
            log("send_keysend", target_pubkey, result)

        except Exception as e:
            keysend_payment["status"] = LNPayment.Status.FAILRO
            print(f"Cannot send XMR keysend: {e}")

        return True, keysend_payment

    @classmethod
    def double_check_htlc_is_settled(cls, payment_hash):
        """
        Verifies XMR escrow subaddress has confirmed funds.
        """
        try:
            subaddress_index = cls._get_subaddress_index(payment_hash)
            if subaddress_index is None:
                return False

            result = rpc_call("get_balance", {
                "account_index": 0,
                "address_indices": [subaddress_index],
            })

            per_sub = result.get("per_subaddress", [])
            if not per_sub:
                return False

            unlocked = per_sub[0].get("unlocked_balance", 0)
            log("double_check_htlc_is_settled", payment_hash, unlocked)
            return unlocked > 0

        except Exception as e:
            print(f"Cannot double check XMR settlement: {e}")
            return False

    # ---- Helper methods ----

    @classmethod
    def _store_subaddress_mapping(cls, payment_hash, subaddress_index):
        """Store payment_hash -> subaddress_index mapping in the database"""
        from api.models import LNPayment
        try:
            lnpayment = LNPayment.objects.get(payment_hash=payment_hash)
            lnpayment.subaddress_index = subaddress_index
            lnpayment.save(update_fields=["subaddress_index"])
        except LNPayment.DoesNotExist:
            pass

    @classmethod
    def _get_subaddress_index(cls, payment_hash):
        """Retrieve subaddress_index from database"""
        from api.models import LNPayment
        try:
            lnpayment = LNPayment.objects.get(payment_hash=payment_hash)
            return lnpayment.subaddress_index
        except LNPayment.DoesNotExist:
            return None
