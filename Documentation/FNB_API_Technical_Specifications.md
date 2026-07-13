# FNB Transaction History API - Technical Specifications
## Based on Official FNB Documentation

---

## 1. API MESSAGE FORMAT SPECIFICATION

### Field Definition Structure

| Column | Definition |
|--------|------------|
| **Field** | Refers to a JSON field |
| **Name** | Refers to the full name of the field |
| **Multiplicity** | Determines if a field is optional or mandatory, and how many times the field can be repeated as per the base ISO message |
| **R/O/C** | Determines if a field is Required/Optional/Conditional for FNB |
| **FNB Rules** | Defines the FNB restrictions on a field |
| **Additional Information** | Provides general information about the purpose of the field |

### Multiplicity Notation

- **[0..1]** - Field can appear 0 or 1 time. The field is optional.
- **[0..n]** - Field can appear 0 or multiple times. The field is optional.
- **[1..1]** - Field is required and must appear once.
- **[1..n]** - Field is required and must appear at least once. The field can appear multiple times.

**Important**: In case a lower-level field is required while its higher field is optional, the lower level is required only if the higher-level field is present.

### R/O/C Notation

- **R** = Required
- **O** = Optional
- **C** = Conditional. Example: Either the creditor or the ultimate creditor details can be provided. If both are provided the ultimate creditor details will be used.
- **XOR** = This field or the next field, but not both must be populated.

---

## 2. API ENDPOINT STRUCTURE

### 2.1 Query Parameters

| Field | Multiplicity | R/O/C | FNB Rules | Additional Information |
|-------|--------------|-------|-----------|------------------------|
| **fromDate** | 1..1 | R | ISODateTime<br>YYYY-MM-DD | Date at which the message was created.<br>Start value for transaction date range.<br>Transaction on, and newer than fromDate will be returned. |
| **toDate** | 1..1 | R | ISODateTime<br>YYYY-MM-DD | End value for transaction date range.<br>Transaction on, and older than fromDate will be returned. |
| **lastItemKey** | 1..1 | C | Text: Maximum = 15 | Key used to retrieve the next set of items to be returned. This only required if the lastPageIndicator = "false". |

### 2.2 Path Variables

| Field | Multiplicity | R/O/C | FNB Rules | Additional Information |
|-------|--------------|-------|-----------|------------------------|
| **accountNumber** | 1..1 | R | Text: Maximum = 23 | Client account number that Transaction History is being queried for.<br>Only allows one account at a time.<br>Must not only contain zeroes or spaces. |

---

## 3. TRANSACTION HISTORY RESPONSE FIELDS

### 3.1 Response Structure

| Name | Multiplicity | R/O/C | FNB Rules | Additional Information |
|------|--------------|-------|-----------|------------------------|
| **entry** | 1..n | R | - | Specifies an entry in the Transaction History. |
| **entryId** | 1..1 | R | Text: Maximum = 15 | The identification field is assigned by the bank and is used to identify each entry in the Transaction History.<br>The field is not unique and can be repeated within the same date range. |
| **bookingDate** | 1..1 | R | - | Date when an entry is posted to an account on the account servicer's books. |
| **Date** | 1..1 | R | ISODateTime<br>yyyy-mm-dd | Date when an entry is posted to an account on the account servicer's books. |

### 3.2 Transaction Details

| Field | Multiplicity | R/O/C | FNB Rules | Additional Information |
|-------|--------------|-------|-----------|------------------------|
| **valueDate** | 1..1 | R | - | Date at which assets become available to the account owner in case of a credit entry or cease to be available to the account owner in case of a debit entry. |
| **Date** | 1..1 | R | ISODateTime<br>yyyy-mm-dd | Date and time at which assets become available to the account owner in case of a credit entry or cease to be available to the account owner in case of a debit entry. |
| **entryDetails** | - | R | - | Provides further details into the entry. |
| **transactionDetails** | 1..1 | R | - | Provides information on the underlying transaction(s). |
| **remittanceInfo** | 1..1 | R | - | Information supplied to enable the matching of an entry with the items that the transfer is intended to settle, such as commercial invoices in an accounts receivable system. |

### 3.3 Payment Reference Fields

