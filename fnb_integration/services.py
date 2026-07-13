import requests
import uuid
import socket
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from django.conf import settings
from django.utils import timezone
from .models import FNBAccessToken


FNB_CLIENT_ID = settings.FNB_CLIENT_ID
FNB_CLIENT_SECRET = settings.FNB_CLIENT_SECRET
FNB_BASE_URL = settings.FNB_BASE_URL


def _resolve_host(host, retries=3, delay=2):
    for attempt in range(retries):
        try:
            socket.getaddrinfo(host, 443)
            return True
        except socket.gaierror:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


LOG_STEPS = []


def _log(step, status, detail=""):
    icon = {"ok": "✓", "pending": "…", "error": "✗", "info": "i"}
    LOG_STEPS.append({
        "step": step,
        "status": status,
        "icon": icon.get(status, "?"),
        "detail": detail,
    })


def get_access_token(force_refresh=False) -> Tuple[str, datetime]:
    _log("FNB Authentication", "pending", "Requesting OAuth2 token...")

    latest = FNBAccessToken.objects.first()
    if latest and not force_refresh and latest.expires_at > timezone.now():
        _log("FNB Authentication", "ok", "Using cached token (valid until " + latest.expires_at.strftime("%H:%M:%S") + ")")
        return latest.token, latest.expires_at

    url = f"{FNB_BASE_URL}/oauth2/token/v2"
    _log("FNB Authentication", "info", "POST " + url)

    from urllib.parse import urlparse
    host = urlparse(url).hostname
    _log("DNS Resolution", "pending", f"Resolving {host}...")
    _resolve_host(host)
    _log("DNS Resolution", "ok", f"{host} resolved")

    payload = {
        "grant_type": "client_credentials",
        "client_id": FNB_CLIENT_ID,
        "client_secret": FNB_CLIENT_SECRET,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 3600)
    expires_at = timezone.now() + timedelta(seconds=expires_in)

    FNBAccessToken.objects.create(token=token, expires_at=expires_at)
    _log("FNB Authentication", "ok", "Token obtained (expires in " + str(expires_in) + "s)")
    return token, expires_at


