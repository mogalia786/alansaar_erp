# FNB Payment Execution API - Integration Guide
## Bulk EFT Payment Processing for Oven Delights ERP

---

## 1. OVERVIEW

### What is Payment Execution API?

The FNB Payment Execution API allows businesses to **programmatically initiate EFT payments** to suppliers, vendors, and creditors directly from the ERP system. This eliminates manual banking and enables automated bulk payment processing.

### Key Capabilities

1. **EFT Payment Initiation** - Submit single or batch payment instructions
2. **Payment Status Tracking** - Retrieve real-time payment status
3. **Unpaid Payments Report** - View failed/rejected payments for reprocessing

### Use Cases for Oven Delights

- **Supplier Payments**: Pay ingredient suppliers, packaging vendors
- **Utility Payments**: Electricity, water, rent
- **Staff Payments**: Salaries, bonuses, reimbursements
- **Creditor Payments**: Pay outstanding purchase invoices
- **Bulk Processing**: Process multiple payments in single API call

---

## 2. API ENDPOINTS

### Base URLs

| Environment | URL |
|-------------|-----|
| **Integration** (Testing) | `https://api.i.fnb.co.za/apigateway` |
| **Pre-Production** | `https://api.p.fnb.co.za/apigateway` |
| **Production** | `https://api.fnb.co.za/apigateway` |

### Available Endpoints

#### 1. Initiate Payment
```
POST /paymentExecution/initiate/v1
```
**Purpose**: Submit payment instruction(s) for processing

**Request**: Payment details (debtor, creditor, amount, reference)
**Response**: `instructionId` for tracking

#### 2. Retrieve Payment Report
```
GET /paymentExecution/retrieveReport/v1/{instructionId}
```
**Purpose**: Check status of submitted payment

**Response**: Payment status (ACCEPTED, REJECTED, PENDING, etc.)

#### 3. Retrieve Unpaid Payments
```
POST /paymentExecution/retrieveFilteredUnpaids/v1
```
**Purpose**: Get list of failed/rejected payments for reprocessing

**Request**: Date range, account filters, pagination
**Response**: List of unpaid transactions with rejection reasons

---

## 3. AUTHENTICATION

### OAuth 2.0 Client Credentials Flow

**Token Endpoint**: `https://api.p.fnb.co.za/apigateway/oauth2/token/v2`

**Flow**:
1. Request access token using client credentials
2. Receive bearer token
3. Include token in Authorization header for all API calls
4. Token expires after set period - refresh as needed

**Required Credentials** (from FNB):
- Client ID
- Client Secret
- Scope: `i_can` (provides permissions based on partner setup)

**Example Token Request**:
```http
POST /apigateway/oauth2/token/v2
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=YOUR_CLIENT_ID
&client_secret=YOUR_CLIENT_SECRET
&scope=i_can
```

