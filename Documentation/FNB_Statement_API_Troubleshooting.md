# FNB Statement API - 400 Bad Request Troubleshooting

## Current Status
The FNB Statement Execution API is returning `400 BAD_REQUEST` with no specific error details.

## Request Details (Verified Correct Format)
```
URL: https://api.p.fnb.co.za/apigateway/statements/retrieveStatement/v1/
Method: POST
Headers:
  - Authorization: Bearer [token]
  - X-Request-ID: [UUID v4]
  - Content-Type: application/json

Body:
{
  "accountId": "63001723469",
  "fromDate": "2025-12-28",
  "toDate": "2026-01-27"
}
```

## Verification Checklist

### ✅ Confirmed Correct:
1. **Date Format**: Using `YYYY-MM-DD` as per API spec
2. **Account Number**: Using sandbox debtor account `63001723469`
3. **Environment**: Using preprod environment `https://api.p.fnb.co.za/apigateway`
4. **Headers**: X-Request-ID (UUID v4) and Authorization Bearer token included
5. **OAuth Token**: Successfully obtained from `/oauth2/token/v2`
6. **Request Structure**: Matches OpenAPI specification exactly

### ❓ Possible Issues:

1. **Account Not Enabled for Statements**
   - The account `63001723469` may be configured for payments only
   - Statement API might require different test account numbers
   - Account may need to be specifically enabled for statement retrieval

2. **OAuth Scope Issue**
   - Client credentials may not have `statement:read` or similar scope
   - Different API products may require separate credentials
   - Statement API might need additional permissions beyond payment API

3. **Environment Mismatch**
   - Preprod environment may not have statement data for this account
   - Integration environment (`api.i.fnb.co.za`) might be required for statements
   - Different environments may use different test accounts

4. **API Product Not Activated**
   - Statement Execution API may be a separate product from Bulk Payment API
   - May require separate onboarding/activation with FNB
   - Client ID may only be authorized for payment APIs

## Recommended Actions

### 1. Contact FNB API Support
**Email**: api.support@fnb.co.za (or check FNB developer portal)

**Information to Provide**:
- Client ID: `E84OOE`
- Environment: Preprod (`api.p.fnb.co.za`)
- API: Statement Execution API v1
- Error: 400 Bad Request with no details
- Request ID: [from logs]
- Question: What test account number should be used for Statement API in preprod?

### 2. Check FNB Developer Portal
- Verify Statement Execution API is activated for your client
- Check if separate credentials are needed
- Look for statement-specific test account numbers
- Review any statement API specific documentation

### 3. Try Integration Environment
Update to integration environment to test:
```sql
UPDATE FNB_APICredentials
SET BaseURL = 'https://api.i.fnb.co.za/apigateway',
    TokenURL = 'https://api.i.fnb.co.za/apigateway/oauth2/token/v2'
WHERE Environment = 'Sandbox'
```

### 4. Alternative: Use Manual Statement Upload
Until API access is resolved, implement manual CSV statement upload:
- Download statement from FNB online banking
- Upload CSV file through Bank Statement Viewer
- Parse and import transactions manually

## Technical Notes

### Working APIs:
- ✅ OAuth Token Generation: Working
- ✅ Bulk Payment API: Working (confirmed from previous implementation)

### Not Working:
- ❌ Statement Execution API: 400 Bad Request

### Hypothesis:
The Statement Execution API likely requires:
1. Separate API product activation
2. Different test account numbers
3. Additional OAuth scopes
4. Or is not available in sandbox/preprod environments

## Next Steps

**Priority 1**: Contact FNB API support to:
- Confirm Statement API is activated for client `E84OOE`
- Get correct test account number for statements
- Verify environment (integration vs preprod)
- Check if additional permissions needed

**Priority 2**: Implement manual statement upload as fallback

**Priority 3**: Once API access confirmed, test with correct account/environment

---

## API Documentation Reference
File: `statementExecutionAPI.yaml`
- Endpoint: `/statements/retrieveStatement/v1/`
- Method: POST
- Request format: Verified correct per OpenAPI spec
- Response: Should return CustomerStatement object with entries

## Error Response
```json
{
  "status": "FAILED",
  "message": "400 BAD_REQUEST",
  "details": "Bad Request"
}
```

**Note**: FNB is not providing specific error details, suggesting either:
- Invalid credentials/permissions
- Account not configured
- API not activated
- Environment issue