class FNBStatementService:
    def __init__(self):
        self.access_token, _ = get_access_token()

    def _ensure_token(self):
        latest = FNBAccessToken.objects.first()
        if not latest or latest.expires_at <= timezone.now():
            _log("Token Refresh", "pending", "Token expired, refreshing...")
            self.access_token, _ = get_access_token(force_refresh=True)
            _log("Token Refresh", "ok", "Token refreshed successfully")

    def fetch_statement(self, account_number: str, from_date: str, to_date: str) -> Dict:
        self._ensure_token()
        url = f"{FNB_BASE_URL}/statements/retrieveStatement/v1/"
        request_id = str(uuid.uuid4())
        _log("API Request", "pending", f"Fetching statement for account {account_number}")
        _log("API Request", "info", f"POST {url}")
        _log("API Request", "info", f"Date range: {from_date} to {to_date}")

        from urllib.parse import urlparse
        host = urlparse(url).hostname
        _log("DNS Resolution", "pending", f"Resolving {host}...")
        _resolve_host(host)
        _log("DNS Resolution", "ok", f"{host} resolved")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": request_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "accountId": account_number,
            "fromDate": from_date,
            "toDate": to_date,
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        _log("API Request", "ok", f"Statement received for account {account_number}")
        return data

    def fetch_statement_range(self, account_number: str, to_date_str: str, lookback_months: int = 6) -> Dict:
        result = {"entries": [], "opening_balance": None, "closing_balance": None}
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
        from_date = to_date - timedelta(days=lookback_months * 30)

        current_start = from_date
        CHUNK_DELAY = 1.5
        while current_start <= to_date:
            chunk_end = min(current_start + timedelta(days=30), to_date)
            f_str = current_start.strftime("%Y-%m-%d")
            t_str = chunk_end.strftime("%Y-%m-%d")
            retries = 3
            while retries > 0:
                try:
                    data = self.fetch_statement(account_number, f_str, t_str)
                    statement = data.get("statement", {})
                    entries = statement.get("entry", [])
                    if entries:
                        _log("Chunk Result", "ok", f"{f_str} to {t_str}: {len(entries)} entries")
                        result["entries"].extend(entries)
                    else:
                        _log("Chunk Result", "info", f"{f_str} to {t_str}: 0 entries")
                    balances = statement.get("balance", [])
                    for b in balances:
                        bal_type = b.get("typeCode", "")
                        if bal_type == "OPBD" and result["opening_balance"] is None:
                            result["opening_balance"] = b
                        if bal_type == "CLBD":
                            result["closing_balance"] = b
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 400:
                        _log("Chunk Result", "info", f"{f_str} to {t_str}: skipped (no data for this period)")
                        break
                    elif e.response.status_code == 429:
                        retries -= 1
                        wait = 5 * (4 - retries)
                        _log("Chunk Result", "pending", f"Rate limited, retrying in {wait}s ({retries} left)")
                        time.sleep(wait)
                    else:
                        retries -= 1
                        if retries == 0:
                            _log("Chunk Result", "error", f"{f_str} to {t_str}: {e}")
                        else:
                            _log("Chunk Result", "pending", f"Error, retrying ({retries} left)")
                            time.sleep(2)
            current_start = chunk_end + timedelta(days=1)
            time.sleep(CHUNK_DELAY)

        _log("Range Complete", "ok", f"Total entries across all chunks: {len(result['entries'])}")
        return result

    @staticmethod
    def parse_transactions(statement_data: Dict) -> List[Dict]:
        entries = statement_data.get("statement", {}).get("entry", [])
        return FNBStatementService._parse_entries(entries)

    @staticmethod
    def parse_entries(entries: List[Dict]) -> List[Dict]:
        return FNBStatementService._parse_entries(entries)

    @staticmethod
    def _parse_entries(entries: List[Dict]) -> List[Dict]:
        from django.utils import timezone
        transactions = []
        _log("Parse Transactions", "info", f"Parsing {len(entries)} entries")
        for entry in entries:
            amount_val = entry.get("amountValue", 0)
            indicator = entry.get("creditDebitIndicator", "")
            txn_details = entry.get("transactionDetails", {})
            raw_date = entry.get("bookingDateTime", "")
            try:
                dt = datetime.strptime(raw_date[:10], "%Y-%m-%d")
                booking_date = timezone.make_aware(dt) if dt else None
            except (ValueError, TypeError):
                booking_date = None
            if indicator == "Debit":
                debit = Decimal(str(amount_val))
                credit = Decimal('0')
                txn_type = "Debit"
            else:
                debit = Decimal('0')
                credit = Decimal(str(amount_val))
                txn_type = "Credit"
            transactions.append({
                "transaction_date": booking_date,
                "description": entry.get("servicerReference", ""),
                "reference": txn_details.get("referenceEndToEndId", ""),
                "debit_amount": debit,
                "credit_amount": credit,
                "balance": None,
                "transaction_type": txn_type,
            })
        _log("Parse Transactions", "ok", f"Parsed {len(transactions)} transactions")
        return transactions