| Field | Multiplicity | R/O/C | FNB Rules | Additional Information |
|-------|--------------|-------|-----------|------------------------|
| **unstructured** | 1..1 | R | Text: Maximum = 30 | This is the reference that will appear on the beneficiary's (recipient's) account statement.<br>**Payments to LOAN, TRNS, SBSH and GRCP FNB accounts will only process the first 20 characters of this field. Must not only contain spaces. Spaces after text will be trimmed.**<br>Where the beneficiary / recipient enforces reference validation on the payment, only the first 20 characters will be validated. |
| **reference** | 1..1 | R | - | Provides the identification of the underlying transaction. |

### 3.4 Transaction Amount Fields

| Field | Multiplicity | R/O/C | FNB Rules | Additional Information |
|-------|--------------|-------|-----------|------------------------|
| **endToEndId** | 1..1 | R | Text: Maximum = 20 | Unique identification, as assigned by the initiating party, to unambiguously identify the transaction. This identification is passed on, unchanged, throughout the entire end-to-end chain. |
| **amount** | 1..1 | R | - | Value of the transaction and the corresponding currency. |
| **amount** | 1..1 | R | Decimal Number<br>Total Digits: 13<br>Fraction Digits: 2 | Value of the transaction. |
| **currency** | 1..1 | R | Code<br>Text: Maximum = 3 | Currency used for the transaction.<br>Currency code as per ISO 4217 three-letter code. |
| **creditDebitIndicator** | 1..1 | R | Code<br>Text: Maximum = 6 | Indicates whether the transaction is a credit or a debit transaction.<br>• CREDIT - for all credit transactions<br>• DEBIT - for all debit transactions. |

### 3.5 Balance Information

| Field | Multiplicity | R/O/C | FNB Rules | Additional Information |
|-------|--------------|-------|-----------|------------------------|
| **availability** | 1..1 | R | - | Identifies the balance available due to that entry. |
| **amount** | 1..1 | R | Decimal Number<br>Total Digits: 13<br>Fraction Digits: 2 | Identifies the value of the available balance in the account. |

---

## 4. KEY TECHNICAL INSIGHTS FOR IMPLEMENTATION

### 4.1 Critical Field Limitations

**Reference Field (unstructured)**
- **Maximum Length**: 30 characters
- **Critical Limitation**: For LOAN, TRNS, SBSH and GRCP FNB accounts, only the **first 20 characters** are processed
- **Validation**: Only first 20 characters validated if beneficiary enforces reference validation
- **Formatting**: Spaces after text will be trimmed
- **Must not contain only spaces**

**Impact on Invoice Matching**:
```
✅ GOOD: "INV-2024-001234" (16 chars)
✅ GOOD: "INV001234" (9 chars)
⚠️  CAUTION: "INVOICE-2024-001234-BRANCH01" (29 chars, but only first 20 used)
❌ BAD: "Invoice Number 2024-001234 Branch 01" (38 chars, truncated)
```

### 4.2 Account Number Restrictions

- **Maximum Length**: 23 characters
- **Single Account Only**: API only allows querying one account at a time
- **Validation**: Must not contain only zeroes or spaces
- **Implication**: For multi-branch operations, must make separate API calls per account

### 4.3 Date Range Query

- **Format**: ISO DateTime (YYYY-MM-DD)
- **fromDate**: Required - Start of transaction date range (inclusive)
- **toDate**: Required - End of transaction date range (inclusive)
- **Behavior**: Returns transactions on or between these dates

**Recommended Query Strategy**:
```
Daily Sync: fromDate = yesterday, toDate = today
Initial Load: fromDate = 90 days ago, toDate = today
Historical: Use pagination with lastItemKey
```

### 4.4 Pagination Support

- **lastItemKey**: Conditional field (required if lastPageIndicator = "false")
- **Maximum Length**: 15 characters
- **Purpose**: Retrieve next set of items when results exceed single page
- **Implementation**: Store lastItemKey from response, use in next request

### 4.5 Entry Identification

- **entryId**: Assigned by bank, maximum 15 characters
- **Important**: Field is **NOT unique** and can be repeated within the same date range
- **Implication**: Cannot use entryId alone as primary key
- **Recommendation**: Use combination of entryId + bookingDate + amount as composite key

### 4.6 Amount Precision