**Example Token Response**:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "i_can"
}
```

**Using Token in API Calls**:
```http
POST /paymentExecution/initiate/v1
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
```

---

## 4. PAYMENT INITIATION STRUCTURE

### Request Schema

```json
{
  "groupHeader": {
    "messageId": "UNIQUE_MESSAGE_ID",
    "creationDateTime": "2024-01-23T10:30:00",
    "initiatingPartyName": "OVEN DELIGHTS",
    "initiatingPartyBIC": "FIRNZAJJ",
    "totalNumberOfTransactions": 2,
    "totalControlSum": 15000.00
  },
  "paymentInformation": [
    {
      "paymentInformationId": "BATCH_001",
      "paymentInformationMethod": "TRF",
      "batchBooking": true,
      "numberOfTransactions": 2,
      "controlSum": 15000.00,
      "paymentTypeInformationServiceLevelCode": "SDVA",
      "requestedExecutionDate": "2024-01-24",
      "debtor": {
        "name": "Oven Delights Pty Ltd",
        "bicOrBEI": "FIRNZAJJ"
      },
      "debtorAccount": {
        "accountNumber": "62844045455",
        "accountType": "CACC"
      },
      "debtorAgent": {
        "branchId": "250655"
      },
      "creditTransferTransactionInformation": [
        {
          "endToEndId": "INV-2024-001234",
          "amount": {
            "currency": "ZAR",
            "value": 10000.00
          },
          "creditor": {
            "name": "Supplier ABC Pty Ltd",
            "bicOrBEI": "ABSAZAJJ"
          },
          "creditorAccount": {
            "accountNumber": "123456789",
            "accountType": "CACC"
          },
          "creditorAgent": {
            "branchId": "250655"
          },
          "remittanceInformationUnstructured": "Inv 1347893",
          "remittanceLocationMethod": "EMAL",
          "remittanceLocationElectronicAddress": "supplier@example.com"
        }
      ]
    }
  ]
}
```

### Key Fields Explained

#### Group Header (Batch Level)
- **messageId**: Unique identifier for this payment batch (your reference)
- **creationDateTime**: ISO DateTime when batch created
- **initiatingPartyName**: Your company name
- **initiatingPartyBIC**: FNB SWIFT code (FIRNZAJJ for FNB South Africa)
- **totalNumberOfTransactions**: Total count of all payments in batch
- **totalControlSum**: Total amount of all payments (validation)

#### Payment Information (Batch Details)
- **paymentInformationId**: Unique ID for this payment group
- **paymentInformationMethod**: Always "TRF" (Transfer)
- **batchBooking**: true = single debit entry, false = individual debits
- **paymentTypeInformationServiceLevelCode**: Service level (see codes below)
- **requestedExecutionDate**: When payment should be processed (YYYY-MM-DD)

#### Debtor (Your Account - Money Going Out)
- **name**: Your company name
- **bicOrBEI**: Bank identifier code
- **accountNumber**: Your FNB account number (max 23 chars)
- **accountType**: "CACC" (Current/Cheque), "SVGS" (Savings)
- **branchId**: Your FNB branch code

#### Creditor (Supplier Account - Money Going In)
- **name**: Supplier/vendor name
- **bicOrBEI**: Supplier's bank identifier
- **accountNumber**: Supplier's account number
- **accountType**: Account type
- **branchId**: Supplier's bank branch code

#### Transaction Details
- **endToEndId**: Unique transaction reference (your invoice/payment number)
- **amount.currency**: "ZAR" (South African Rand)
- **amount.value**: Payment amount (max 2 decimals)
- **remittanceInformationUnstructured**: Reference on supplier's statement (**max 20 chars for LOAN/TRNS/SBSH/GRCP accounts**)
- **remittanceLocationMethod**: "EMAL" if sending proof of payment via email
- **remittanceLocationElectronicAddress**: Supplier's email for proof of payment

---

## 5. SERVICE LEVEL CODES

| Code | Description | Processing Time |
|------|-------------|-----------------|
| **SDVA** | Same Day Value | Same business day |
| **NURG** | Normal Urgent | Next business day |
| **URGP** | Urgent Payment | Immediate (higher fee) |

**Recommendation**: Use **SDVA** for standard supplier payments (same day processing at lower cost)

---

## 6. PAYMENT STATUS CODES

### Group/Batch Status
- **ACCP** - Accepted (payment batch accepted for processing)
- **RJCT** - Rejected (entire batch rejected)
- **PDNG** - Pending (awaiting processing)
- **ACSC** - Accepted Settlement Completed (all payments processed)

### Individual Transaction Status
- **ACCC** - Accepted Settlement Completed (payment successful)
- **RJCT** - Rejected (payment failed)
- **PDNG** - Pending (awaiting processing)
- **ACSP** - Accepted Settlement In Process

---

## 7. REJECTION REASON CODES

Common rejection reasons from API:

| Code | Description | Solution |
|------|-------------|----------|
| **UN20** | Missing mandatory reference | Include remittanceInformationUnstructured |
| **AC01** | Incorrect account number | Verify creditor account number |
| **AC04** | Closed account | Update supplier account details |
| **AC06** | Blocked account | Contact supplier |
| **AM04** | Insufficient funds | Ensure debtor account has sufficient balance |
| **BE05** | Unrecognized initiating party | Verify BIC codes |
| **DT01** | Invalid date | Check requestedExecutionDate format |
| **FF01** | Invalid file format | Verify JSON structure |
| **RR01** | Missing debtor account | Include debtorAccount details |
| **RR02** | Missing debtor name | Include debtor.name |
| **RR03** | Missing creditor account | Include creditorAccount details |
| **RR04** | Missing creditor name | Include creditor.name |

---

## 8. DATABASE SCHEMA FOR ERP INTEGRATION

### 8.1 Payment Batches Table

```sql
CREATE TABLE PaymentBatches (
    BatchID INT IDENTITY(1,1) PRIMARY KEY,
    MessageID NVARCHAR(50) UNIQUE NOT NULL,           -- groupHeader.messageId
    InstructionID NVARCHAR(200),                      -- From API response
    
    -- Batch Details
    CreationDateTime DATETIME NOT NULL,
    InitiatingPartyName NVARCHAR(100),
    TotalNumberOfTransactions INT,
    TotalControlSum DECIMAL(18,2),
    
    -- Processing Details
    RequestedExecutionDate DATE,
    ServiceLevelCode NVARCHAR(10),                    -- SDVA, NURG, URGP
    
    -- Status
    BatchStatus NVARCHAR(20),                         -- ACCP, RJCT, PDNG, ACSC
    StatusCheckedDate DATETIME,
    
    -- Debtor (Our Account)
    DebtorAccountNumber NVARCHAR(23),
    DebtorAccountType NVARCHAR(10),
    DebtorBranchID NVARCHAR(10),
    
    -- Audit
    CreatedBy INT,                                    -- FK to Users
    CreatedDate DATETIME DEFAULT GETDATE(),
    SubmittedDate DATETIME,
    CompletedDate DATETIME,
    
    -- Error Handling
    RejectionReason NVARCHAR(MAX),
    ErrorDetails NVARCHAR(MAX),
    
    INDEX IX_MessageID (MessageID),
    INDEX IX_InstructionID (InstructionID),
    INDEX IX_BatchStatus (BatchStatus),
    INDEX IX_RequestedExecutionDate (RequestedExecutionDate)
);
```

### 8.2 Payment Transactions Table

```sql
CREATE TABLE PaymentTransactions (
    PaymentTransactionID INT IDENTITY(1,1) PRIMARY KEY,
    BatchID INT NOT NULL,                             -- FK to PaymentBatches
    
    -- Transaction Identification
    EndToEndID NVARCHAR(50) NOT NULL,                 -- Our reference (invoice number)
    
    -- Amount
    Currency NVARCHAR(3) DEFAULT 'ZAR',
    Amount DECIMAL(18,2) NOT NULL,
    
    -- Creditor (Supplier)
    CreditorName NVARCHAR(100) NOT NULL,
    CreditorAccountNumber NVARCHAR(23) NOT NULL,
    CreditorAccountType NVARCHAR(10),
    CreditorBranchID NVARCHAR(10),
    CreditorBIC NVARCHAR(20),
    
    -- Remittance
    RemittanceReference NVARCHAR(30),                 -- Reference on supplier statement
    RemittanceReference20 NVARCHAR(20),               -- First 20 chars (what's processed)
    ProofOfPaymentEmail NVARCHAR(100),
    
    -- Status
    TransactionStatus NVARCHAR(20),                   -- ACCC, RJCT, PDNG, ACSP
    StatusCheckedDate DATETIME,
    
    -- Linking
    SupplierID INT,                                   -- FK to Suppliers
    PurchaseInvoiceID INT,                            -- FK to PurchaseInvoices
    
    -- Error Handling
    RejectionReasonCode NVARCHAR(10),
    RejectionReasonText NVARCHAR(500),
    
    -- Audit
    CreatedDate DATETIME DEFAULT GETDATE(),
    ProcessedDate DATETIME,
    
    FOREIGN KEY (BatchID) REFERENCES PaymentBatches(BatchID),
    INDEX IX_EndToEndID (EndToEndID),
    INDEX IX_TransactionStatus (TransactionStatus),
    INDEX IX_SupplierID (SupplierID),
    INDEX IX_PurchaseInvoiceID (PurchaseInvoiceID)
);
```

### 8.3 Supplier Bank Details Table (Enhancement)

```sql
-- Add bank details to existing Suppliers table or create separate table
ALTER TABLE Suppliers
ADD BankAccountNumber NVARCHAR(23),
    BankAccountType NVARCHAR(10) DEFAULT 'CACC',
    BankBranchCode NVARCHAR(10),
    BankName NVARCHAR(50),
    BankBIC NVARCHAR(20),
    ProofOfPaymentEmail NVARCHAR(100),
    IsActive BIT DEFAULT 1;
```

### 8.4 Payment Status Log Table

```sql
CREATE TABLE PaymentStatusLog (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    BatchID INT,
    PaymentTransactionID INT,
    
    StatusCheckDateTime DATETIME DEFAULT GETDATE(),
    PreviousStatus NVARCHAR(20),
    NewStatus NVARCHAR(20),
    StatusDetails NVARCHAR(MAX),
    
    CheckedBy INT,                                    -- FK to Users (or NULL for automated)
    
    INDEX IX_BatchID (BatchID),
    INDEX IX_PaymentTransactionID (PaymentTransactionID)
);
```

---

## 9. INTEGRATION WORKFLOW

### 9.1 Payment Initiation Flow

```
1. User selects purchase invoices to pay
   ↓
2. ERP validates:
   - Supplier has bank details
   - Invoice not already paid
   - Sufficient account balance
   ↓
3. ERP creates payment batch:
   - Generate unique messageId
   - Group by execution date
   - Calculate control sums
   ↓
4. ERP calls FNB API:
   POST /paymentExecution/initiate/v1
   ↓
5. API validates and returns:
   - instructionId (for tracking)
   - HTTP 200 (Accepted)
   ↓
6. ERP stores:
   - Save batch to PaymentBatches
   - Save transactions to PaymentTransactions
   - Update invoice status to "Payment Submitted"
   ↓
7. Schedule status check:
   - Check status after 5 minutes
   - Retry every 15 minutes until final status
```

### 9.2 Status Checking Flow

```
1. Scheduled job runs (every 15 minutes)
   ↓
2. Get all batches with status ACCP or PDNG
   ↓
3. For each batch:
   GET /paymentExecution/retrieveReport/v1/{instructionId}
   ↓
4. Parse response:
   - Update batch status
   - Update individual transaction statuses
   - Log status changes
   ↓
5. For successful payments (ACCC):
   - Update invoice status to "Paid"
   - Create payment record
   - Send confirmation email
   ↓
6. For rejected payments (RJCT):
   - Flag for review
   - Notify finance team
   - Log rejection reason
```

### 9.3 Unpaid Payments Handling

```
1. Daily job runs (morning)
   ↓
2. Call API:
   POST /paymentExecution/retrieveFilteredUnpaids/v1
   Request: Last 7 days, all accounts
   ↓
3. Parse response:
   - Identify unpaid transactions
   - Match to PaymentTransactions by endToEndId
   ↓
4. Update records:
   - Set status to "Unpaid"
   - Store rejection reason
   - Flag for reprocessing
   ↓
5. Notify finance team:
   - Email with unpaid list
   - Rejection reasons
   - Action required
```

---

## 10. VB.NET IMPLEMENTATION

### 10.1 API Client Class

```vb.net
Public Class FNBPaymentExecutionAPI
    Private _baseUrl As String
    Private _clientId As String
    Private _clientSecret As String
    Private _accessToken As String
    Private _tokenExpiry As DateTime
    
    Public Sub New(environment As String)
        Select Case environment.ToLower()
            Case "integration"
                _baseUrl = "https://api.i.fnb.co.za/apigateway"
            Case "preprod"
                _baseUrl = "https://api.p.fnb.co.za/apigateway"
            Case "production"
                _baseUrl = "https://api.fnb.co.za/apigateway"
            Case Else
                Throw New ArgumentException("Invalid environment")
        End Select
        
        ' Load from encrypted config
        _clientId = ConfigurationManager.AppSettings("FNB_ClientID")
        _clientSecret = ConfigurationManager.AppSettings("FNB_ClientSecret")
    End Sub
    
    Private Function GetAccessToken() As String
        ' Check if token is still valid
        If Not String.IsNullOrEmpty(_accessToken) AndAlso DateTime.Now < _tokenExpiry Then
            Return _accessToken
        End If
        
        ' Request new token
        Using client As New HttpClient()
            Dim tokenUrl = $"{_baseUrl}/oauth2/token/v2"
            
            Dim content As New FormUrlEncodedContent(New Dictionary(Of String, String) From {
                {"grant_type", "client_credentials"},
                {"client_id", _clientId},
                {"client_secret", _clientSecret},
                {"scope", "i_can"}
            })
            
            Dim response = client.PostAsync(tokenUrl, content).Result
            
            If response.IsSuccessStatusCode Then
                Dim json = response.Content.ReadAsStringAsync().Result
                Dim tokenResponse = JsonConvert.DeserializeObject(Of TokenResponse)(json)
                
                _accessToken = tokenResponse.AccessToken
                _tokenExpiry = DateTime.Now.AddSeconds(tokenResponse.ExpiresIn - 60) ' 60s buffer
                
                Return _accessToken
            Else
                Throw New Exception($"Token request failed: {response.StatusCode}")
            End If
        End Using
    End Function
    
    Public Function InitiatePayment(paymentRequest As PaymentInitiationRequest) As PaymentInitiationResponse
        Dim token = GetAccessToken()
        
        Using client As New HttpClient()
            client.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}")
            
            Dim json = JsonConvert.SerializeObject(paymentRequest)
            Dim content As New StringContent(json, Encoding.UTF8, "application/json")
            
            Dim response = client.PostAsync($"{_baseUrl}/paymentExecution/initiate/v1", content).Result
            
            If response.IsSuccessStatusCode Then
                Dim responseJson = response.Content.ReadAsStringAsync().Result
                Return JsonConvert.DeserializeObject(Of PaymentInitiationResponse)(responseJson)
            Else
                Dim errorJson = response.Content.ReadAsStringAsync().Result
                Dim errorResponse = JsonConvert.DeserializeObject(Of ErrorMessage)(errorJson)
                Throw New Exception($"Payment initiation failed: {errorResponse.Text}")
            End If
        End Using
    End Function
    
    Public Function GetPaymentStatus(instructionId As String) As PaymentStatusReport
        Dim token = GetAccessToken()
        
        Using client As New HttpClient()
            client.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}")
            
            Dim response = client.GetAsync($"{_baseUrl}/paymentExecution/retrieveReport/v1/{instructionId}").Result
            
            If response.IsSuccessStatusCode Then
                Dim json = response.Content.ReadAsStringAsync().Result
                Return JsonConvert.DeserializeObject(Of PaymentStatusReport)(json)
            Else
                Throw New Exception($"Status retrieval failed: {response.StatusCode}")
            End If
        End Using
    End Function
    
    Public Function GetUnpaidPayments(filter As UnpaidsFilter) As UnpaidsPaymentStatusReportList
        Dim token = GetAccessToken()
        
        Using client As New HttpClient()
            client.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}")
            
            Dim json = JsonConvert.SerializeObject(filter)
            Dim content As New StringContent(json, Encoding.UTF8, "application/json")
            
            Dim response = client.PostAsync($"{_baseUrl}/paymentExecution/retrieveFilteredUnpaids/v1", content).Result
            
            If response.IsSuccessStatusCode Then
                Dim responseJson = response.Content.ReadAsStringAsync().Result
                Return JsonConvert.DeserializeObject(Of UnpaidsPaymentStatusReportList)(responseJson)
            Else
                Throw New Exception($"Unpaids retrieval failed: {response.StatusCode}")
            End If
        End Using
    End Function