class FNBPaymentService:
    def __init__(self):
        self.access_token, _ = get_access_token()

    def _ensure_token(self):
        latest = FNBAccessToken.objects.first()
        if not latest or latest.expires_at <= timezone.now():
            _log("Token Refresh", "pending", "Token expired, refreshing...")
            self.access_token, _ = get_access_token(force_refresh=True)
            _log("Token Refresh", "ok", "Token refreshed successfully")

    def create_payment(
        self,
        debtor_account: str,
        debtor_branch: str,
        creditor_account: str,
        creditor_branch: str,
        amount: Decimal,
        reference: str,
        creditor_name: str = "Beneficiary",
    ) -> Dict:
        self._ensure_token()
        url = f"{FNB_BASE_URL}/paymentExecution/initiate/v1"
        message_id = str(uuid.uuid4())
        now = timezone.now()

        _log("Payment Initiation", "pending", f"Preparing payment of R{amount} to {creditor_name}")
        _log("Debtor Account", "info", f"{debtor_account} (Branch: {debtor_branch})")
        _log("Creditor Account", "info", f"{creditor_account} (Branch: {creditor_branch})")
        _log("Reference", "info", f"{reference[:20]}")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": message_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        reference = str(reference)[:20]
        payload = {
            "groupHeader": {
                "messageId": message_id,
                "creationDateTime": now.strftime("%Y-%m-%dT%H:%M:%S"),
                "initiatingPartyName": "Al Ansaar Foundation",
                "initiatingPartyBIC": "FIRNZAJJ",
                "totalNumberOfTransactions": 1,
                "totalControlSum": float(amount),
            },
            "paymentInformation": [
                {
                    "paymentInformationId": f"PAY-{now.strftime('%Y%m%d-%H%M%S')}",
                    "paymentInformationMethod": "TRF",
                    "batchBooking": False,
                    "numberOfTransactions": 1,
                    "controlSum": float(amount),
                    "paymentTypeInformationServiceLevelCode": "SDVA",
                    "requestedExecutionDate": now.strftime("%Y-%m-%d"),
                    "debtor": {
                        "name": "Al Ansaar Foundation",
                        "bicOrBEI": "FIRNZAJJ",
                    },
                    "debtorAccount": {
                        "accountNumber": debtor_account,
                        "accountType": "CACC",
                    },
                    "debtorAgent": {
                        "branchId": debtor_branch,
                    },
                    "creditTransferTransactionInformation": [
                        {
                            "endToEndId": reference or message_id[:20],
                            "amount": {
                                "currency": "ZAR",
                                "value": float(amount),
                            },
                            "creditor": {
                                "name": creditor_name,
                                "bicOrBEI": "FIRNZAJJ",
                            },
                            "creditorAccount": {
                                "accountNumber": creditor_account,
                                "accountType": "CACC",
                            },
                            "creditorAgent": {
                                "branchId": creditor_branch,
                            },
                            "remittanceInformationUnstructured": reference,
                        }
                    ],
                }
            ],
        }
        _log("Sending to FNB", "pending", f"POST {url}")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        _log("Sending to FNB", "ok", f"Instruction ID: {data.get('instructionId', 'N/A')}")
        return data

    def create_batch_payment(
        self,
        debtor_account: str,
        debtor_branch: str,
        payments: List[Dict],
    ) -> Dict:
        self._ensure_token()
        url = f"{FNB_BASE_URL}/paymentExecution/initiate/v1"
        message_id = str(uuid.uuid4())
        now = timezone.now()

        _log("Batch Payment", "pending", f"Preparing batch of {len(payments)} payments")
        _log("Debtor Account", "info", f"{debtor_account} (Branch: {debtor_branch})")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": message_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        total_sum = float(sum(p["amount"] for p in payments))
        txns = []
        for p in payments:
            _log("Payment Item", "info", f"R{p['amount']} to {p.get('creditor_account', '?')} ({p.get('creditor_name', 'Beneficiary')}) -> {p.get('reference', '')[:20]}")
        for p in payments:
            ref = str(p.get("reference", ""))[:20]
            txns.append({
                "endToEndId": ref or str(uuid.uuid4())[:20],
                "amount": {
                    "currency": "ZAR",
                    "value": float(p["amount"]),
                },
                "creditor": {
                    "name": p.get("creditor_name", "Beneficiary"),
                    "bicOrBEI": p.get("creditor_bic", "FIRNZAJJ"),
                },
                "creditorAccount": {
                    "accountNumber": p["creditor_account"],
                    "accountType": "CACC",
                },
                "creditorAgent": {
                    "branchId": p["creditor_branch"],
                },
                "remittanceInformationUnstructured": ref,
            })
        payload = {
            "groupHeader": {
                "messageId": message_id,
                "creationDateTime": now.strftime("%Y-%m-%dT%H:%M:%S"),
                "initiatingPartyName": "Al Ansaar Foundation",
                "initiatingPartyBIC": "FIRNZAJJ",
                "totalNumberOfTransactions": len(payments),
                "totalControlSum": total_sum,
            },
            "paymentInformation": [
                {
                    "paymentInformationId": f"BATCH-{now.strftime('%Y%m%d-%H%M%S')}",
                    "paymentInformationMethod": "TRF",
                    "batchBooking": True,
                    "numberOfTransactions": len(payments),
                    "controlSum": total_sum,
                    "paymentTypeInformationServiceLevelCode": "SDVA",
                    "requestedExecutionDate": now.strftime("%Y-%m-%d"),
                    "debtor": {
                        "name": "Al Ansaar Foundation",
                        "bicOrBEI": "FIRNZAJJ",
                    },
                    "debtorAccount": {
                        "accountNumber": debtor_account,
                        "accountType": "CACC",
                    },
                    "debtorAgent": {
                        "branchId": debtor_branch,
                    },
                    "creditTransferTransactionInformation": txns,
                }
            ],
        }
        _log("Sending to FNB", "pending", f"POST {url}")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        _log("Sending to FNB", "ok", f"Batch instruction ID: {data.get('instructionId', 'N/A')}")
        return data