- **Format**: Decimal Number
- **Total Digits**: 13
- **Fraction Digits**: 2
- **Example**: 999999999999.99 (max value)
- **Currency**: ISO 4217 three-letter code (e.g., ZAR, USD, EUR)

### 4.7 Transaction Type Indicator

- **Field**: creditDebitIndicator
- **Values**:
  - **CREDIT**: All credit transactions (money in)
  - **DEBIT**: All debit transactions (money out)
- **Use Case**: Filter for customer payments (CREDIT only)

---

## 5. DATABASE SCHEMA UPDATES (BASED ON ACTUAL API)

### 5.1 Enhanced BankTransactions Table

```sql
CREATE TABLE BankTransactions (
    -- Primary Key
    TransactionID INT IDENTITY(1,1) PRIMARY KEY,
    
    -- API Response Fields (Exact Match)
    EntryId NVARCHAR(15) NOT NULL,                    -- From API: entryId
    BookingDate DATE NOT NULL,                         -- From API: bookingDate
    BookingDateTime DATETIME,                          -- Full datetime if provided
    ValueDate DATE NOT NULL,                           -- From API: valueDate
    ValueDateTime DATETIME,                            -- Full datetime if provided
    
    -- Transaction Identification
    EndToEndId NVARCHAR(20) NOT NULL,                 -- From API: endToEndId (unique per transaction)
    Reference NVARCHAR(MAX),                           -- From API: reference
    UnstructuredReference NVARCHAR(30),                -- From API: unstructured (payment reference)
    UnstructuredReference20 NVARCHAR(20),              -- First 20 chars (what's actually validated)
    
    -- Amount Information
    Amount DECIMAL(13,2) NOT NULL,                     -- From API: amount
    Currency NVARCHAR(3) NOT NULL,                     -- From API: currency (ISO 4217)
    CreditDebitIndicator NVARCHAR(6) NOT NULL,         -- From API: CREDIT or DEBIT
    
    -- Balance Information
    AvailableBalance DECIMAL(13,2),                    -- From API: availability.amount
    
    -- Account Information
    AccountNumber NVARCHAR(23) NOT NULL,               -- From path variable
    BranchID INT,                                      -- FK to Branches
    
    -- Matching & Reconciliation
    Status NVARCHAR(20) DEFAULT 'Pending',             -- Pending/Matched/Unmatched/Reconciled
    MatchedInvoiceID INT,                              -- FK to Invoices
    MatchConfidence DECIMAL(5,2),                      -- 0-100%
    MatchType NVARCHAR(20),                            -- Auto/Manual/Fuzzy
    
    -- Audit Fields
    ImportedDate DATETIME DEFAULT GETDATE(),
    ProcessedDate DATETIME,
    LastModifiedDate DATETIME,
    LastModifiedBy INT,
    
    -- Additional Details (JSON storage for full API response)
    TransactionDetailsJSON NVARCHAR(MAX),              -- Store full transactionDetails
    RemittanceInfoJSON NVARCHAR(MAX),                  -- Store full remittanceInfo
    EntryDetailsJSON NVARCHAR(MAX),                    -- Store full entryDetails
    
    -- Indexes
    INDEX IX_BookingDate (BookingDate),
    INDEX IX_EndToEndId (EndToEndId),
    INDEX IX_AccountNumber (AccountNumber),
    INDEX IX_Status (Status),
    INDEX IX_UnstructuredReference (UnstructuredReference20),
    
    -- Composite unique constraint (since entryId is not unique)
    CONSTRAINT UQ_Transaction UNIQUE (EntryId, BookingDate, Amount, AccountNumber)
);
```

### 5.2 API Pagination Tracking Table

```sql
CREATE TABLE BankTransactionSyncLog (
    SyncLogID INT IDENTITY(1,1) PRIMARY KEY,
    AccountNumber NVARCHAR(23) NOT NULL,
    FromDate DATE NOT NULL,
    ToDate DATE NOT NULL,
    LastItemKey NVARCHAR(15),                          -- For pagination
    LastPageIndicator BIT,                             -- TRUE if last page reached
    TransactionsRetrieved INT,
    SyncStartTime DATETIME,
    SyncEndTime DATETIME,
    Status NVARCHAR(20),                               -- InProgress/Completed/Failed
    ErrorMessage NVARCHAR(MAX),
    CreatedDate DATETIME DEFAULT GETDATE()
);
```

