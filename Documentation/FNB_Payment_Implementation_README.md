# FNB Payment Execution API - Implementation Guide
## Automated Bulk Payment Processing for Oven Delights ERP

---

## IMPLEMENTATION COMPLETE ✅

The FNB Payment Execution API has been fully integrated into the ERP system with automated payment processing capabilities.

---

## 🎯 WHAT WAS IMPLEMENTED

### 1. Database Schema
**Location**: `Database/FNB/`

#### Tables Created:
- **FNB_PaymentBatches** - Stores payment batch submissions
- **FNB_PaymentTransactions** - Individual payment transactions
- **FNB_PaymentStatusLog** - Audit trail of status changes
- **FNB_APICredentials** - Encrypted API credentials storage

#### Stored Procedures Created:
- `sp_FNB_CreatePaymentBatch` - Create new payment batch
- `sp_FNB_AddPaymentTransaction` - Add transaction to batch
- `sp_FNB_UpdateBatchStatus` - Update batch status
- `sp_FNB_UpdateTransactionStatus` - Update transaction status
- `sp_FNB_GetPendingBatches` - Get batches awaiting status check
- `sp_FNB_GetBatchTransactions` - Get transactions for batch
- `sp_FNB_GetPaymentHistory` - Get payment history with filters
- `sp_FNB_GetTransactionDetails` - Get detailed transaction info
- `sp_FNB_MarkTransactionPosted` - Mark transaction as posted to journals
- `sp_FNB_GetAPICredentials` - Retrieve API credentials

#### Suppliers Table Enhancement:
- Added `BankAccountNumber` (NVARCHAR(23))
- Added `BankAccountType` (NVARCHAR(10))
- Added `BankBranchCode` (NVARCHAR(10))
- Added `BankName` (NVARCHAR(50))
- Added `BankBIC` (NVARCHAR(20))
- Added `ProofOfPaymentEmail` (NVARCHAR(100))

### 2. Service Layer
**Location**: `Services/`

#### FNBPaymentAPIClient.vb
- OAuth 2.0 authentication with automatic token refresh
- Payment initiation API calls
- Payment status retrieval
- Unpaid payments retrieval
- Complete request/response models

#### FNBPaymentExecutionService.vb
- High-level payment batch creation
- Payment line validation
- Automatic API request building
- Status checking automation
- Database integration

### 3. User Interface
**Location**: `Forms/Accounting/`

#### PaymentBatchForm (Enhanced)
- **"Submit to FNB API"** button added (blue, prominent)
- **"View Transactions"** button added
- Loads suppliers with bank details automatically
- Validates payment data before submission
- Shows confirmation dialogs with totals
- Displays sandbox mode warnings
- Clears grid after successful submission

#### FNBTransactionViewerForm (New)
- View all payment batches with filters
- Date range filtering
- Status filtering (All, Pending, ACCP, ACSC, RJCT, PDNG)
- Master-detail view (batches → transactions)
- Real-time status checking via "Check Status" button
- Batch and transaction counts
- Color-coded status display

#### FNBTransactionDetailsForm (New)
- Complete transaction details view
- Transaction identification (IDs, references)
- Creditor information
- Status and rejection details
- Remittance references (30 chars + 20 char truncation)
- Date tracking (created, requested, processed)
- Journal posting status
- Status history timeline

---

## 🔧 SETUP INSTRUCTIONS

### Step 1: Run Database Scripts

Execute in this order:

```sql
-- 1. Create tables and insert sandbox credentials
Database\FNB\Create_FNB_Payment_Tables.sql

-- 2. Add bank fields to Suppliers table and create test suppliers
Database\FNB\Update_Suppliers_BankDetails.sql

-- 3. Create stored procedures
Database\FNB\sp_FNB_Payment_Procedures.sql
```

### Step 2: Verify Sandbox Credentials

Check that sandbox credentials were inserted:

```sql
SELECT * FROM FNB_APICredentials WHERE Environment = 'Sandbox'
```

Should show:
- **Client ID**: E84OOE
- **Client Secret**: 621NZsDknRDWjqf8sKhyH0ktjPXtbsr4
- **Debtor Account**: 63001723469
- **Base URL**: https://api.i.fnb.co.za/apigateway

### Step 3: Verify Test Suppliers

Check that test suppliers were created:

```sql
SELECT SupplierID, CompanyName, BankAccountNumber, BankBranchCode 
FROM Suppliers 
WHERE BankAccountNumber IN ('63001730117', '63001731222')
```

Should show:
- **TEST SUPPLIER 1 - SANDBOX** → Account: 63001730117
- **TEST SUPPLIER 2 - SANDBOX** → Account: 63001731222

---

## 🚀 HOW TO USE

### Making Payments

1. **Open Payment Batch Form**
   - Navigate to: Accounting → Payment Batch

2. **Load Suppliers**
   - Click **"Load"** button
   - System loads all active suppliers with bank details
   - Sample invoices are generated for testing

3. **Review Payment List**
   - Check supplier names
   - Verify amounts
   - Confirm bank account numbers (sandbox accounts)

4. **Submit to FNB API**
   - Click **"Submit to FNB API"** (blue button)
   - Review confirmation dialog showing:
     - Number of payments
     - Total amount
     - Execution date
     - Sandbox mode warning
   - Click **"Yes"** to submit

5. **Confirmation**
   - Success message shows:
     - Instruction ID from FNB
     - Batch ID for tracking
   - Grid clears automatically

### Viewing Transactions

1. **Open Transaction Viewer**
   - Click **"View Transactions"** button
   - Or navigate to: Accounting → FNB Transactions

2. **Filter Payments**
   - **From Date**: Start of date range
   - **To Date**: End of date range
   - **Status**: Filter by batch status
     - All
     - Pending (not yet submitted)
     - ACCP (Accepted)
     - ACSC (Accepted Settlement Completed)
     - RJCT (Rejected)
     - PDNG (Pending processing)

3. **View Batch Details**
   - Click on any batch in top grid
   - Bottom grid shows all transactions in that batch

4. **Check Payment Status**
   - Select a batch
   - Click **"Check Status"** button
   - System calls FNB API to get latest status
   - Statuses update automatically

5. **View Transaction Details**
   - Select a transaction in bottom grid
   - Click **"View Details"** button
   - Detailed form shows:
     - All transaction information
     - Creditor details
     - Status and rejection reasons
     - Status history timeline

---

## 📊 PAYMENT FLOW

```
1. User loads suppliers with bank details
   ↓
2. User reviews payment list
   ↓
3. User clicks "Submit to FNB API"
   ↓
4. System validates:
   - Bank account numbers present
   - Branch codes present
   - Amounts > 0
   - References ≤ 20 characters
   ↓
5. System builds API request:
   - Creates unique MessageID
   - Calculates control sums
   - Formats all fields per FNB spec
   ↓
6. System calls FNB API:
   - Authenticates with OAuth 2.0
   - Submits payment batch
   - Receives InstructionID
   ↓
7. System saves to database:
   - Creates batch record
   - Creates transaction records
   - Stores API request/response
   ↓
8. User monitors via Transaction Viewer:
   - Views all batches
   - Checks status periodically
   - Reviews transaction details
   ↓
9. System updates statuses:
   - Calls FNB status API
   - Updates batch status (ACCP → ACSC)
   - Updates transaction statuses (ACCC/RJCT)
   - Logs all status changes
```

---

## 🔐 SANDBOX TESTING

### Test Environment Details

**Environment**: Integration/Sandbox  
**Purpose**: Testing without real money transfers  
**Base URL**: https://api.i.fnb.co.za/apigateway

### Test Accounts

#### Debtor Accounts (Our Accounts - Money Going Out)
1. **63001723469** - Primary test account
2. **63001731248** - Secondary test account

#### Beneficiary Accounts (Supplier Accounts - Money Going In)
1. **63001730117** - Test Supplier 1
2. **63001731222** - Test Supplier 2

### Test Credentials

- **Client ID**: E84OOE
- **Client Secret**: 621NZsDknRDWjqf8sKhyH0ktjPXtbsr4
- **Scope**: i_can

### Important Notes

⚠️ **SANDBOX MODE ACTIVE**
- All payments use test accounts
- No real money is transferred
- Test data only
- Marked clearly in UI

---

## 📋 STATUS CODES

### Batch Status Codes

| Code | Description | Meaning |
|------|-------------|---------|
| **Pending** | Not yet submitted | Batch created but not sent to API |
| **ACCP** | Accepted | FNB accepted the batch for processing |
| **ACSC** | Accepted Settlement Completed | All payments processed successfully |
| **RJCT** | Rejected | Batch rejected by FNB |
| **PDNG** | Pending | Awaiting processing |