End Class
```

### 10.2 Payment Service Class

```vb.net
Public Class PaymentExecutionService
    Private _connectionString As String
    Private _fnbApi As FNBPaymentExecutionAPI
    
    Public Sub New(connectionString As String)
        _connectionString = connectionString
        _fnbApi = New FNBPaymentExecutionAPI("production")
    End Sub
    
    Public Function CreatePaymentBatch(invoiceIds As List(Of Integer), executionDate As Date) As Tuple(Of Boolean, String, Integer?)
        Try
            ' 1. Retrieve invoice and supplier details
            Dim invoices = GetInvoicesForPayment(invoiceIds)
            
            If invoices.Count = 0 Then
                Return New Tuple(Of Boolean, String, Integer?)(False, "No valid invoices found", Nothing)
            End If
            
            ' 2. Validate supplier bank details
            For Each inv In invoices
                If String.IsNullOrEmpty(inv.SupplierBankAccount) Then
                    Return New Tuple(Of Boolean, String, Integer?)(False, $"Supplier {inv.SupplierName} has no bank details", Nothing)
                End If
            Next
            
            ' 3. Create batch record
            Dim messageId = $"OD-{DateTime.Now:yyyyMMddHHmmss}-{Guid.NewGuid().ToString().Substring(0, 8)}"
            Dim batchId = SavePaymentBatch(messageId, invoices, executionDate)
            
            ' 4. Build API request
            Dim request = BuildPaymentRequest(messageId, invoices, executionDate)
            
            ' 5. Submit to FNB
            Dim response = _fnbApi.InitiatePayment(request)
            
            ' 6. Update batch with instructionId
            UpdateBatchInstructionId(batchId, response.InstructionId)
            
            Return New Tuple(Of Boolean, String, Integer?)(True, "Payment batch submitted successfully", batchId)
            
        Catch ex As Exception
            Return New Tuple(Of Boolean, String, Integer?)(False, ex.Message, Nothing)
        End Try
    End Function
    
    Private Function BuildPaymentRequest(messageId As String, invoices As List(Of InvoicePaymentInfo), executionDate As Date) As PaymentInitiationRequest
        Dim request As New PaymentInitiationRequest()
        
        ' Group Header
        request.GroupHeader = New GroupHeader() With {
            .MessageId = messageId,
            .CreationDateTime = DateTime.Now,
            .InitiatingPartyName = "OVEN DELIGHTS PTY LTD",
            .InitiatingPartyBIC = "FIRNZAJJ",
            .TotalNumberOfTransactions = invoices.Count,
            .TotalControlSum = invoices.Sum(Function(i) i.Amount)
        }
        
        ' Payment Information (single batch)
        Dim paymentInfo As New PaymentInformation() With {
            .PaymentInformationId = messageId,
            .PaymentInformationMethod = "TRF",
            .BatchBooking = True,
            .NumberOfTransactions = invoices.Count,
            .ControlSum = invoices.Sum(Function(i) i.Amount),
            .PaymentTypeInformationServiceLevelCode = "SDVA",
            .RequestedExecutionDate = executionDate,
            .Debtor = New Debtor() With {
                .Name = "Oven Delights Pty Ltd",
                .BicOrBEI = "FIRNZAJJ"
            },
            .DebtorAccount = New DebtorAccount() With {
                .AccountNumber = ConfigurationManager.AppSettings("FNB_DebtorAccountNumber"),
                .AccountType = "CACC"
            },
            .DebtorAgent = New DebtorAgent() With {
                .BranchId = ConfigurationManager.AppSettings("FNB_DebtorBranchId")
            }
        }
        
        ' Credit Transfer Transactions
        paymentInfo.CreditTransferTransactionInformation = New List(Of CreditTransferTransaction)()
        
        For Each inv In invoices
            Dim transaction As New CreditTransferTransaction() With {
                .EndToEndId = inv.InvoiceNumber,
                .Amount = New Amount() With {
                    .Currency = "ZAR",
                    .Value = inv.Amount
                },
                .Creditor = New Creditor() With {
                    .Name = inv.SupplierName,
                    .BicOrBEI = If(String.IsNullOrEmpty(inv.SupplierBIC), "FIRNZAJJ", inv.SupplierBIC)
                },
                .CreditorAccount = New CreditorAccount() With {
                    .AccountNumber = inv.SupplierBankAccount,
                    .AccountType = If(String.IsNullOrEmpty(inv.SupplierAccountType), "CACC", inv.SupplierAccountType)
                },
                .CreditorAgent = New CreditorAgent() With {
                    .BranchId = inv.SupplierBranchCode
                },
                .RemittanceInformationUnstructured = Left(inv.InvoiceNumber, 20)
            }
            
            ' Add email if provided
            If Not String.IsNullOrEmpty(inv.SupplierEmail) Then
                transaction.RemittanceLocationMethod = "EMAL"
                transaction.RemittanceLocationElectronicAddress = inv.SupplierEmail
            End If
            
            paymentInfo.CreditTransferTransactionInformation.Add(transaction)
        Next
        
        request.PaymentInformation = New List(Of PaymentInformation) From {paymentInfo}
        
        Return request
    End Function
    
    Public Sub CheckPaymentStatuses()
        ' Get all pending batches
        Dim pendingBatches = GetPendingBatches()
        
        For Each batch In pendingBatches
            Try
                Dim status = _fnbApi.GetPaymentStatus(batch.InstructionId)
                UpdateBatchStatus(batch.BatchId, status)
            Catch ex As Exception
                LogError($"Failed to check status for batch {batch.BatchId}: {ex.Message}")
            End Try
        Next
    End Sub
