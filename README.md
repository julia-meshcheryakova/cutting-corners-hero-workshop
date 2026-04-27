---
title: Cutting Corners Hero
description: Interactive security workshop game where participants compete to be the most recklessly efficient AI engineer
---

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Without `AZURE_OPENAI_ENDPOINT` set, the app uses mock scores.
To enable AI scoring, sign in with `az login` and set the endpoint:

```bash
export AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com
python app.py
```

Authentication uses `DefaultAzureCredential`, which picks up your Azure CLI login,
managed identity, or other configured credentials automatically.
The identity needs the **Cognitive Services OpenAI User** role on the Azure OpenAI resource.

* Participants: `http://localhost:5000/`
* Facilitator: `http://localhost:5000/facilitator.html`

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | No | Azure OpenAI endpoint URL (mock scores if absent) |
| `AZURE_OPENAI_DEPLOYMENT` | No | Deployment name (default: `gpt-4o-mini`) |
| `PORT` | No | HTTP port (default: 5000) |

## Deploy to Azure App Service

```bash
export APP_NAME=cutting-corners-hero RESOURCE_GROUP=my-rg APP_SERVICE_PLAN=my-plan
export AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com
bash deploy.sh
```

The deploy script enables system-assigned managed identity on the web app.
After deploying, assign the **Cognitive Services OpenAI User** role to the
web app's managed identity on your Azure OpenAI resource.
