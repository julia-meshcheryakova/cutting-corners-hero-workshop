# Cutting Corners Hero

Interactive security workshop — participants compete to be the most recklessly efficient AI engineer.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in your Azure OpenAI creds (optional — mock scores work without)
python app.py
```

- Participants: http://localhost:5000/
- Facilitator: http://localhost:5000/facilitator.html

## Env vars

| Variable | Required | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | No | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_KEY` | No | API key (mock scores if absent) |
| `AZURE_OPENAI_DEPLOYMENT` | No | Deployment name (default: `gpt-4o-mini`) |
| `PORT` | No | HTTP port (default: 5000) |

## Deploy to Azure App Service

```bash
export APP_NAME=cutting-corners-hero RESOURCE_GROUP=my-rg APP_SERVICE_PLAN=my-plan
export AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_KEY=...
bash deploy.sh
```