### Transaction Status Codes

| Code | Description | Meaning |
|------|-------------|---------|
| **Pending** | Not yet submitted | Transaction created but not sent |
| **ACCC** | Accepted Settlement Completed | Payment successful ✅ |
| **RJCT** | Rejected | Payment failed ❌ |
| **PDNG** | Pending | Awaiting processing |
| **ACSP** | Accepted Settlement In Process | Being processed |

### Rejection Reason Codes

| Code | Description | Solution |
|------|-------------|----------|
| **UN20** | Missing mandatory reference | Add remittance reference |
| **AC01** | Incorrect account number | Verify creditor account |
| **AC04** | Closed account | Update supplier bank details |
| **AC06** | Blocked account | Contact supplier |
| **AM04** | Insufficient funds | Ensure debtor account has balance |
| **BE05** | Unrecognized initiating party | Verify BIC codes |
| **DT01** | Invalid date | Check execution date format |
| **FF01** | Invalid file format | Check JSON structure |
| **RR01** | Missing debtor account | Include debtor account |
| **RR02** | Missing debtor name | Include debtor name |
| **RR03** | Missing creditor account | Include creditor account |
| **RR04** | Missing creditor name | Include creditor name |

---

## ⚠️ CRITICAL LIMITATIONS

### 1. Reference Field Limitation (20 Characters)

**MOST IMPORTANT**: Only the **first 20 characters** of `remittanceInformationUnstructured` are processed by FNB for LOAN/TRNS/SBSH/GRCP accounts.

**System Handles This Automatically**:
- Full reference stored in `RemittanceReference` (30 chars)
- Truncated reference stored in `RemittanceReference20` (20 chars)
- API sends only first 20 characters

**Best Practices**:
- Keep invoice numbers under 20 characters
- Use formats like: `INV-001234`, `PAY-20240123-001`
- Avoid: `Invoice Number 001234` (too long)

### 2. Control Sum Validation

FNB validates that:
- `groupHeader.totalControlSum` = sum of all transaction amounts
- `paymentInformation.controlSum` = sum of transactions in batch

**System Handles This Automatically**:
- Calculates sums programmatically
- Validates before submission

### 3. Unique Message IDs

Each batch needs unique `messageId`.

**System Handles This Automatically**:
- Format: `OD-yyyyMMddHHmmss-GUID`
- Example: `OD-20240123103045-A1B2C3D4`

---

## 🔄 AUTOMATED STATUS CHECKING

### Manual Status Check
- Open Transaction Viewer
- Select a batch
- Click "Check Status" button
- System calls FNB API immediately

### Automated Status Check (Future Enhancement)
Can be implemented as scheduled task:

```vb.net
' Run every 15 minutes
Dim paymentService As New FNBPaymentExecutionService(connectionString, "Sandbox")
paymentService.CheckPaymentStatuses()
```

---

## 📁 FILE STRUCTURE

```
Oven-Delights-ERP/
├── Database/
│   └── FNB/
│       ├── Create_FNB_Payment_Tables.sql
│       ├── Update_Suppliers_BankDetails.sql
│       └── sp_FNB_Payment_Procedures.sql
├── Services/
│   ├── FNBPaymentAPIClient.vb
│   └── FNBPaymentExecutionService.vb
├── Forms/
│   └── Accounting/
│       ├── PaymentBatchForm.vb (Enhanced)
│       ├── PaymentBatchForm.Designer.vb (Enhanced)
│       ├── FNBTransactionViewerForm.vb (New)
│       ├── FNBTransactionViewerForm.Designer.vb (New)
│       ├── FNBTransactionDetailsForm.vb (New)
│       └── FNBTransactionDetailsForm.Designer.vb (New)
└── Documentation/
    ├── FNB_Payment_Execution_API_Guide.md
    ├── FNB_API_Technical_Specifications.md
    ├── FNB_Integration_Guide_and_Questions.md
    └── FNB_Payment_Implementation_README.md (This file)
```

---

## 🎓 TRAINING USERS

### For Finance Team

1. **Making Payments**
   - Load suppliers
   - Review amounts
   - Submit to FNB
   - Verify confirmation

