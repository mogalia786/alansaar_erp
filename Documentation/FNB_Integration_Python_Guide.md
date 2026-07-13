# FNB Banking Integration Guide - Python Implementation

## Overview

This guide provides Python code examples for integrating with FNB's banking APIs to:
1. Fetch bank statements (transaction history)
2. Make payments to beneficiaries

## FNB Test Account Details

### Your Business Accounts (Debtor - Money Going Out)
- **Account 1**: 63001723469 (Branch: 250655, BIC: FIRNZAJJ)
- **Account 2**: 63001731248 (Branch: 250655, BIC: FIRNZAJJ)

### Beneficiary Accounts (Creditor - Money Coming In)
- **Account 1**: 63001730117 (Branch: 250655, BIC: FIRNZAJJ)
- **Account 2**: 63001731222 (Branch: 250655, BIC: FIRNZAJJ)

### API Credentials (Sandbox Environment)
- **Base URL**: https://api.i.fnb.co.za/apigateway
- **Auth URL**: https://api.i.fnb.co.za/apigateway/oauth2/token/v2
- **Client ID**: E84OOE
- **Client Secret**: 621NZsDknRDWjqf8sKhyH0ktjPXtbsr4

---

## Prerequisites

```bash
pip install requests
```

---

## Part 1: Fetch Bank Statements

### Python Implementation

```python
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class FNBStatementService:
    """FNB Statement API Service for fetching transaction history"""
    
    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url
        self.access_token = None
        self.token_expiry = None
    
    def get_access_token(self) -> str:
        """Obtain OAuth access token from FNB"""
        token_url = f"{self.base_url}/oauth2/token/v2"
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            response = requests.post(token_url, data=payload, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            
            # Token typically expires in 3600 seconds (1 hour)
            self.token_expiry = datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600))
            
            print(f"✓ Access token obtained successfully")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to obtain access token: {e}")
    
    def fetch_statement(self, account_id: str, from_date: str, to_date: str) -> Dict:
        """
        Fetch bank statement for a specific account
        
        Args:
            account_id: FNB account number (e.g., "63001723469")
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
        
        Returns:
            Dictionary containing statement data with transactions
        """
        # Ensure we have a valid token
        if not self.access_token or (self.token_expiry and datetime.now() >= self.token_expiry):
            self.get_access_token()
        
        url = f"{self.base_url}/statements/retrieveStatement/v1/"
        request_id = str(uuid.uuid4())
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": request_id,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        payload = {
            "accountId": account_id,
            "fromDate": from_date,
            "toDate": to_date
        }
        
        try:
            print(f"Fetching statement for account {account_id} from {from_date} to {to_date}")
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            statement_data = response.json()
            
            # Extract transaction count
            entry_count = 0
            if "statement" in statement_data and "entry" in statement_data["statement"]:
                entry_count = len(statement_data["statement"]["entry"])
            
            print(f"✓ Statement retrieved successfully. Transactions: {entry_count}")
            return statement_data
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch statement: {e}")
    
    def parse_transactions(self, statement_data: Dict) -> List[Dict]:
        """
        Parse transactions from statement data
        
        Returns:
            List of transaction dictionaries
        """
        transactions = []
        
        if "statement" not in statement_data or "entry" not in statement_data["statement"]:
            return transactions
        
        for entry in statement_data["statement"]["entry"]:
            transaction = {
                "transaction_date": entry.get("bookingDateTime"),
                "description": entry.get("transactionDetails", {}).get("transactionDetails", {}).get("description"),
                "reference": entry.get("transactionDetails", {}).get("transactionDetails", {}).get("reference"),
                "debit_amount": entry.get("transactionDetails", {}).get("valueAmount", {}).get("amount"),
                "credit_amount": None,  # Will be calculated
                "balance": entry.get("transactionDetails", {}).get("balance", {}).get("balanceAmount", {}).get("amount"),
                "transaction_type": None  # Will be calculated
            }
            
            # Determine if debit or credit
            amount = entry.get("transactionDetails", {}).get("valueAmount", {}).get("amount")
            sign = entry.get("transactionDetails", {}).get("valueAmount", {}).get("sign")
            
            if sign == "-":
                transaction["debit_amount"] = abs(amount)
                transaction["transaction_type"] = "Debit"
            else:
                transaction["credit_amount"] = amount
                transaction["transaction_type"] = "Credit"
            
            transactions.append(transaction)
        
        return transactions


# Example Usage
if __name__ == "__main__":
    # Initialize service with sandbox credentials
    fnb_service = FNBStatementService(
        client_id="E84OOE",
        client_secret="621NZsDknRDWjqf8sKhyH0ktjPXtbsr4",
        base_url="https://api.i.fnb.co.za/apigateway"
    )
    
    # Fetch statement for the last 30 days
    from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")
    
    # Use your business account
    account_id = "63001723469"
    
    try:
        # Fetch statement
        statement = fnb_service.fetch_statement(account_id, from_date, to_date)
        
        # Parse transactions
        transactions = fnb_service.parse_transactions(statement)
        
        # Display transactions
        print(f"\n{'='*80}")
        print(f"TRANSACTIONS FOR ACCOUNT {account_id}")
        print(f"{'='*80}")
        
        for txn in transactions:
            print(f"Date: {txn['transaction_date']}")
            print(f"Description: {txn['description']}")
            print(f"Reference: {txn['reference']}")
            print(f"Type: {txn['transaction_type']}")
            if txn['debit_amount']:
                print(f"Debit: R{txn['debit_amount']:.2f}")
            if txn['credit_amount']:
                print(f"Credit: R{txn['credit_amount']:.2f}")
            print(f"Balance: R{txn['balance']:.2f}")
            print("-" * 80)
        
        print(f"\nTotal Transactions: {len(transactions)}")
        
    except Exception as e:
        print(f"Error: {e}")
```

