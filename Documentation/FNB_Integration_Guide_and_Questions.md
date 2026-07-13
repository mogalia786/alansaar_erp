# FNB Transaction History API Integration Guide
## Oven Delights ERP System

---

## 1. OVERVIEW

### What is FNB Transaction History API?
The FNB Transaction History API allows businesses to programmatically retrieve banking transaction data directly from their FNB business accounts. This enables automated reconciliation of payments, real-time transaction monitoring, and seamless integration between banking operations and ERP systems.

### Key Benefits for Oven Delights:
- **Automated Payment Reconciliation**: Automatically match customer payments to invoices
- **Real-time Transaction Monitoring**: Receive transaction data as it happens
- **Reduced Manual Data Entry**: Eliminate manual bank statement processing
- **Improved Cash Flow Visibility**: Real-time view of incoming and outgoing payments
- **Audit Trail**: Complete digital record of all banking transactions
- **Multi-branch Support**: Consolidate transactions across multiple branches

---

## 2. HOW THE INTEGRATION WORKS

### Architecture Overview
```
FNB Banking System
        ↓
FNB Transaction History API (REST/SOAP)
        ↓
Oven Delights ERP Middleware/Integration Layer
        ↓
ERP Database (Transaction Matching Engine)
        ↓
Invoice/Payment Reconciliation Module
```

### Typical Integration Flow

#### A. Transaction Retrieval
1. **Scheduled Polling**: ERP system calls FNB API at regular intervals (e.g., every 15 minutes, hourly, daily)
2. **Request Parameters**: Specify date range, account number, transaction types
3. **API Response**: Returns transaction data in structured format (XML/JSON)
4. **Data Parsing**: Extract relevant fields (amount, reference, date, payer details)

#### B. Transaction Processing
1. **Store Raw Data**: Save all transaction data to staging table
2. **Validation**: Check for duplicates, validate amounts and dates
3. **Reference Extraction**: Parse payment references for invoice numbers
4. **Matching Logic**: Apply rules to match transactions to invoices

#### C. Reconciliation
1. **Automatic Matching**: Match transactions to open invoices based on:
   - Exact amount match
   - Invoice number in reference field
   - Customer account number
   - Date proximity
2. **Manual Review Queue**: Flag unmatched transactions for manual review
3. **Payment Application**: Update invoice status, create payment records
4. **Notification**: Alert accounting team of matched/unmatched payments

---

## 3. KEY TECHNICAL COMPONENTS

### API Authentication
- **OAuth 2.0 / API Keys**: Secure authentication mechanism
- **Certificate-based Security**: SSL/TLS certificates for secure communication
- **Token Management**: Refresh tokens, expiry handling

### Data Fields Typically Available
- Transaction ID (unique identifier)
- Transaction Date & Time
- Transaction Amount
- Transaction Type (Credit/Debit)
- Account Number (Debited/Credited)
- Reference/Description
- Balance After Transaction
- Payer/Payee Name
- Payer/Payee Account Number
- Transaction Status

### Integration Methods
1. **REST API**: Modern, JSON-based, easier to implement
2. **SOAP API**: XML-based, more structured
3. **File-based**: SFTP/FTP file drops (batch processing)
4. **Webhook/Push Notifications**: Real-time transaction alerts

---

## 4. IMPLEMENTATION IN OVEN DELIGHTS ERP

### Database Schema Requirements

#### New Tables Needed:

**1. BankTransactions**
```sql
- TransactionID (PK)
- BankTransactionRef (Unique)
- AccountNumber
- TransactionDate
- TransactionTime
- Amount
- TransactionType (Credit/Debit)
- PayerName
- PayerAccountNumber
- Reference
- Description
- BalanceAfter
- Status (Pending/Matched/Unmatched/Reconciled)
- ImportedDate
- ProcessedDate
- MatchedInvoiceID (FK)
- BranchID (FK)
- Notes
```

**2. PaymentReconciliation**
```sql
- ReconciliationID (PK)
- BankTransactionID (FK)
- InvoiceID (FK)
- MatchType (Auto/Manual)
- MatchConfidence (0-100%)
- MatchedAmount
- MatchedDate
- MatchedBy (UserID)
- Status (Pending/Confirmed/Rejected)
- Notes
```

**3. BankAccounts**
```sql
- BankAccountID (PK)
- BranchID (FK)
- AccountNumber
- AccountName
- BankName
- AccountType
- IsActive
- APICredentials (Encrypted)
- LastSyncDate
```

### Matching Rules Engine

#### Priority 1: Exact Match
- Invoice number found in reference field
- Amount matches invoice balance exactly
- Transaction date within expected payment window

#### Priority 2: Fuzzy Match
- Amount matches within tolerance (e.g., ±R1.00 for rounding)
- Customer name similarity
- Multiple invoices totaling transaction amount

