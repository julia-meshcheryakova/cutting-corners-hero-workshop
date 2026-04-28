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

### Option 1 — Bicep (infrastructure as code)

The `infra/` folder contains Bicep templates that provision everything:

* App Service Plan (Linux, S1)
* Web App (Python 3.12, system-assigned managed identity)
* RBAC role assignment — **Cognitive Services OpenAI User** on the Azure OpenAI resource

#### Prerequisites

* An existing resource group
* An existing Azure OpenAI resource with a `gpt-4o-mini` deployment

#### Deploy infrastructure

```bash
az deployment group create \
  -g <resource-group> \
  -f infra/main.bicep \
  -p infra/main.bicepparam
```

Override defaults inline if needed:

```bash
az deployment group create \
  -g my-rg \
  -f infra/main.bicep \
  -p appName=myapp \
     skuName=B1 \
     openAiEndpoint=https://my-openai.openai.azure.com/ \
     openAiDeployment=gpt-4o-mini \
     openAiResourceId=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<name>
```

#### Deploy application code

After infrastructure is up, push the app code:

```bash
zip -r deploy.zip app.py index.html facilitator.html scenarios.json requirements.txt
az webapp deploy -g <resource-group> -n <app-name> --src-path deploy.zip --type zip
```

#### Bicep parameters

| Parameter | Default | Description |
|---|---|---|
| `appName` | `cuttingcornershero` | Web app name (must be globally unique) |
| `location` | resource group location | Azure region |
| `skuName` | `S1` | App Service Plan SKU |
| `openAiEndpoint` | *(required)* | Azure OpenAI endpoint URL |
| `openAiDeployment` | `gpt-4o-mini` | Model deployment name |
| `openAiResourceId` | *(required)* | Full resource ID of the Azure OpenAI account |

### Option 2 — Shell script

```bash
export APP_NAME=cutting-corners-hero RESOURCE_GROUP=my-rg APP_SERVICE_PLAN=my-plan
export AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com
bash deploy.sh
```

The deploy script enables system-assigned managed identity on the web app.
After deploying, assign the **Cognitive Services OpenAI User** role to the
web app's managed identity on your Azure OpenAI resource.