---

## Part 2: Make Payments

### Python Implementation

```python
import requests
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class FNBPaymentService:
    """FNB Payment API Service for executing payments"""
    
    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url
        self.access_token = None
        self.token_expiry = None
    
    def get_access_token(self) -> str:
        """Obtain OAuth access token from FNB"""
        token_url = f"{self.base_url}/oauth2/token/v2"
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            response = requests.post(token_url, data=payload, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            
            self.token_expiry = datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600))
            
            print(f"✓ Access token obtained successfully")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to obtain access token: {e}")
    
    def create_payment(self, 
                     debtor_account: str,
                     debtor_branch: str,
                     creditor_account: str,
                     creditor_branch: str,
                     amount: float,
                     reference: str,
                     description: str = "Payment") -> Dict:
        """
        Create and submit a payment
        
        Args:
            debtor_account: Your account number (money going out)
            debtor_branch: Your branch code
            creditor_account: Beneficiary account number (money going in)
            creditor_branch: Beneficiary branch code
            amount: Payment amount in ZAR
            reference: Payment reference (max 20 chars for LOAN/TRNS/SBSH/GRCP accounts)
            description: Payment description
        
        Returns:
            Dictionary containing payment response
        """
        # Ensure we have a valid token
        if not self.access_token or (self.token_expiry and datetime.now() >= self.token_expiry):
            self.get_access_token()
        
        url = f"{self.base_url}/payments/v1"
        request_id = str(uuid.uuid4())
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": request_id,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # IMPORTANT: Reference field limitation
        # For LOAN, TRNS, SBSH and GRCP FNB accounts, only first 20 characters are processed
        reference = reference[:20]
        
        payload = {
            "paymentInformation": {
                "debtorAccount": {
                    "accountNumber": debtor_account,
                    "accountType": "CACC",  # Current/Cheque account
                    "branchId": debtor_branch
                },
                "debtorAgent": {
                    "bicOrBEI": "FIRNZAJJ"  # FNB South Africa BIC
                },
                "creditorAccount": {
                    "accountNumber": creditor_account,
                    "accountType": "CACC",
                    "branchId": creditor_branch
                },
                "creditorAgent": {
                    "bicOrBEI": "FIRNZAJJ"
                },
                "instructedAmount": {
                    "amount": str(amount),
                    "currency": "ZAR"
                },
                "remittanceInformationUnstructured": reference,
                "requestedExecutionDate": datetime.now().strftime("%Y-%m-%d")
            }
        }
        
        try:
            print(f"Creating payment: R{amount:.2f} from {debtor_account} to {creditor_account}")
            print(f"Reference: {reference}")
            
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            payment_response = response.json()
            
            print(f"✓ Payment created successfully")
            return payment_response
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to create payment: {e}")
    
    def create_batch_payment(self, 
                           debtor_account: str,
                           debtor_branch: str,
                           payments: List[Dict]) -> Dict:
        """
        Create a batch payment (multiple payments in one request)
        
        Args:
            debtor_account: Your account number
            debtor_branch: Your branch code
            payments: List of payment dictionaries with keys:
                - creditor_account: Beneficiary account
                - creditor_branch: Beneficiary branch
                - amount: Payment amount
                - reference: Payment reference
        
        Returns:
            Dictionary containing batch payment response
        """
        # Ensure we have a valid token
        if not self.access_token or (self.token_expiry and datetime.now() >= self.token_expiry):
            self.get_access_token()
        
        url = f"{self.base_url}/payments/v1/batch"
        request_id = str(uuid.uuid4())
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": request_id,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Build payment list
        payment_list = []
        for payment in payments:
            # Truncate reference to 20 chars
            reference = payment.get("reference", "")[:20]
            
            payment_list.append({
                "creditorAccount": {
                    "accountNumber": payment["creditor_account"],
                    "accountType": "CACC",
                    "branchId": payment["creditor_branch"]
                },
                "creditorAgent": {
                    "bicOrBEI": "FIRNZAJJ"
                },
                "instructedAmount": {
                    "amount": str(payment["amount"]),
                    "currency": "ZAR"
                },
                "remittanceInformationUnstructured": reference
            })
        
        payload = {
            "paymentInformation": {
                "debtorAccount": {
                    "accountNumber": debtor_account,
                    "accountType": "CACC",
                    "branchId": debtor_branch
                },
                "debtorAgent": {
                    "bicOrBEI": "FIRNZAJJ"
                },
                "paymentInformationList": payment_list,
                "requestedExecutionDate": datetime.now().strftime("%Y-%m-%d")
            }
        }
        
        try:
            print(f"Creating batch payment with {len(payments)} transactions")
            
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            batch_response = response.json()
            
            print(f"✓ Batch payment created successfully")
            return batch_response
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to create batch payment: {e}")


# Example Usage
if __name__ == "__main__":
    # Initialize service with sandbox credentials
    fnb_payment = FNBPaymentService(
        client_id="E84OOE",
        client_secret="621NZsDknRDWjqf8sKhyH0ktjPXtbsr4",
        base_url="https://api.i.fnb.co.za/apigateway"
    )
    
    # Your business account (debtor)
    debtor_account = "63001723469"
    debtor_branch = "250655"
    
    try:
        # Example 1: Single payment
        print("=" * 80)
        print("SINGLE PAYMENT EXAMPLE")
        print("=" * 80)
        
        single_payment = fnb_payment.create_payment(
            debtor_account=debtor_account,
            debtor_branch=debtor_branch,
            creditor_account="63001730117",  # Beneficiary account
            creditor_branch="250655",
            amount=1500.00,
            reference="INV-2024-001",
            description="Invoice Payment"
        )
        
        print(f"Payment Response: {json.dumps(single_payment, indent=2)}")
        
        # Example 2: Batch payment
        print("\n" + "=" * 80)
        print("BATCH PAYMENT EXAMPLE")
        print("=" * 80)
        
        batch_payments = [
            {
                "creditor_account": "63001730117",
                "creditor_branch": "250655",
                "amount": 500.00,
                "reference": "SUPP-001"
            },
            {
                "creditor_account": "63001731222",
                "creditor_branch": "250655",
                "amount": 750.00,
                "reference": "RENT-JUL"
            },
            {
                "creditor_account": "63001730117",
                "creditor_branch": "250655",
                "amount": 250.00,
                "reference": "UTILITIES"
            }
        ]
        
        batch_payment = fnb_payment.create_batch_payment(
            debtor_account=debtor_account,
            debtor_branch=debtor_branch,
            payments=batch_payments
        )
        
        print(f"Batch Payment Response: {json.dumps(batch_payment, indent=2)}")
        
    except Exception as e:
        print(f"Error: {e}")
```

