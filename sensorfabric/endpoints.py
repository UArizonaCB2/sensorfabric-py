#!/usr/bin/env python3

# Base MDH Endpoint
MDH_BASE = 'https://designer.mydatahelps.org'

# Endpoint for MDH token.
MDH_TOKEN_URL = 'https://designer.mydatahelps.org/identityserver/connect/token'

# Endpoint for MDH explorer.
MDH_EXPLORER_URL = 'https://api.designer.mydatahelps.org/projects/{projectID}/export-explorer/token'

# Get project exports meta-data
MDH_EXPORT_DETAILS = '/api/v1/administration/projects/{projectID}/exports'

# Get incremental export data
MDH_EXPORT_DATA = '/api/v1/administration/projects/{projectID}/exports/{exportID}/data'

# MDH admin endpoint
MDH_PROJ= '/api/v1/administration/projects/{projectID}/'
