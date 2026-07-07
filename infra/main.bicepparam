// infra/main.bicepparam
// ----------------------
// Example parameter file for the dev environment.
// Copy to main.prod.bicepparam and change environment to 'prod' for production.
//
// Secrets (collectorAuthToken, observeCustomerId, observeDatastreamToken) are
// NOT set here — pass them inline on the CLI so they never land in a file:
//   az deployment sub create \
//     --location eastus2 \
//     --template-file infra/main.bicep \
//     --parameters infra/main.bicepparam \
//     --parameters collectorAuthToken=<token> observeCustomerId=<id> observeDatastreamToken=<token>

using 'main.bicep'

param environment = 'dev'
param resourceGroupName = 'rg-immanuelnowpertt-6876'
param location = 'eastus2'
param tags = {
  environment: 'dev'
  application: 'langchain-agent'
  managedBy: 'bicep'
}