#### Priority 3: Manual Review
- No clear match found
- Multiple possible matches
- Partial payments
- Overpayments

### ERP Module Updates Required

**1. Payment Processing Module**
- Add "Import Bank Transactions" button
- Display unmatched transactions grid
- Manual matching interface
- Bulk reconciliation tools

**2. Invoice Management**
- Show linked bank transactions
- Payment status indicators
- Reconciliation history

**3. Reporting**
- Bank reconciliation report
- Unmatched transactions report
- Payment aging with bank data
- Cash flow analysis

**4. Settings/Configuration**
- Bank account setup
- API credentials management
- Matching rules configuration
- Sync schedule settings

---

## 5. CRITICAL QUESTIONS TO ASK FNB

### A. API ACCESS & CREDENTIALS

1. **What is the process to obtain API access?**
   - Application forms required?
   - Approval timeline?
   - Costs involved (setup fees, monthly fees, per-transaction fees)?

2. **What authentication method is used?**
   - OAuth 2.0, API keys, certificates?
   - How are credentials issued and managed?
   - Credential rotation/expiry policies?

3. **Are there separate credentials for testing vs production?**
   - Sandbox environment available?
   - Test data provided?

4. **What IP whitelisting is required?**
   - Do we need static IPs?
   - VPN requirements?

### B. API CAPABILITIES & LIMITATIONS

5. **What is the maximum date range for a single API call?**
   - Can we retrieve 30 days, 90 days, 1 year of history?
   - Pagination support for large result sets?

6. **What is the API rate limit?**
   - Requests per minute/hour/day?
   - Throttling policies?
   - How are rate limit errors handled?

7. **What transaction types are included?**
   - EFT, card payments, cash deposits, cheques?
   - Internal transfers included?
   - Fees and charges included?

8. **How quickly are transactions available via API?**
   - Real-time, near real-time (minutes), end-of-day?
   - Any delay between transaction and API availability?

9. **Can we retrieve historical data?**
   - How far back can we go?
   - Is there a cost for historical data retrieval?

10. **What data fields are provided for each transaction?**
    - Full list of available fields?
    - Optional vs mandatory fields?
    - Field formats and data types?

### C. ACCOUNT STRUCTURE

11. **Can we access multiple accounts via single API connection?**
    - How are multiple accounts specified?
    - Different credentials per account or single credential?

12. **Do sub-accounts or virtual accounts have separate transaction feeds?**
    - Relevant if using separate accounts per branch

13. **Can we filter transactions by type or amount range?**
    - API-side filtering or must filter locally?

### D. PAYMENT REFERENCES & MATCHING

14. **What is the maximum length of the reference field?**
    - Critical for including invoice numbers
    - Any character restrictions?

15. **How are payment references formatted?**
    - Free text or structured format?
    - Multiple reference fields available?

16. **Can we see the payer's account number and name?**
    - Essential for customer matching
    - Privacy/compliance considerations?

17. **For card payments, what information is provided?**
    - Cardholder name?
    - Last 4 digits?
    - Transaction reference?

### E. RECONCILIATION & STATEMENTS

18. **How do API transactions map to bank statements?**
    - Same transaction IDs used?
    - Timing differences between API and statements?

19. **Are opening and closing balances provided?**
    - Per transaction or per API call?
    - How to verify completeness of data?

20. **What happens if a transaction is reversed or corrected?**
    - Separate reversal transaction?
    - Original transaction updated?
    - How to identify reversals?

### F. TECHNICAL INTEGRATION

21. **What is the API endpoint URL?**
    - Production and sandbox URLs
    - Regional differences?

22. **What data format is used?**
    - JSON, XML, both?
    - Request and response formats?

23. **Is there API documentation available?**
    - Developer portal?
    - Sample code/SDKs?
    - Postman collections?

24. **What error codes and messages are returned?**
    - Complete list of error codes?
    - How to handle errors gracefully?

25. **Are webhooks/push notifications supported?**
    - Real-time transaction alerts?
    - Setup process?

26. **What logging/auditing is done on FNB's side?**
    - Can we see API access logs?
    - Retention period?

### G. SECURITY & COMPLIANCE

27. **What security standards must we comply with?**
    - PCI-DSS requirements?
    - Data encryption requirements?

28. **How should API credentials be stored?**
    - Encryption requirements?
    - Key management?

29. **What are the data retention policies?**
    - How long must we keep transaction data?
    - POPIA compliance requirements?

30. **Are there any restrictions on data usage?**
    - Can we store transaction data indefinitely?
    - Can we share data with third parties (e.g., accountants)?

### H. SUPPORT & SLA

31. **What support is available for integration issues?**
    - Technical support contact?
    - Support hours?
    - Response time SLA?

32. **What is the API uptime SLA?**
    - Guaranteed availability?
    - Planned maintenance windows?
    - Notification process for outages?