---

## Important Notes

### Reference Field Limitation
- **CRITICAL**: For LOAN, TRNS, SBSH and GRCP FNB accounts, only the **first 20 characters** of the reference field are processed
- Always truncate references to 20 characters for these account types
- The code automatically handles this truncation

### Account Types
- **CACC**: Current/Cheque account
- **SVGS**: Savings account

### BIC Code
- FNB South Africa: `FIRNZAJJ`

### Token Management
- Access tokens expire after 1 hour (3600 seconds)
- The code automatically refreshes tokens when needed
- Store tokens securely in production (consider using environment variables)

### Error Handling
- Always wrap API calls in try-catch blocks
- Check response status codes before processing
- Log all API requests and responses for debugging

### Sandbox vs Production
- The credentials provided are for **sandbox testing**
- For production, you'll need to obtain production credentials from FNB
- Production URLs may differ from sandbox URLs

---

## Environment Variables (Recommended for Production)

```bash
# .env file
FNB_CLIENT_ID=your_production_client_id
FNB_CLIENT_SECRET=your_production_client_secret
FNB_BASE_URL=https://api.fnb.co.za/apigateway
FNB_DEBTOR_ACCOUNT=your_account_number
FNB_DEBTOR_BRANCH=your_branch_code
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

fnb_service = FNBStatementService(
    client_id=os.getenv("FNB_CLIENT_ID"),
    client_secret=os.getenv("FNB_CLIENT_SECRET"),
    base_url=os.getenv("FNB_BASE_URL")
)
```

---

## Testing Checklist

- [ ] Test statement retrieval for different date ranges
- [ ] Test single payment to beneficiary
- [ ] Test batch payment with multiple beneficiaries
- [ ] Verify reference field truncation (20 chars)
- [ ] Test error handling (invalid account, insufficient funds, etc.)
- [ ] Test token refresh mechanism
- [ ] Verify transaction parsing and data integrity

---

## Support

For FNB API documentation and support:
- FNB Developer Portal: https://developer.fnb.co.za
- API Documentation: Available through FNB's developer portal
- Technical Support: Contact FNB's API support team
