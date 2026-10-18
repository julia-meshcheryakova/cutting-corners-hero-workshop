@description('Name of the web app')
param appName string = 'cuttingcornershero'

@description('Location for all resources')
param location string = resourceGroup().location

@description('App Service Plan SKU')
param skuName string = 'S1'

@description('Azure OpenAI endpoint URL')
param openAiEndpoint string

@description('Azure OpenAI deployment name')
param openAiDeployment string = 'gpt-4o-mini'

@description('Resource ID of the existing Azure OpenAI account for RBAC')
param openAiResourceId string

@secure()
@description('Password for the facilitator page and controls')
param facilitatorKey string

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${appName}-plan'
  location: location
  kind: 'linux'
  properties: {
    reserved: true
  }
  sku: {
    name: skuName
    tier: 'Standard'
  }
}

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'python app.py'
      appSettings: [
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openAiEndpoint
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT'
          value: openAiDeployment
        }
        {
          name: 'FACILITATOR_KEY'
          value: facilitatorKey
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
    }
    httpsOnly: true
  }
}

module openAiRole 'openai-role.bicep' = {
  name: 'openai-role-assignment'
  scope: resourceGroup(split(openAiResourceId, '/')[4])
  params: {
    principalId: webApp.identity.principalId
    openAiAccountName: last(split(openAiResourceId, '/'))
  }
}

output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output principalId string = webApp.identity.principalId
