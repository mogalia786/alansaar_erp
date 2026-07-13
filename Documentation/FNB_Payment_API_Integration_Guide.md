# FNB Payment API Integration Guide
## Oven Delights ERP System

**Version:** 1.0  
**Last Updated:** February 20, 2026  
**Author:** Development Team  

---

## Table of Contents

1. [Overview](#overview)
2. [The Perfect Payload Structure](#the-perfect-payload-structure)
3. [Current Implementation - Bulk Payments](#current-implementation---bulk-payments)
4. [Future Implementation - Supplier Invoices](#future-implementation---supplier-invoices)
5. [Future Implementation - Adhoc Payments](#future-implementation---adhoc-payments)
6. [Proof of Payment (POP) Configuration](#proof-of-payment-pop-configuration)
7. [FNB Statement API Integration](#fnb-statement-api-integration)
8. [Automatic Ledger Account Mapping](#automatic-ledger-account-mapping)
9. [Testing vs Production](#testing-vs-production)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This document provides comprehensive guidance on integrating with the FNB Payment Execution API for all payment types in the Oven Delights ERP system. The integration ensures:

- ✅ Payments are processed through FNB's secure API
- ✅ Proof of Payment (POP) is automatically sent to designated email addresses
- ✅ Payments appear on FNB bank statements with proper references
- ✅ Automatic reconciliation through statement mapping to ledger accounts

---

## The Perfect Payload Structure

### Required Fields for POP (Proof of Payment)

FNB requires the following fields in the payment payload to send Proof of Payment:

```json
{
  "remittanceInformationUnstructured": "INV-20260220141",
  "remittanceLocationMethod": "EMAL",
  "remittanceLocationElectronicAddress": "recipient@email.com"
}
```

### Field Descriptions

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `remittanceInformationUnstructured` | String | Yes | Payment reference (max 20 chars) | "INV-20260220141" |
| `remittanceLocationMethod` | String | **Yes for POP** | Method for sending POP. Use "EMAL" for email | "EMAL" |
| `remittanceLocationElectronicAddress` | String | **Yes for POP** | Email address to receive POP | "supplier@email.com" |

### Complete Payment Transaction Structure

```json
{
  "endToEndId": "INV-20260220141",
  "amount": {
    "currency": "ZAR",
    "value": 1150.0
  },
  "creditor": {
    "name": "Supplier Name",
    "bicOrBEI": "FIRNZAJJ"
  },
  "creditorAccount": {
    "accountNumber": "6300730117",
    "accountType": "CACC"
  },
  "creditorAgent": {
    "branchId": "250655"
  },
  "remittanceInformationUnstructured": "INV-20260220141",
  "remittanceLocationMethod": "EMAL",
  "remittanceLocationElectronicAddress": "supplier@email.com"
}
```

---

## Current Implementation - Bulk Payments

### Location
**File:** `Forms/Accounting/BatchPaymentForm.vb`  
**Method:** `btnSubmitFNB_Click` (Lines 806-1000)

### How It Works

1. **User selects invoices** to pay in the Batch Payment Form
2. **Creates payment batch** with execution date
3. **Builds PaymentLineInfo objects** for each invoice
4. **Submits to FNB API** via `FNBPaymentExecutionService`

### Code Implementation

```vb
' Build payment lines from batch (Line 895-948)
Dim paymentLines As New List(Of PaymentLineInfo)()

Using conn As New SqlConnection(connectionString)
    conn.Open()
    
    Dim sql As String = "
        SELECT 
            i.InvoiceID,
            i.InvoiceNumber,
            i.TotalAmount,
            b.BeneficiaryID,
            b.BeneficiaryName,
            b.AccountNumber,
            b.BranchCode,
            b.Email
        FROM AP_Invoices i
        INNER JOIN AP_Beneficiaries b ON i.BeneficiaryID = b.BeneficiaryID
        WHERE i.InvoiceID IN ({invoiceIds})"
    
    Using cmd As New SqlCommand(sql, conn)
        Using reader As SqlDataReader = cmd.ExecuteReader()
            While reader.Read()
                Dim line As New PaymentLineInfo() With {
                    .SupplierID = invoiceID,
                    .PaymentType = "Beneficiary",
                    .CreditorName = reader.GetString(reader.GetOrdinal("BeneficiaryName")),
                    .CreditorAccountNumber = reader.GetString(reader.GetOrdinal("AccountNumber")),
                    .CreditorAccountType = "CACC",
                    .CreditorBranchCode = reader.GetString(reader.GetOrdinal("BranchCode")),
                    .CreditorBIC = "FIRNZAJJ",
                    .Amount = amount,
                    .Reference = invoiceNum.Substring(0, Math.Min(20, invoiceNum.Length)),
                    .ProofOfPaymentEmail = "tshepo.kgasoane@rmb.co.za"  ' FNB test email
                }
                
                paymentLines.Add(line)
            End While
        End Using
    End Using
End Using

' Submit to FNB API
Dim fnbService As New FNBPaymentExecutionService(connectionString, "Sandbox")
Dim result = fnbService.CreateAndSubmitPaymentBatch(
    paymentLines,
    dtpPaymentDate.Value,
    AppSession.CurrentBranchID,
    AppSession.CurrentUserID
)
```

### Service Layer Implementation

**File:** `Services/FNBPaymentExecutionService.vb`  
**Method:** `BuildPaymentRequest` (Lines 155-229)

```vb
' Build transaction with POP fields (Lines 198-221)
For Each line In paymentLines
    Dim transaction As New CreditTransferTransaction() With {
        .endToEndId = line.Reference,
        .amount = New Amount() With {
            .currency = "ZAR",
            .value = line.Amount
        },
        .creditor = New Creditor() With {
            .name = line.CreditorName,
            .bicOrBEI = line.CreditorBIC
        },
        .creditorAccount = New CreditorAccount() With {
            .accountNumber = line.CreditorAccountNumber,
            .accountType = line.CreditorAccountType
        },
        .creditorAgent = New CreditorAgent() With {
            .branchId = line.CreditorBranchCode
        },
        .remittanceInformationUnstructured = Left(line.Reference, 20)
    }

    ' ADD POP FIELDS IF EMAIL PROVIDED
    If Not String.IsNullOrEmpty(line.ProofOfPaymentEmail) Then
        transaction.remittanceLocationMethod = "EMAL"
        transaction.remittanceLocationElectronicAddress = line.ProofOfPaymentEmail
    End If

    paymentInfo.creditTransferTransactionInformation.Add(transaction)
Next
```

### Key Points

✅ **ProofOfPaymentEmail field** is the trigger for POP  
✅ **If email is provided**, FNB sends POP automatically  
✅ **If email is empty**, no POP is sent (payment still processes)  
✅ **Reference field** appears on bank statement (max 20 characters)  

---

## Future Implementation - Supplier Invoices

### Location (To Be Implemented)
**File:** `Forms/Accounting/SupplierPaymentForm.vb`  
**Status:** 🔴 Not Yet Implemented

### Implementation Plan

When implementing FNB API for supplier invoice payments:

1. **Find the payment submission code** in `SupplierPaymentForm.vb`
2. **Create PaymentLineInfo objects** similar to bulk payments
3. **Add ProofOfPaymentEmail field** to each payment line
4. **Call FNBPaymentExecutionService** instead of direct database insert

### Code Template

```vb
' Example implementation for SupplierPaymentForm.vb
Private Sub btnPayInvoice_Click(sender As Object, e As EventArgs)
    Try
        ' Get supplier and invoice details
        Dim supplierID As Integer = GetSelectedSupplierID()
        Dim invoiceID As Integer = GetSelectedInvoiceID()
        Dim amount As Decimal = GetPaymentAmount()
        Dim reference As String = GetInvoiceNumber()
        
        ' Get supplier banking details
        Dim bankDetails = GetSupplierBankDetails(supplierID)
        
        ' Create payment line
        Dim paymentLine As New PaymentLineInfo() With {
            .SupplierID = supplierID,
            .PurchaseInvoiceID = invoiceID,
            .PaymentType = "Supplier",
            .CreditorName = bankDetails.SupplierName,
            .CreditorAccountNumber = bankDetails.AccountNumber,
            .CreditorAccountType = "CACC",
            .CreditorBranchCode = bankDetails.BranchCode,
            .CreditorBIC = "FIRNZAJJ",
            .Amount = amount,
            .Reference = reference.Substring(0, Math.Min(20, reference.Length)),
            .ProofOfPaymentEmail = GetSupplierEmail(supplierID)  ' Or branch email
        }
        
        ' Submit to FNB API
        Dim fnbService As New FNBPaymentExecutionService(connectionString, "Sandbox")
        Dim paymentLines As New List(Of PaymentLineInfo) From {paymentLine}
        
        Dim result = fnbService.CreateAndSubmitPaymentBatch(
            paymentLines,
            DateTime.Now,
            AppSession.CurrentBranchID,
            AppSession.CurrentUserID
        )
        
        If result.Item1 Then
            MessageBox.Show("Payment submitted successfully!", "Success")
        Else
            MessageBox.Show($"Payment failed: {result.Item2}", "Error")
        End If
        
    Catch ex As Exception
        MessageBox.Show($"Error: {ex.Message}", "Error")
    End Try
End Sub
```

### Required Database Fields

Ensure the following fields exist in your Suppliers/Beneficiaries table:

| Field | Type | Description |
|-------|------|-------------|
| `AccountNumber` | VARCHAR(20) | Bank account number |
| `BranchCode` | VARCHAR(10) | Bank branch code |
| `AccountType` | VARCHAR(10) | Account type (CACC, SVGS, etc.) |
| `Email` | VARCHAR(100) | Email for POP delivery |
| `BIC` | VARCHAR(11) | Bank Identifier Code (optional) |

---

## Future Implementation - Adhoc Payments

### Location (To Be Implemented)
**File:** `Forms/Accounting/AdhocPaymentForm.vb` (or similar)  
**Status:** 🔴 Not Yet Implemented

### Use Cases

- Utility payments (electricity, water, etc.)
- Once-off vendor payments
- Refunds to customers
- Petty cash reimbursements
- Any payment not linked to a supplier invoice

### Implementation Plan

```vb
' Example implementation for adhoc payments
Private Sub btnMakeAdhocPayment_Click(sender As Object, e As EventArgs)
    Try
        ' Get payment details from form
        Dim creditorName As String = txtCreditorName.Text
        Dim accountNumber As String = txtAccountNumber.Text
        Dim branchCode As String = txtBranchCode.Text
        Dim amount As Decimal = CDec(txtAmount.Text)
        Dim reference As String = txtReference.Text
        Dim popEmail As String = txtEmailForPOP.Text
        
        ' Create payment line
        Dim paymentLine As New PaymentLineInfo() With {
            .SupplierID = Nothing,  ' No supplier for adhoc
            .ExpenseBillID = Nothing,  ' Could link to expense if needed
            .PaymentType = "Adhoc",
            .CreditorName = creditorName,
            .CreditorAccountNumber = accountNumber,
            .CreditorAccountType = "CACC",
            .CreditorBranchCode = branchCode,
            .CreditorBIC = "FIRNZAJJ",
            .Amount = amount,
            .Reference = reference.Substring(0, Math.Min(20, reference.Length)),
            .ProofOfPaymentEmail = If(String.IsNullOrEmpty(popEmail), 
                                     "accounts@ovendelights.co.za",  ' Default to branch email
                                     popEmail)
        }
        
        ' Submit to FNB API
        Dim fnbService As New FNBPaymentExecutionService(connectionString, "Sandbox")
        Dim paymentLines As New List(Of PaymentLineInfo) From {paymentLine}
        
        Dim result = fnbService.CreateAndSubmitPaymentBatch(
            paymentLines,
            dtpPaymentDate.Value,
            AppSession.CurrentBranchID,
            AppSession.CurrentUserID
        )
        
        If result.Item1 Then
            ' Record in database for tracking
            RecordAdhocPayment(paymentLine, result.Item3)  ' result.Item3 is BatchID
            MessageBox.Show("Adhoc payment submitted successfully!", "Success")
        Else
            MessageBox.Show($"Payment failed: {result.Item2}", "Error")
        End If
        
    Catch ex As Exception
        MessageBox.Show($"Error: {ex.Message}", "Error")
    End Try
End Sub
```

---

## Proof of Payment (POP) Configuration

### Testing Environment

**Current Configuration:**
```vb
.ProofOfPaymentEmail = "tshepo.kgasoane@rmb.co.za"  ' FNB test email
```

**Purpose:** FNB uses this email to verify that POP is being sent correctly during testing.

### Production Environment

**Option 1: Branch Email (Recommended)**
```vb
.ProofOfPaymentEmail = "accounts@ovendelights.co.za"
```

**Option 2: Supplier/Beneficiary Email**
```vb
.ProofOfPaymentEmail = If(reader("Email") Is DBNull.Value, 
                         "accounts@ovendelights.co.za",  ' Fallback to branch
                         reader.GetString(reader.GetOrdinal("Email")))
```

**Option 3: Dynamic Based on Payment Type**
```vb
' For supplier payments - send to supplier
.ProofOfPaymentEmail = supplierEmail

' For utility payments - send to branch accounts
.ProofOfPaymentEmail = "accounts@ovendelights.co.za"

' For refunds - send to customer
.ProofOfPaymentEmail = customerEmail
```

### POP Email Best Practices

✅ **Always provide an email** - ensures POP is sent  
✅ **Use valid email addresses** - FNB validates format  
✅ **Have a fallback email** - branch accounts email  
✅ **Test with FNB email first** - verify POP delivery works  
✅ **Document email strategy** - who receives POP for what payment type  

---

## FNB Statement API Integration

### Overview

The FNB Statement API provides transaction details that appear on your bank statement. This is crucial for:

- ✅ Automatic reconciliation
- ✅ Matching payments to invoices
- ✅ Posting to correct ledger accounts
- ✅ Audit trail

### Statement API Response Structure

```json
{
  "transactions": [
    {
      "transactionId": "TXN-123456789",
      "transactionDate": "2026-02-20",
      "valueDate": "2026-02-20",
      "amount": {
        "currency": "ZAR",
        "value": -1150.00
      },
      "description": "Payment to Supplier",
      "reference": "INV-20260220141",
      "creditorName": "Durban Electricity",
      "creditorAccount": "6300730117",
      "instructionId": "OD-20260220-ABC123",
      "status": "BOOK",
      "balance": {
        "currency": "ZAR",
        "value": 45850.00
      }
    }
  ]
}
```

### Key Fields for Reconciliation

| Field | Description | Use for Mapping |
|-------|-------------|-----------------|
| `reference` | Payment reference (max 20 chars) | **PRIMARY** - Match to invoice number |
| `creditorName` | Beneficiary/Supplier name | **SECONDARY** - Match to supplier |
| `creditorAccount` | Beneficiary account number | Verify correct recipient |
| `instructionId` | FNB instruction ID | Link to batch payment |
| `amount.value` | Transaction amount | Verify payment amount |
| `transactionDate` | Date transaction processed | Posting date |
| `description` | Transaction description | Additional context |

---

## Automatic Ledger Account Mapping

### Mapping Strategy

To automatically post FNB statement transactions to the correct ledger accounts, use a **multi-level matching strategy**:

### Level 1: Reference Number Matching (Highest Priority)

```vb
' Match by reference number (invoice number)
Function MapToLedgerByReference(reference As String) As Integer?
    Using conn As New SqlConnection(connectionString)
        conn.Open()
        
        ' Try to find invoice by reference
        Dim sql = "
            SELECT TOP 1 
                i.InvoiceID,
                i.ExpenseAccountID,
                i.SupplierID
            FROM AP_Invoices i
            WHERE i.InvoiceNumber = @Reference
              AND i.PaymentStatus <> 'Paid'"
        
        Using cmd As New SqlCommand(sql, conn)
            cmd.Parameters.AddWithValue("@Reference", reference)
            Using reader = cmd.ExecuteReader()
                If reader.Read() Then
                    ' Found invoice - use its expense account
                    Return reader.GetInt32(reader.GetOrdinal("ExpenseAccountID"))
                End If
            End Using
        End Using
    End Using
    
    Return Nothing  ' No match found
End Function
```

### Level 2: Creditor Name Matching (Medium Priority)

```vb
' Match by creditor/supplier name
Function MapToLedgerByCreditor(creditorName As String) As Integer?
    Using conn As New SqlConnection(connectionString)
        conn.Open()
        
        ' Find supplier by name
        Dim sql = "
            SELECT TOP 1 
                s.SupplierID,
                s.DefaultExpenseAccountID
            FROM Suppliers s
            WHERE s.SupplierName LIKE @CreditorName
              AND s.IsActive = 1"
        
        Using cmd As New SqlCommand(sql, conn)
            cmd.Parameters.AddWithValue("@CreditorName", "%" & creditorName & "%")
            Using reader = cmd.ExecuteReader()
                If reader.Read() Then
                    ' Found supplier - use default expense account
                    If Not reader.IsDBNull(reader.GetOrdinal("DefaultExpenseAccountID")) Then
                        Return reader.GetInt32(reader.GetOrdinal("DefaultExpenseAccountID"))
                    End If
                End If
            End Using
        End Using
    End Using
    
    Return Nothing  ' No match found
End Function
```

### Level 3: Instruction ID Matching (Batch Payments)

```vb
' Match by FNB instruction ID (for batch payments)
Function MapToLedgerByInstructionId(instructionId As String) As List(Of LedgerMapping)
    Dim mappings As New List(Of LedgerMapping)()
    
    Using conn As New SqlConnection(connectionString)
        conn.Open()
        
        ' Find batch and its transactions
        Dim sql = "
            SELECT 
                bt.TransactionID,
                bt.InvoiceID,
                i.ExpenseAccountID,
                bt.Amount
            FROM FNB_BatchTransactions bt
            INNER JOIN FNB_Batches b ON bt.BatchID = b.BatchID
            INNER JOIN AP_Invoices i ON bt.InvoiceID = i.InvoiceID
            WHERE b.InstructionID = @InstructionId"
        
        Using cmd As New SqlCommand(sql, conn)
            cmd.Parameters.AddWithValue("@InstructionId", instructionId)
            Using reader = cmd.ExecuteReader()
                While reader.Read()
                    mappings.Add(New LedgerMapping With {
                        .InvoiceID = reader.GetInt32(reader.GetOrdinal("InvoiceID")),
                        .LedgerAccountID = reader.GetInt32(reader.GetOrdinal("ExpenseAccountID")),
                        .Amount = reader.GetDecimal(reader.GetOrdinal("Amount"))
                    })
                End While
            End Using
        End Using
    End Using
    
    Return mappings
End Function
```

### Level 4: Default Account (Fallback)

```vb
' Use default suspense account if no match found
Function GetDefaultSuspenseAccount() As Integer
    ' Return suspense account ID for manual review
    Return 9999  ' Example: "Unallocated Payments" account
End Function
```

### Complete Mapping Function

```vb
Public Function MapStatementToLedger(
    reference As String,
    creditorName As String,
    instructionId As String,
    amount As Decimal
) As LedgerMappingResult
    
    Dim result As New LedgerMappingResult()
    
    ' Level 1: Try reference number first
    Dim accountId = MapToLedgerByReference(reference)
    If accountId.HasValue Then
        result.LedgerAccountID = accountId.Value
        result.MappingMethod = "Reference"
        result.Confidence = "High"
        Return result
    End If
    
    ' Level 2: Try instruction ID (batch payments)
    Dim batchMappings = MapToLedgerByInstructionId(instructionId)
    If batchMappings.Count > 0 Then
        result.LedgerMappings = batchMappings
        result.MappingMethod = "InstructionID"
        result.Confidence = "High"
        Return result
    End If
    
    ' Level 3: Try creditor name
    accountId = MapToLedgerByCreditor(creditorName)
    If accountId.HasValue Then
        result.LedgerAccountID = accountId.Value
        result.MappingMethod = "Creditor"
        result.Confidence = "Medium"
        Return result
    End If
    
    ' Level 4: Use suspense account
    result.LedgerAccountID = GetDefaultSuspenseAccount()
    result.MappingMethod = "Suspense"
    result.Confidence = "Low"
    result.RequiresManualReview = True
    
    Return result
End Function

Public Class LedgerMappingResult
    Public Property LedgerAccountID As Integer
    Public Property LedgerMappings As List(Of LedgerMapping)
    Public Property MappingMethod As String
    Public Property Confidence As String
    Public Property RequiresManualReview As Boolean
End Class

Public Class LedgerMapping
    Public Property InvoiceID As Integer
    Public Property LedgerAccountID As Integer
    Public Property Amount As Decimal
End Class
```

### Database Schema for Mapping

**Recommended Tables:**

```sql
-- Store statement transactions
CREATE TABLE FNB_StatementTransactions (
    TransactionID INT IDENTITY(1,1) PRIMARY KEY,
    StatementDate DATE NOT NULL,
    TransactionDate DATE NOT NULL,
    ValueDate DATE NOT NULL,
    Reference VARCHAR(20),
    CreditorName VARCHAR(100),
    CreditorAccount VARCHAR(20),
    InstructionID VARCHAR(50),
    Amount DECIMAL(18,2) NOT NULL,
    Description VARCHAR(255),
    Status VARCHAR(20),
    LedgerAccountID INT,  -- Mapped ledger account
    MappingMethod VARCHAR(20),  -- How it was mapped
    MappingConfidence VARCHAR(20),  -- High/Medium/Low
    IsReconciled BIT DEFAULT 0,
    ReconciledBy INT,
    ReconciledDate DATETIME,
    CreatedDate DATETIME DEFAULT GETDATE()
)

-- Link suppliers to default expense accounts
ALTER TABLE Suppliers
ADD DefaultExpenseAccountID INT NULL

-- Link invoices to expense accounts
ALTER TABLE AP_Invoices
ADD ExpenseAccountID INT NULL
```

### Reconciliation Workflow

```vb
' Example reconciliation process
Public Sub ReconcileStatementTransactions(statementDate As Date)
    Try
        ' 1. Fetch statement from FNB API
        Dim fnbClient As New FNBStatementAPIClient(connectionString)
        Dim transactions = fnbClient.GetStatementTransactions(statementDate)
        
        ' 2. Process each transaction
        For Each txn In transactions
            ' Map to ledger account
            Dim mapping = MapStatementToLedger(
                txn.reference,
                txn.creditorName,
                txn.instructionId,
                txn.amount.value
            )
            
            ' Save to database
            SaveStatementTransaction(txn, mapping)
            
            ' If high confidence, auto-reconcile
            If mapping.Confidence = "High" AndAlso Not mapping.RequiresManualReview Then
                AutoReconcileTransaction(txn, mapping)
            Else
                ' Flag for manual review
                FlagForManualReview(txn, mapping)
            End If
        Next
        
        MessageBox.Show("Statement reconciliation complete!", "Success")
        
    Catch ex As Exception
        MessageBox.Show($"Reconciliation error: {ex.Message}", "Error")
    End Try
End Sub
```

---

## Testing vs Production

### Environment Configuration

**File:** `Services/FNBPaymentAPIClient.vb`

```vb
Public Sub New(connectionString As String, Optional environment As String = "Sandbox")
    _connectionString = connectionString
    
    If environment.ToUpper() = "SANDBOX" Then
        _baseUrl = "https://api.sandbox.fnb.co.za/payment-initiation/v1"
        _authUrl = "https://api.sandbox.fnb.co.za/oauth/token"
    Else
        _baseUrl = "https://api.fnb.co.za/payment-initiation/v1"
        _authUrl = "https://api.fnb.co.za/oauth/token"
    End If
End Sub
```

### Testing Checklist

Before going live, verify:

- ✅ POP is sent to FNB test email (`tshepo.kgasoane@rmb.co.za`)
- ✅ Payment appears on FNB sandbox statement
- ✅ Reference number appears correctly on statement
- ✅ Amount is correct
- ✅ Creditor name matches
- ✅ Statement API returns transaction details
- ✅ Automatic mapping to ledger accounts works
- ✅ Reconciliation process completes successfully

### Production Deployment

1. **Update POP email** to branch email or supplier email
2. **Change environment** from "Sandbox" to "Production"
3. **Update API credentials** to production credentials
4. **Test with small payment** first
5. **Monitor statement** for correct posting
6. **Verify reconciliation** works correctly

---

## Troubleshooting

### POP Not Being Sent

**Problem:** FNB is not sending Proof of Payment

**Solutions:**
1. Verify `ProofOfPaymentEmail` is not empty
2. Verify `remittanceLocationMethod` is set to "EMAL"
3. Verify `remittanceLocationElectronicAddress` contains valid email
4. Check FNB API response for errors
5. Verify email address format is valid

### Payment Not Appearing on Statement

**Problem:** Payment processed but not on statement

**Solutions:**
1. Check payment status via FNB Status API
2. Verify `instructionId` was returned
3. Check if payment is still pending (PDNG status)
4. Wait for value date (may be next business day)
5. Contact FNB support with instruction ID

### Reference Not Showing on Statement

**Problem:** Reference field is blank on statement

**Solutions:**
1. Verify `remittanceInformationUnstructured` is populated
2. Check reference length (max 20 characters)
3. Verify no special characters causing issues
4. Check FNB API response for truncation warnings

### Automatic Mapping Failing

**Problem:** Transactions going to suspense account

**Solutions:**
1. Verify invoice numbers match exactly
2. Check supplier names for typos
3. Ensure `DefaultExpenseAccountID` is set for suppliers
4. Review mapping confidence levels
5. Add manual mapping rules for common cases

---

## Summary

### Current Status

✅ **Bulk Payments** - Implemented with FNB API integration  
✅ **POP Configuration** - Using FNB test email for testing  
✅ **Service Layer** - `FNBPaymentExecutionService` handles all API calls  
✅ **Payload Structure** - Perfect payload with all required fields  

### Next Steps

🔴 **Supplier Invoice Payments** - Apply same pattern to `SupplierPaymentForm.vb`  
🔴 **Adhoc Payments** - Create new form with FNB API integration  
🔴 **Statement API** - Implement automatic statement fetching  
🔴 **Auto Reconciliation** - Implement mapping and reconciliation workflow  
🔴 **Production Deployment** - Switch from sandbox to production  

### Key Takeaways

1. **Always include POP fields** if you want FNB to send Proof of Payment
2. **Reference field is critical** for statement reconciliation
3. **Use multi-level mapping** for automatic ledger account assignment
4. **Test thoroughly** in sandbox before going to production
5. **Document everything** for future reference and troubleshooting

---

**End of Document**

For questions or issues, contact the development team.