33. **How are API changes communicated?**
    - Advance notice period?
    - Versioning strategy?
    - Backward compatibility guarantees?

### I. COSTS & BILLING

34. **What are the costs associated with API access?**
    - Setup fees?
    - Monthly subscription?
    - Per-transaction fees?
    - Volume discounts?

35. **Are there costs for exceeding rate limits?**
    - Overage charges?

36. **What is the billing cycle and payment terms?**

### J. BUSINESS RULES

37. **Can we set up automatic payment notifications?**
    - Email/SMS alerts for specific transaction types?
    - Threshold-based alerts?

38. **Are there any restrictions on automated access?**
    - Must transactions be reviewed by a human?
    - Compliance requirements?

39. **What happens if our API access is suspended?**
    - Reasons for suspension?
    - Reinstatement process?

40. **Can we access transaction data for closed accounts?**
    - Historical data retention?

---

## 6. MAPPING BANK STATEMENTS TO INVOICES

### Automatic Matching Strategies

#### Strategy 1: Invoice Number in Reference
**Best Practice**: Train customers to include invoice number in payment reference
- Example: "INV-2024-001234" or "Invoice 1234"
- Parse reference field using regex patterns
- Match confidence: 95-100%

**Implementation**:
```
1. Extract all numbers from reference field
2. Check if any number matches an open invoice number
3. Verify amount matches invoice balance
4. If match found, auto-reconcile
```

#### Strategy 2: Exact Amount Match
- Find open invoices with exact amount
- Filter by customer if payer details available
- Filter by date range (e.g., invoice date ± 30 days)
- Match confidence: 70-90%

**Considerations**:
- Multiple invoices may have same amount
- Requires additional validation (customer name, date)

#### Strategy 3: Customer Account Matching
- Maintain mapping of customer bank account numbers
- Match transaction to customer first
- Then match to oldest open invoice
- Match confidence: 60-80%

**Database Enhancement**:
```sql
ALTER TABLE Customers
ADD BankAccountNumber VARCHAR(20),
    BankAccountName VARCHAR(100);
```

#### Strategy 4: Partial Payment Handling
- Allow splitting transaction across multiple invoices
- Track partial payments per invoice
- Handle overpayments (credit to customer account)

#### Strategy 5: Bulk Payment Processing
- Some customers pay multiple invoices in one transaction
- Sum of invoice amounts matches transaction amount
- Allocate payment across invoices

### Manual Matching Interface

**Features Needed**:
1. **Unmatched Transactions Grid**
   - Show all unmatched transactions
   - Filter by date, amount, branch
   - Search by reference, payer name

2. **Suggested Matches**
   - Display top 5 possible invoice matches
   - Show match confidence score
   - Highlight matching criteria (amount, customer, date)

3. **Quick Actions**
   - One-click match confirmation
   - Split payment across invoices
   - Mark as "Not an invoice payment" (e.g., loan, transfer)
   - Add to manual review queue

4. **Bulk Operations**
   - Match multiple transactions at once
   - Apply matching rules to filtered set

### Exception Handling

**Common Scenarios**:

1. **Overpayment**
   - Apply to invoice, credit balance to customer account
   - Option to refund or apply to future invoices

2. **Underpayment**
   - Partial payment applied to invoice
   - Invoice remains open for balance
   - Track payment history

3. **Wrong Amount**
   - Flag for investigation
   - Contact customer for clarification
   - Manual adjustment if needed

4. **Duplicate Payment**
   - Identify duplicate transactions
   - Refund process
   - Update invoice status

5. **Payment for Non-existent Invoice**
   - Create credit note
   - Contact customer
   - Possible advance payment

6. **Payment from Unknown Payer**
   - Hold in suspense account
   - Investigation required
   - Possible new customer

### Reconciliation Workflow

**Daily Process**:
```
1. Import transactions (automated, scheduled)
2. Run automatic matching (90% success rate target)
3. Review unmatched transactions (accounting team)
4. Manual matching/investigation
5. Generate reconciliation report
6. Update invoice statuses
7. Send payment confirmations to customers
```

**Month-end Process**:
```
1. Full reconciliation of all accounts
2. Match bank statement to ERP records
3. Investigate all discrepancies
4. Adjust for timing differences
5. Close accounting period
6. Archive reconciliation records
```

---

## 7. IMPLEMENTATION ROADMAP

### Phase 1: Setup & Configuration (Week 1-2)
- [ ] Apply for FNB API access
- [ ] Obtain credentials and documentation
- [ ] Set up sandbox environment
- [ ] Create database schema
- [ ] Configure bank accounts in ERP

### Phase 2: Core Integration (Week 3-4)
- [ ] Develop API connection module
- [ ] Implement transaction import
- [ ] Create staging tables
- [ ] Build basic matching engine
- [ ] Test with sandbox data