2. **Monitoring Payments**
   - Open transaction viewer
   - Check batch status
   - Review rejections
   - Reprocess failed payments

3. **Troubleshooting**
   - Check rejection codes
   - Verify supplier bank details
   - Contact suppliers if needed

### For System Administrators

1. **Database Maintenance**
   - Monitor table sizes
   - Archive old batches
   - Review error logs

2. **API Credentials**
   - Stored in `FNB_APICredentials` table
   - Encrypted (should be)
   - Separate sandbox/production

3. **Status Monitoring**
   - Check pending batches regularly
   - Investigate stuck batches
   - Review API response logs

---

## 🚨 TROUBLESHOOTING

### Payment Submission Fails

**Check**:
1. API credentials are correct
2. Network connectivity to FNB
3. Supplier has bank account details
4. Reference length ≤ 20 characters
5. Amount > 0

**View**:
- `FNB_PaymentBatches.ErrorDetails`
- `FNB_PaymentBatches.APIResponseJSON`

### Status Not Updating

**Check**:
1. InstructionID is present
2. Batch status is ACCP or PDNG
3. Network connectivity
4. API credentials valid

**Action**:
- Click "Check Status" manually
- Review `FNB_PaymentStatusLog` table

### Transaction Rejected

**Check**:
1. Rejection reason code in transaction details
2. Supplier bank account valid
3. Account not closed/blocked
4. Sufficient funds in debtor account

**Action**:
- Fix issue (update bank details, add funds)
- Resubmit payment in new batch

---

## 🔜 PRODUCTION DEPLOYMENT

### Before Going Live

1. **Get Production Credentials from FNB**
   - Production Client ID
   - Production Client Secret
   - Production account numbers

2. **Update FNB_APICredentials Table**
   ```sql
   UPDATE FNB_APICredentials
   SET ClientID = 'PRODUCTION_CLIENT_ID',
       ClientSecret = 'PRODUCTION_CLIENT_SECRET',
       BaseURL = 'https://api.fnb.co.za/apigateway',
       TokenURL = 'https://api.fnb.co.za/apigateway/oauth2/token/v2',
       DebtorAccountNumber = 'PRODUCTION_ACCOUNT',
       IsActive = 1,
       IsSandbox = 0
   WHERE Environment = 'Production'
   ```

3. **Update Supplier Bank Details**
   - Replace sandbox accounts with real supplier bank accounts
   - Verify all bank details with suppliers
   - Test with small amounts first

4. **Change Environment in Code**
   ```vb.net
   ' Change from "Sandbox" to "Production"
   Dim paymentService As New FNBPaymentExecutionService(connectionString, "Production")
   ```

5. **Remove Sandbox Warnings**
   - Update form titles
   - Remove "SANDBOX MODE" labels
   - Update confirmation messages

6. **Test Thoroughly**
   - Submit small test payment
   - Verify funds transferred
   - Check supplier statements
   - Confirm references appear correctly

---

## ✅ IMPLEMENTATION CHECKLIST

- [x] Database tables created
- [x] Stored procedures created
- [x] Suppliers table enhanced with bank fields
- [x] Test suppliers created with sandbox accounts
- [x] Sandbox credentials inserted
- [x] API client service created
- [x] Payment execution service created
- [x] PaymentBatchForm enhanced with FNB API button
- [x] Transaction viewer form created
- [x] Transaction details form created
- [x] OAuth 2.0 authentication implemented
- [x] Payment initiation implemented
- [x] Status checking implemented
- [x] Error handling implemented
- [x] Validation implemented
- [x] UI feedback implemented
- [x] Documentation created

---

## 📞 SUPPORT

### For Technical Issues
- Review error messages in `FNB_PaymentBatches.ErrorDetails`
- Check API response in `FNB_PaymentBatches.APIResponseJSON`
- Review status log in `FNB_PaymentStatusLog`

### For FNB API Issues
- Contact FNB API support
- Reference your InstructionID
- Provide MessageID from batch

---

## 📝 VERSION HISTORY

**Version 1.0** - January 23, 2026
- Initial implementation
- Sandbox testing ready
- Full UI integration
- Automated payment processing
- Status monitoring
- Transaction tracking

---

**IMPLEMENTATION STATUS: COMPLETE ✅**

All components have been implemented and are ready for testing with FNB sandbox environment.

---