---

## 6. MATCHING LOGIC IMPLEMENTATION

### 6.1 Reference Parsing Strategy

Given the 20-character limitation, implement smart parsing:

```sql
-- Extract invoice number from unstructured reference
CREATE FUNCTION dbo.fn_ExtractInvoiceNumber(@reference NVARCHAR(30))
RETURNS NVARCHAR(20)
AS
BEGIN
    DECLARE @invoiceNumber NVARCHAR(20);
    
    -- Take first 20 characters
    SET @reference = LEFT(@reference, 20);
    
    -- Remove common prefixes and extract numbers
    SET @reference = REPLACE(@reference, 'INV-', '');
    SET @reference = REPLACE(@reference, 'INV', '');
    SET @reference = REPLACE(@reference, 'INVOICE', '');
    SET @reference = LTRIM(RTRIM(@reference));
    
    -- Extract numeric portion
    -- Pattern matching logic here
    
    RETURN @invoiceNumber;
END;
```

### 6.2 Automatic Matching Stored Procedure

```sql
CREATE PROCEDURE sp_MatchBankTransactionsToInvoices
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Priority 1: Exact match on invoice number in first 20 chars + amount
    UPDATE bt
    SET 
        bt.MatchedInvoiceID = i.InvoiceID,
        bt.Status = 'Matched',
        bt.MatchType = 'Auto-Exact',
        bt.MatchConfidence = 100.0,
        bt.ProcessedDate = GETDATE()
    FROM BankTransactions bt
    INNER JOIN Invoices i ON 
        i.InvoiceNumber = dbo.fn_ExtractInvoiceNumber(bt.UnstructuredReference20)
        AND ABS(i.TotalAmount - bt.Amount) < 0.01  -- Allow 1 cent rounding
        AND bt.CreditDebitIndicator = 'CREDIT'
        AND i.Status IN ('Open', 'Partial')
    WHERE bt.Status = 'Pending';
    
    -- Priority 2: Amount match + customer + date proximity
    UPDATE bt
    SET 
        bt.MatchedInvoiceID = i.InvoiceID,
        bt.Status = 'Matched',
        bt.MatchType = 'Auto-Fuzzy',
        bt.MatchConfidence = 85.0,
        bt.ProcessedDate = GETDATE()
    FROM BankTransactions bt
    INNER JOIN Invoices i ON 
        ABS(i.TotalAmount - bt.Amount) < 0.01
        AND bt.CreditDebitIndicator = 'CREDIT'
        AND i.Status IN ('Open', 'Partial')
        AND DATEDIFF(DAY, i.InvoiceDate, bt.BookingDate) BETWEEN 0 AND 30
    WHERE bt.Status = 'Pending'
        AND NOT EXISTS (
            SELECT 1 FROM Invoices i2 
            WHERE ABS(i2.TotalAmount - bt.Amount) < 0.01 
            AND i2.InvoiceID <> i.InvoiceID
            AND i2.Status IN ('Open', 'Partial')
        ); -- Only if single match found
    
    -- Mark remaining as unmatched for manual review
    UPDATE BankTransactions
    SET Status = 'Unmatched'
    WHERE Status = 'Pending';
    
END;
```

---

## 7. API INTEGRATION CODE STRUCTURE

### 7.1 API Request Builder