### Phase 3: Matching Logic (Week 5-6)
- [ ] Implement automatic matching rules
- [ ] Build manual matching interface
- [ ] Create reconciliation reports
- [ ] Test with real data (limited scope)

### Phase 4: User Interface (Week 7-8)
- [ ] Design payment reconciliation screen
- [ ] Build unmatched transactions grid
- [ ] Create matching wizard
- [ ] Add reporting dashboards

### Phase 5: Testing & Refinement (Week 9-10)
- [ ] User acceptance testing
- [ ] Refine matching rules
- [ ] Performance optimization
- [ ] Security audit

### Phase 6: Go-Live (Week 11-12)
- [ ] Switch to production API
- [ ] Import historical data
- [ ] Train users
- [ ] Monitor and support

---

## 8. RISKS & MITIGATION

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| API downtime | High | Cache data locally, queue failed requests |
| Rate limiting | Medium | Implement exponential backoff, optimize polling |
| Data inconsistency | High | Validate all data, maintain audit logs |
| Security breach | Critical | Encrypt credentials, secure API calls, regular audits |

### Business Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Poor matching accuracy | High | Continuous refinement of rules, manual review process |
| User adoption | Medium | Training, clear benefits communication |
| Cost overruns | Medium | Clear pricing agreement, monitor usage |
| Compliance issues | Critical | Legal review, POPIA compliance |

---

## 9. SUCCESS METRICS

### Key Performance Indicators (KPIs)

1. **Automatic Matching Rate**: Target 85-90%
2. **Time to Reconcile**: Reduce from days to hours
3. **Manual Effort**: Reduce by 70-80%
4. **Payment Processing Time**: Real-time to 24 hours
5. **Error Rate**: < 1% of transactions
6. **User Satisfaction**: > 4/5 rating

### Monitoring & Reporting

**Daily Metrics**:
- Transactions imported
- Automatic matches
- Manual matches
- Unmatched transactions
- Errors/exceptions

**Weekly Metrics**:
- Matching accuracy trend
- Processing time trend
- User activity
- API performance

**Monthly Metrics**:
- Cost analysis
- ROI calculation
- Process improvements
- User feedback

---

## 10. NEXT STEPS

### Immediate Actions
1. **Contact FNB Business Banking**
   - Request API access information
   - Schedule meeting with API team
   - Obtain pricing and documentation

2. **Internal Preparation**
   - Review current payment reconciliation process
   - Document pain points and requirements
   - Identify key users for training
   - Allocate budget and resources

3. **Technical Assessment**
   - Review ERP system capabilities
   - Identify integration points
   - Assess security requirements
   - Plan database changes

### Questions for Internal Stakeholders

**Finance Team**:
- What is the current reconciliation process?
- How many transactions per day/month?
- What are the biggest pain points?
- What reports are needed?

**IT Team**:
- What is our current infrastructure?
- Security and compliance requirements?
- Integration approach (custom vs third-party)?
- Support and maintenance plan?

**Management**:
- Budget approval
- Timeline expectations
- Success criteria
- Risk tolerance

---

## 11. APPENDIX

### Glossary of Terms

- **API**: Application Programming Interface
- **EFT**: Electronic Funds Transfer
- **OAuth**: Open Authorization (security protocol)
- **REST**: Representational State Transfer
- **SOAP**: Simple Object Access Protocol
- **Webhook**: HTTP callback for real-time notifications
- **Reconciliation**: Process of matching transactions to invoices
- **POPIA**: Protection of Personal Information Act

### Sample API Request/Response

**Request** (Conceptual):
```json
{
  "accountNumber": "62xxxxxxxx",
  "fromDate": "2024-01-01",
  "toDate": "2024-01-31",
  "transactionType": "CREDIT"
}
```

**Response** (Conceptual):
```json
{
  "transactions": [
    {
      "transactionId": "TXN123456789",
      "date": "2024-01-15",
      "time": "14:30:00",
      "amount": 1250.00,
      "type": "CREDIT",
      "reference": "INV-2024-001234",
      "payerName": "ABC Bakery",
      "payerAccount": "62xxxxxxxx",
      "balance": 125000.00
    }
  ],
  "totalRecords": 1,
  "hasMore": false
}
```

### Contact Information

**FNB Business Banking**
- Website: www.fnb.co.za/business
- API Support: (To be obtained)
- Business Banking: 087 575 9404

**Oven Delights ERP Team**
- Project Lead: [Name]
- Technical Lead: [Name]
- Finance Lead: [Name]

---

## DOCUMENT VERSION CONTROL

- **Version**: 1.0
- **Date**: January 22, 2026
- **Author**: Oven Delights ERP Team
- **Status**: Draft - Pending FNB Consultation
- **Next Review**: After FNB meeting

---

**END OF DOCUMENT**
