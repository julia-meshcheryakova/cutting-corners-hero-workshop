#!/bin/bash
# Deploy to Azure App Service (Linux, Python 3.12)
# Prerequisites: az cli logged in, resource group + app service plan exist

APP_NAME="${APP_NAME:-cutting-corners-hero}"
RG="${RESOURCE_GROUP:-my-rg}"
PLAN="${APP_SERVICE_PLAN:-my-plan}"
LOCATION="${LOCATION:-eastus}"

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$APP_NAME" \
  --runtime "PYTHON:3.12"

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --settings \
    AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
    AZURE_OPENAI_KEY="$AZURE_OPENAI_KEY" \
    AZURE_OPENAI_DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-gpt-4o-mini}" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true

# Configure startup command
az webapp config set \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --startup-file "python app.py"

# Deploy from current directory
zip -r deploy.zip . -x "*.git*" "__pycache__/*" "*.pyc" ".env"
az webapp deployment source config-zip \
  --resource-group "$RG" \
  --name "$APP_NAME" \
  --src deploy.zip

rm deploy.zip
echo "Deployed: https://${APP_NAME}.azurewebsites.net"
echo "Facilitator: https://${APP_NAME}.azurewebsites.net/facilitator.html"
