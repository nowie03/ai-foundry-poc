// infra/main.bicep
// ----------------
// Subscription-scoped deployment.
// Deploys Log Analytics workspace, Application Insights, ACR, Container Apps
// Environment, and the OTel Collector Container App into an existing resource
// group (the Azure AI Foundry account/project already live there are not
// managed by this template).
//
// Usage:
//   az deployment sub create \
//     --location eastus2 \
//     --template-file infra/main.bicep \
//     --parameters infra/main.bicepparam \
//     --parameters collectorAuthToken=<token> observeCustomerId=<id> observeDatastreamToken=<token>
//
//   az deployment sub what-if \
//     --location eastus2 \
//     --template-file infra/main.bicep \
//     --parameters infra/main.bicepparam \
//     --parameters collectorAuthToken=<token> observeCustomerId=<id> observeDatastreamToken=<token>

targetScope = 'subscription'

// ── Parameters ────────────────────────────────────────────────────────────────

@description('Deployment environment. Drives naming and configuration.')
@allowed(['dev', 'prod'])
param environment string

@description('Existing resource group to deploy into.')
param resourceGroupName string = 'rg-immanuelnowpertt-6876'

@description('Azure region for all resources.')
param location string = 'eastus2'

@description('Tags applied to all resources.')
param tags object = {
  environment: environment
  application: 'langchain-agent'
  managedBy: 'bicep'
}

@description('Bearer token the Foundry-hosted agent must supply to the OTel Collector.')
@secure()
param collectorAuthToken string

@description('Observe Inc customer ID, used to build the datastream ingest URL.')
@secure()
param observeCustomerId string

@description('Observe Inc datastream bearer token.')
@secure()
param observeDatastreamToken string

// ── Resources module ──────────────────────────────────────────────────────────

module resources 'resources.bicep' = {
  name: 'langchain-resources-${environment}'
  scope: resourceGroup(resourceGroupName)
  params: {
    environment: environment
    location: location
    tags: tags
    collectorAuthToken: collectorAuthToken
    observeCustomerId: observeCustomerId
    observeDatastreamToken: observeDatastreamToken
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

@description('Resource group name deployed into.')
output resourceGroupName string = resourceGroupName

@description('Application Insights resource name.')
output appInsightsName string = resources.outputs.appInsightsName

@description('Log Analytics workspace name.')
output logAnalyticsWorkspaceName string = resources.outputs.logAnalyticsWorkspaceName

@description('App Insights connection string (secure — do not print in plain logs).')
@secure()
output appInsightsConnectionString string = resources.outputs.appInsightsConnectionString

@description('Container Registry login server.')
output acrLoginServer string = resources.outputs.acrLoginServer

@description('OTel Collector public HTTPS endpoint. Set OTEL_EXPORTER_OTLP_ENDPOINT to this value in the Foundry agent environment variables.')
output collectorEndpoint string = resources.outputs.collectorEndpoint