End Class
```

---

## 11. CRITICAL IMPLEMENTATION NOTES

### 11.1 Reference Field Limitation (CRITICAL!)

**Same as Transaction History API**: 
- `remittanceInformationUnstructured` max 30 characters
- **Only first 20 characters processed** for LOAN/TRNS/SBSH/GRCP accounts
- Use invoice numbers that fit in 20 characters

**Example**:
```vb.net
' Good: "INV-2024-001234" (16 chars)
transaction.RemittanceInformationUnstructured = invoiceNumber

' Better: Truncate to 20 chars
transaction.RemittanceInformationUnstructured = Left(invoiceNumber, 20)
```

### 11.2 Control Sum Validation

API validates that:
- `groupHeader.totalControlSum` = sum of all transaction amounts
- `paymentInformation.controlSum` = sum of transactions in that batch
- Mismatch = rejection

**Always calculate programmatically**:
```vb.net
request.GroupHeader.TotalControlSum = invoices.Sum(Function(i) i.Amount)
```

### 11.3 Unique Message IDs

Each payment batch needs unique `messageId`:
```vb.net
Dim messageId = $"OD-{DateTime.Now:yyyyMMddHHmmss}-{Guid.NewGuid().ToString().Substring(0, 8)}"
' Example: OD-20240123103045-a1b2c3d4
```

### 11.4 Date Formats

- **requestedExecutionDate**: YYYY-MM-DD (ISO Date)
- **creationDateTime**: YYYY-MM-DDThh:mm:ss (ISO DateTime)

### 11.5 Account Type Codes

- **CACC**: Current Account / Cheque Account
- **SVGS**: Savings Account

### 11.6 Error Handling

Always handle:
- Token expiry (refresh before API call)
- Network timeouts
- API rate limits
- Validation errors (400)
- Authorization errors (403)
- Server errors (500)

---

## 12. TESTING STRATEGY

### 12.1 Integration Environment Testing

1. **Single Payment Test**
   - Create one invoice payment
   - Submit to integration API
   - Verify instructionId returned
   - Check status after 5 minutes

2. **Batch Payment Test**
   - Create 5-10 invoice payments
   - Submit as single batch
   - Verify all transactions tracked

3. **Validation Tests**
   - Invalid account number → expect rejection
   - Missing reference → expect rejection
   - Incorrect control sum → expect rejection

4. **Status Checking Test**
   - Submit payment
   - Poll status every minute
   - Verify status transitions (PDNG → ACCP → ACSC)

5. **Unpaid Payments Test**
   - Submit payment with invalid account
   - Wait for rejection
   - Retrieve unpaids list
   - Verify rejection reason

### 12.2 Pre-Production Testing

- Test with real bank accounts (small amounts)
- Verify funds actually transferred
- Test proof of payment emails
- Validate statement references

---

## 13. SECURITY CONSIDERATIONS

### 13.1 Credential Storage

```vb.net
' NEVER store in plain text
' Use encrypted configuration or Azure Key Vault