```vb.net
Public Class FNBTransactionHistoryAPI
    Private _baseUrl As String = "https://api.fnb.co.za/transaction-history/v1"
    Private _apiKey As String
    Private _clientId As String
    
    Public Function GetTransactionHistory(
        accountNumber As String,
        fromDate As Date,
        toDate As Date,
        Optional lastItemKey As String = Nothing
    ) As TransactionHistoryResponse
        
        ' Validate inputs
        If accountNumber.Length > 23 Then
            Throw New ArgumentException("Account number cannot exceed 23 characters")
        End If
        
        If accountNumber.Trim() = "" OrElse accountNumber.All(Function(c) c = "0"c) Then
            Throw New ArgumentException("Account number cannot be empty or all zeros")
        End If
        
        ' Build request URL
        Dim url As String = $"{_baseUrl}/accounts/{accountNumber}/transactions"
        
        ' Add query parameters
        Dim queryParams As New List(Of String) From {
            $"fromDate={fromDate:yyyy-MM-dd}",
            $"toDate={toDate:yyyy-MM-dd}"
        }
        
        If Not String.IsNullOrEmpty(lastItemKey) Then
            queryParams.Add($"lastItemKey={lastItemKey}")
        End If
        
        url &= "?" & String.Join("&", queryParams)
        
        ' Make API call
        Using client As New HttpClient()
            client.DefaultRequestHeaders.Add("Authorization", $"Bearer {_apiKey}")
            client.DefaultRequestHeaders.Add("X-Client-Id", _clientId)
            
            Dim response = client.GetAsync(url).Result
            
            If response.IsSuccessStatusCode Then
                Dim json = response.Content.ReadAsStringAsync().Result
                Return JsonConvert.DeserializeObject(Of TransactionHistoryResponse)(json)
            Else
                Throw New Exception($"API Error: {response.StatusCode} - {response.ReasonPhrase}")
            End If
        End Using
    End Function
End Class
```

### 7.2 Response Models

```vb.net
Public Class TransactionHistoryResponse
    Public Property Entries As List(Of TransactionEntry)
    Public Property LastItemKey As String
    Public Property LastPageIndicator As Boolean
End Class

Public Class TransactionEntry
    Public Property EntryId As String              ' Max 15 chars
    Public Property BookingDate As Date
    Public Property ValueDate As Date
    Public Property EndToEndId As String           ' Max 20 chars
    Public Property Amount As Decimal              ' 13 digits, 2 decimals
    Public Property Currency As String             ' 3 chars (ISO 4217)
    Public Property CreditDebitIndicator As String ' CREDIT or DEBIT
    Public Property UnstructuredReference As String ' Max 30 chars
    Public Property Reference As String
    Public Property AvailableBalance As Decimal
    Public Property TransactionDetails As Object
    Public Property RemittanceInfo As Object
    Public Property EntryDetails As Object
End Class
```

---

## 8. CUSTOMER TRAINING REQUIREMENTS

### 8.1 Payment Reference Best Practices

**Train customers to include invoice numbers in payment references:**

**✅ RECOMMENDED FORMATS** (all under 20 characters):
- `INV-001234`
- `001234`
- `2024-001234`
- `INV001234`

**❌ AVOID THESE FORMATS**:
- `Invoice Number 001234` (too long, words wasted)
- `Payment for Invoice 001234 Branch 01` (truncated)
- `001234 - Customer Name` (customer name not needed)

**Communication Template for Customers**:
```
IMPORTANT: Payment Reference Instructions

When making payment, please include your INVOICE NUMBER in the payment reference field.

✅ Correct: INV-001234
❌ Incorrect: Payment for invoice

This ensures your payment is automatically matched to your invoice.
Maximum 20 characters will be processed.
```

---

## 9. ERROR HANDLING & EDGE CASES

### 9.1 Duplicate Transaction Handling

**Issue**: `entryId` is NOT unique within date range

**Solution**:
```sql
-- Use composite key for duplicate detection
IF EXISTS (
    SELECT 1 FROM BankTransactions
    WHERE EntryId = @entryId
        AND BookingDate = @bookingDate
        AND Amount = @amount
        AND AccountNumber = @accountNumber
)
BEGIN
    -- Skip duplicate
    RETURN;
END
```

### 9.2 Reference Truncation Handling

**Issue**: References longer than 20 characters are truncated

**Solution**:
```vb.net
' Store both full and truncated versions
transaction.UnstructuredReference = apiResponse.UnstructuredReference ' Full 30 chars
transaction.UnstructuredReference20 = Left(apiResponse.UnstructuredReference, 20) ' First 20

' Match against truncated version
Dim invoiceNumber = ExtractInvoiceNumber(transaction.UnstructuredReference20)
```

### 9.3 Pagination Loop Protection

**Issue**: Infinite loop if lastPageIndicator not properly checked

