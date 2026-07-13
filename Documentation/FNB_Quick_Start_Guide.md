# FNB Payment API - Quick Start Guide

## ⚠️ IMPORTANT: Install Newtonsoft.Json First

Before testing, you **MUST** install the Newtonsoft.Json NuGet package:

### Option 1: Visual Studio Package Manager
1. Right-click on your project in Solution Explorer
2. Select "Manage NuGet Packages..."
3. Click "Browse" tab
4. Search for "Newtonsoft.Json"
5. Click "Install"

### Option 2: Package Manager Console
```powershell
Install-Package Newtonsoft.Json
```

---

## 🗄️ Database Setup (Run These Scripts in Order)

Execute these SQL scripts in SQL Server Management Studio:

1. **`Database\FNB\Create_FNB_Payment_Tables.sql`**
   - Creates FNB payment tables
   - Inserts sandbox credentials

2. **`Database\FNB\Update_Suppliers_BankDetails.sql`**
   - Adds bank fields to Suppliers table
   - Creates 2 test suppliers with sandbox accounts

3. **`Database\FNB\sp_FNB_Payment_Procedures.sql`**
   - Creates stored procedures for payment management

---

## 🎯 What Was Added to Your Form

### BatchPaymentForm Enhancements:

**Two new buttons added to the "Current Batch Items" section:**

1. **"Submit to FNB API"** (Blue button)
   - Submits the current batch to FNB Payment Execution API
   - Shows sandbox warning
   - Validates supplier bank details
   - Returns FNB Instruction ID

2. **"View Transactions"** (Light blue button)
   - Opens transaction viewer
   - Shows all FNB payment batches
   - Allows status checking
   - Displays transaction details

---

## 🚀 How to Test

### Step 1: Run Database Scripts
Execute all 3 SQL scripts listed above.

### Step 2: Install Newtonsoft.Json
Use one of the methods shown at the top of this guide.

### Step 3: Rebuild Project
- Build → Rebuild Solution
- Fix any remaining compilation errors

### Step 4: Test Payment Submission

1. **Open Batch Invoice Payment form**
   - Navigate to: Accounting → Batch Invoice Payment

2. **Create a batch**
   - Select payment date
   - Select payment method: EFT
   - Select bank account
   - Click "Create Batch"

3. **Add invoices**
   - Check the invoices you want to pay
   - Click "Add Selected to Batch"
   - Invoices appear in "Current Batch Items"

4. **Submit to FNB API**
   - Click the blue **"Submit to FNB API"** button
   - Review confirmation dialog showing:
     - Sandbox mode warning
     - Total amount
     - Payment date
   - Click "Yes" to submit

5. **View results**
   - Success message shows FNB Instruction ID
   - Click **"View Transactions"** to monitor status

---

## 🔍 Viewing Transactions

The **"View Transactions"** button opens a form showing:

### Top Grid: Payment Batches
- Batch ID
- Message ID (unique identifier)
- Instruction ID (from FNB)
- Status (Pending, ACCP, ACSC, RJCT)
- Total amount
- Execution date

### Bottom Grid: Transactions
- Individual payments in selected batch
- Creditor name
- Amount
- Status
- End-to-End ID

### Actions:
- **Check Status**: Updates payment status from FNB API
- **View Details**: Shows complete transaction information

---

## 🔐 Sandbox Test Data

### Test Suppliers Created:
1. **TEST SUPPLIER 1 - SANDBOX**
   - Account: 63001730117
   - Branch: 250655

2. **TEST SUPPLIER 2 - SANDBOX**
   - Account: 63001731222
   - Branch: 250655

### Debtor Account (Your Account):
- Account: 63001723469
- Branch: 250655

### API Credentials:
- Client ID: E84OOE
- Client Secret: 621NZsDknRDWjqf8sKhyH0ktjPXtbsr4
- Environment: Sandbox

---

## ✅ What Happens When You Submit

```
1. System validates batch has items
   ↓
2. Loads supplier bank details from database
   ↓
3. Validates all suppliers have bank accounts
   ↓
4. Builds FNB API payment request
   ↓
5. Authenticates with OAuth 2.0
   ↓
6. Submits to FNB Payment Execution API
   ↓
7. Receives Instruction ID from FNB
   ↓
8. Saves batch and transactions to database
   ↓
9. Shows success message with Instruction ID
```

---

## 📊 Payment Status Codes

| Code | Meaning |
|------|---------|
| **Pending** | Not yet submitted to FNB |
| **ACCP** | Accepted by FNB |
| **ACSC** | Accepted Settlement Completed (Success ✅) |
| **RJCT** | Rejected by FNB (Failed ❌) |
| **PDNG** | Pending processing |

---

## 🐛 Troubleshooting

### "JsonConvert is not declared"
**Solution**: Install Newtonsoft.Json NuGet package (see top of this guide)

### "Supplier has no bank account number"
**Solution**: Run `Update_Suppliers_BankDetails.sql` to add test suppliers

### "Cannot connect to FNB API"
**Solution**: Check internet connection and firewall settings

### Bank account showing "151" instead of account number
**Solution**: This is the SupplierID. The form now queries actual bank account numbers from the Suppliers table after you run the SQL scripts.

---

## 🎓 Next Steps

1. ✅ Install Newtonsoft.Json
2. ✅ Run all 3 SQL scripts
3. ✅ Rebuild project
4. ✅ Test with sandbox data
5. ⏳ Monitor transactions via "View Transactions"
6. ⏳ When ready for production:
   - Get production credentials from FNB
   - Update `FNB_APICredentials` table
   - Replace test supplier accounts with real ones
   - Change environment from "Sandbox" to "Production"

---

## 📁 Files Modified

- `Forms\Accounting\BatchPaymentForm.vb` - Added FNB button handlers
- `Forms\Accounting\BatchPaymentForm.Designer.vb` - Added UI buttons
- `Services\FNBPaymentAPIClient.vb` - API client (created)
- `Services\FNBPaymentExecutionService.vb` - Payment service (created)
- `Forms\Accounting\FNBTransactionViewerForm.vb` - Transaction viewer (created)
- `Forms\Accounting\FNBTransactionDetailsForm.vb` - Details form (created)

---

**You're all set! Install Newtonsoft.Json, run the SQL scripts, and start testing!** 🚀
