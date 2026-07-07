// infra/resources.bicep
// ----------------------
// Resource-group-scoped module.
// Called by main.bicep — contains the Log Analytics workspace, Application
// Insights, Container Registry, and standalone OTel Collector Container App
// for one environment.
//
// NOTE: The Azure AI Foundry account/project this collector serves already
// exists in the target resource group (created via the Azure AI Foundry
// portal) and is not managed by this template.

targetScope = 'resourceGroup'

// ── Parameters ────────────────────────────────────────────────────────────────

@description('Deployment environment label (dev or prod).')
param environment string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Tags applied to all resources.')
param tags object

@description('Bearer token the Foundry-hosted agent must supply to the OTel Collector. Generate with: openssl rand -hex 32')
@secure()
param collectorAuthToken string

@description('Observe Inc customer ID, used to build the datastream ingest URL.')
@secure()
param observeCustomerId string

@description('Observe Inc datastream bearer token.')
@secure()
param observeDatastreamToken string

// ── Log Analytics Workspace ───────────────────────────────────────────────────

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-agent-${environment}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: environment == 'prod' ? 90 : 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ── Application Insights ──────────────────────────────────────────────────────

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'ai-agent-${environment}'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    // Workspace-based App Insights (recommended — data queryable in Log Analytics and Sentinel)
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ── Container Registry ────────────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cragent${environment}${uniqueString(resourceGroup().id)}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// ── Container Apps Environment ────────────────────────────────────────────────
resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-agent-${environment}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// ── OTel Collector — Standalone Container App ──────────────────────────────────
// The Collector runs as its own Container App (not as a sidecar).
// External HTTPS ingress is enabled so the Azure AI Foundry-hosted agent can
// reach it over the public internet, secured by bearer token authentication.
resource collectorApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-collector-${environment}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // Public HTTPS ingress — the collector endpoint the Foundry agent calls.
        // TLS is terminated by Container Apps; the collector receives plain HTTP internally.
        external: true
        targetPort: 4318  // OTLP HTTP port
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'appinsights-connection-string'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'registry-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          // Static bearer token that the Foundry agent must send in the
          // Authorization header.  Generate with:
          //   openssl rand -hex 32
          // and inject via:
          //   az deployment sub create ... --parameters collectorAuthToken="<token>"
          name: 'collector-auth-token'
          value: collectorAuthToken
        }
        {
          name: 'observe-customer-id'
          value: observeCustomerId
        }
        {
          name: 'observe-datastream-token'
          value: observeDatastreamToken
        }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'otel-collector'
          image: '${acr.properties.loginServer}/otel-collector:latest'
          args: [
            '--config=/etc/otelcol/collector-config.${environment}.yaml'
          ]
          env: [
            {
              name: 'AZURE_APPINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
            {
              name: 'COLLECTOR_AUTH_TOKEN'
              secretRef: 'collector-auth-token'
            }
            {
              name: 'OBSERVE_CUSTOMER_ID'
              secretRef: 'observe-customer-id'
            }
            {
              name: 'OBSERVE_DATASTREAM_TOKEN'
              secretRef: 'observe-datastream-token'
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ── AcrPull role for collector ────────────────────────────────────────────────
// AcrPull role definition ID: 7f951dda-4ed3-4680-a7ca-43fe172d538d
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, collectorApp.id, acrPullRoleId)
  scope: acr
  properties: {
    principalId: collectorApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

@description('Application Insights resource name.')
output appInsightsName string = appInsights.name

@description('Application Insights instrumentation key.')
output instrumentationKey string = appInsights.properties.InstrumentationKey

@description('Application Insights connection string.')
@secure()
output appInsightsConnectionString string = appInsights.properties.ConnectionString

@description('Log Analytics workspace name.')
output logAnalyticsWorkspaceName string = logAnalyticsWorkspace.name

@description('Log Analytics workspace ID.')
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id

@description('Container Registry login server.')
output acrLoginServer string = acr.properties.loginServer

@description('OTel Collector public HTTPS endpoint. Set OTEL_EXPORTER_OTLP_ENDPOINT to this value in the Foundry agent.')
output collectorEndpoint string = 'https://${collectorApp.properties.configuration.ingress.fqdn}'