**Solution**:
```vb.net
Dim maxPages As Integer = 100 ' Safety limit
Dim pageCount As Integer = 0
Dim lastItemKey As String = Nothing

Do
    Dim response = GetTransactionHistory(accountNumber, fromDate, toDate, lastItemKey)
    
    ' Process transactions
    ProcessTransactions(response.Entries)
    
    ' Check if more pages
    If response.LastPageIndicator Then
        Exit Do ' Last page reached
    End If
    
    lastItemKey = response.LastItemKey
    pageCount += 1
    
    If pageCount >= maxPages Then
        LogError("Pagination limit reached - possible infinite loop")
        Exit Do
    End If
Loop While Not String.IsNullOrEmpty(lastItemKey)
```

---

## 10. TESTING CHECKLIST

### 10.1 API Integration Tests

- [ ] Single account query with date range
- [ ] Pagination with multiple pages
- [ ] Empty result set handling
- [ ] Invalid account number (>23 chars)
- [ ] Invalid date format
- [ ] Missing required parameters
- [ ] Authentication failure
- [ ] Network timeout handling
- [ ] Rate limit exceeded

### 10.2 Data Parsing Tests

- [ ] Parse all required fields correctly
- [ ] Handle optional fields (nulls)
- [ ] Decimal precision (13.2) validation
- [ ] Currency code validation (ISO 4217)
- [ ] Date format parsing (YYYY-MM-DD)
- [ ] Reference truncation (20 chars)
- [ ] JSON storage of complex objects

### 10.3 Matching Logic Tests

- [ ] Exact invoice number match
- [ ] Fuzzy amount match (±R1)
- [ ] Multiple invoices same amount
- [ ] Partial payment handling
- [ ] Overpayment handling
- [ ] Reference with special characters
- [ ] Reference with only numbers
- [ ] No matching invoice found

### 10.4 Edge Case Tests

- [ ] Duplicate entryId handling
- [ ] Same-day multiple transactions
- [ ] Zero amount transactions
- [ ] Foreign currency transactions
- [ ] Very large amounts (13 digits)
- [ ] Transactions at midnight
- [ ] Weekend/holiday transactions

---

## 11. PERFORMANCE OPTIMIZATION

### 11.1 Indexing Strategy

```sql
-- Critical indexes for matching performance
CREATE INDEX IX_Invoices_Number_Amount ON Invoices(InvoiceNumber, TotalAmount) 
    INCLUDE (Status, InvoiceDate);

CREATE INDEX IX_BankTransactions_Reference ON BankTransactions(UnstructuredReference20) 
    INCLUDE (Amount, CreditDebitIndicator, Status);

CREATE INDEX IX_BankTransactions_Amount_Status ON BankTransactions(Amount, Status) 
    INCLUDE (BookingDate, CreditDebitIndicator);
```

### 11.2 Batch Processing

```vb.net
' Process transactions in batches of 100
Const BATCH_SIZE As Integer = 100

For i As Integer = 0 To transactions.Count - 1 Step BATCH_SIZE
    Dim batch = transactions.Skip(i).Take(BATCH_SIZE).ToList()
    
    Using scope As New TransactionScope()
        For Each transaction In batch
            SaveTransaction(transaction)
        Next
        scope.Complete()
    End Using
Next
```

---

## 12. SECURITY CONSIDERATIONS

### 12.1 API Credential Storage

```vb.net
' NEVER store credentials in plain text
' Use encrypted configuration

Public Class SecureConfig
    Public Shared Function GetAPIKey() As String
        ' Retrieve from encrypted config or Azure Key Vault
        Dim encryptedKey = ConfigurationManager.AppSettings("FNB_API_Key_Encrypted")
        Return DecryptString(encryptedKey)
    End Function
End Class
```

### 12.2 Sensitive Data Handling

```sql
-- Mask account numbers in logs
CREATE FUNCTION dbo.fn_MaskAccountNumber(@accountNumber NVARCHAR(23))
RETURNS NVARCHAR(23)
AS
BEGIN
    RETURN LEFT(@accountNumber, 4) + REPLICATE('*', LEN(@accountNumber) - 8) + RIGHT(@accountNumber, 4)
END;

-- Example: 62123456789 becomes 6212*****789
```

---

## DOCUMENT VERSION

- **Version**: 1.0 - Technical Specifications
- **Date**: January 22, 2026
- **Based On**: FNB API Transaction History Message Specification V-03
- **Status**: Technical Reference Document

---

**END OF TECHNICAL SPECIFICATIONS**
