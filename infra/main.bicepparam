using './main.bicep'

param appName = 'cuttingcornershero'
param skuName = 'S1'
param openAiEndpoint = 'https://openai-juliameai.openai.azure.com/'
param openAiDeployment = 'gpt-4o-mini'
param openAiResourceId = '/subscriptions/765e135f-0a63-495f-885e-fd3fcb4cc30d/resourceGroups/rg-juliameai/providers/Microsoft.CognitiveServices/accounts/openai-juliameai'
param facilitatorKey = readEnvironmentVariable('FACILITATOR_KEY')