<appSettings>
  <add key="FNB_ClientID_Encrypted" value="ENCRYPTED_VALUE"/>
  <add key="FNB_ClientSecret_Encrypted" value="ENCRYPTED_VALUE"/>
  <add key="FNB_DebtorAccountNumber_Encrypted" value="ENCRYPTED_VALUE"/>
</appSettings>
```

### 13.2 Access Control

- Restrict payment initiation to authorized users only
- Implement approval workflow for large amounts
- Log all payment submissions with user details
- Require dual authorization for payments > threshold

### 13.3 Audit Trail

Log every API call:
- Request timestamp
- User who initiated
- Request payload (sanitized - no sensitive data)
- Response status
- instructionId

---

## 14. QUESTIONS FOR FNB

### API Access
1. How to apply for Payment Execution API access?
2. What is the approval timeline?
3. Are there setup fees or monthly costs?
4. Transaction fees per payment?

### Credentials
5. How are client credentials issued?
6. Credential rotation policy?
7. Separate credentials for integration/production?

### Limits & Quotas
8. Maximum transactions per batch?
9. Maximum batch size (total amount)?
10. API rate limits (requests per minute)?
11. Daily payment limits?

### Processing
12. Cut-off times for same-day payments (SDVA)?
13. Processing time for NURG vs URGP?
14. Weekend/holiday processing?

### Testing
15. Sandbox environment available?
16. Test accounts provided?
17. Can we test without actual fund transfers?

### Support
18. Technical support contact?
19. Support hours and SLA?
20. How are API changes communicated?

---

## 15. IMPLEMENTATION ROADMAP

### Phase 1: Database & Backend (Week 1-2)
- [ ] Create PaymentBatches table
- [ ] Create PaymentTransactions table
- [ ] Add bank details to Suppliers table
- [ ] Create PaymentStatusLog table
- [ ] Build API client class
- [ ] Build payment service class

### Phase 2: UI & Workflow (Week 3-4)
- [ ] Create "Pay Invoices" screen
- [ ] Invoice selection grid
- [ ] Supplier bank details validation
- [ ] Payment batch preview
- [ ] Submit payment button
- [ ] Payment status tracking screen

### Phase 3: Status Monitoring (Week 5)
- [ ] Build status checking service
- [ ] Schedule automated status checks
- [ ] Update invoice payment status
- [ ] Email notifications (success/failure)

### Phase 4: Unpaid Payments (Week 6)
- [ ] Build unpaids retrieval service
- [ ] Unpaid payments report
- [ ] Reprocessing workflow
- [ ] Finance team notifications

### Phase 5: Testing (Week 7-8)
- [ ] Integration environment testing
- [ ] Pre-production testing with real accounts
- [ ] User acceptance testing
- [ ] Security audit

### Phase 6: Go-Live (Week 9)
- [ ] Switch to production API
- [ ] Process first live payments
- [ ] Monitor closely
- [ ] Gather user feedback

---

## 16. BENEFITS FOR OVEN DELIGHTS

### Operational Efficiency
- **Time Savings**: Eliminate manual banking (hours → minutes)
- **Reduced Errors**: No manual data entry mistakes
- **Bulk Processing**: Pay 50+ suppliers in one batch
- **Automated Tracking**: Real-time payment status

### Financial Control
- **Approval Workflow**: Multi-level authorization
- **Audit Trail**: Complete payment history
- **Cash Flow Management**: Schedule payments optimally
- **Cost Savings**: Reduce banking fees vs manual EFTs

### Supplier Relations
- **Faster Payments**: Same-day processing
- **Proof of Payment**: Automatic email to suppliers
- **Accurate References**: Invoice numbers on statements
- **Reliability**: Consistent payment processing

---

## DOCUMENT VERSION

- **Version**: 1.0
- **Date**: January 23, 2026
- **Based On**: FNB Payment Execution API v1.0 (OpenAPI Spec)
- **Status**: Implementation Guide

---

**END OF DOCUMENT**
