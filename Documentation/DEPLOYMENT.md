# Deployment Guide

## Render

- **Service**: alansaar-erp
- **Service ID**: srv-d9am9358nd3s73am9mc0
- **Dashboard**: https://dashboard.render.com/web/srv-d9am9358nd3s73am9mc0
- **URL**: https://alansaar.site
- **Render API Key**: `rnd_l2KhiW0RbyKIG2XXf1oUAMLb2rJe`
- **GitHub Repo**: https://github.com/mogalia786/alansaar_erp
- **Branch**: main

### Deploy via API

```powershell
$headers = @{ "Authorization" = "Bearer rnd_l2KhiW0RbyKIG2XXf1oUAMLb2rJe"; "Content-Type" = "application/json" }
$body = @{ "clearCache" = "clear" } | ConvertTo-Json
Invoke-RestMethod -Uri "https://api.render.com/v1/services/srv-d9am9358nd3s73am9mc0/deploys" -Headers $headers -Method POST -Body $body
```

### Check Deploy Status

```powershell
$headers = @{ "Authorization" = "Bearer rnd_l2KhiW0RbyKIG2XXf1oUAMLb2rJe" }
Invoke-RestMethod -Uri "https://api.render.com/v1/services/srv-d9am9358nd3s73am9mc0/deploys?limit=5" -Headers $headers
```

### Environment Variables (set in Render dashboard, NOT in .env)

- FNB_BASE_URL is NOT set as env var — uses code default from settings.py
- DATABASE_URL, SECRET_KEY, ALLOWED_HOSTS, email config, AWS S3 config are all set in Render dashboard

### Notes

- `.env` is gitignored — does NOT affect Render deployment
- Render env vars override code defaults
- Auto-deploy is on (commits to main trigger deploy)
- Free plan — cold starts take a few minutes
