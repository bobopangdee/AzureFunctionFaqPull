# Content Preprocessing Pipeline for Chatbot Knowledge Base

Automated Azure pipeline that fetches raw JSON from an API, strips unnecessary
content from `<img>` `src` attributes, stores the cleaned result in Blob Storage,
and triggers reindexing in Azure AI Search — the knowledge base for an LLM chatbot.

---

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Components](#components)
- [Configuration](#configuration)
- [Triggers](#triggers)
- [Deployment](#deployment)
- [Security](#security)
- [Monitoring](#monitoring)

---

## Overview

Previously, raw JSON content was manually preprocessed (removing image data from
HTML) and uploaded to a Storage container via the Azure Portal. This pipeline
**fully automates** that process using an Azure Function, with optional automatic
reindexing into Azure AI Search.

**Key capabilities:**
- Fetch raw JSON from an external API endpoint
- Strip data content from `<img src>` attributes to reduce noise
- Upload the cleaned JSON to a Blob Storage container
- Trigger Azure AI Search indexer to refresh the vector knowledge base
- Run **manually (HTTP)** or **on a schedule (Timer)**

---

## Architecture

```text
                         ┌──────────────────────┐
        Manual (HTTP)    │                      │
        ───────────────▶ │                      │      ┌─────────────────┐
                         │   Azure Function     │ ───▶ │  API Endpoint   │
        Scheduled        │                      │ ◀─── │  (raw JSON)     │
        ───────────────▶ │  1. Fetch JSON       │      └─────────────────┘
        (Timer)          │  2. Strip img src    │
                         │  3. Upload to Blob   │
                         │  4. Trigger reindex  │
                         └──────┬───────┬───────┘
                                │       │
                                ▼       │
                  ┌──────────────────┐  │
                  │  Blob Storage    │  │
                  │  Container       │  │
                  │  processed.json  │  │
                  └────────┬─────────┘  │
                           │            │
              (indexer     │            │ (run indexer
               reads from) │            │  via REST API)
                           ▼            ▼
                  ┌────────────────────────────┐
                  │     Azure AI Search        │
                  │  ┌──────────────────────┐  │
                  │  │ Indexer              │  │
                  │  │  └▶ Index (vectors)  │  │
                  │  └──────────────────────┘  │
                  └─────────────┬──────────────┘
                                │
                                ▼
                  ┌────────────────────────────┐
                  │   Chatbot API (LLM, RAG)   │
                  │   queries the knowledge base│
                  └────────────────────────────┘
```

---

## How It Works

1. **Trigger** — The function runs on a schedule (Timer) or on demand (HTTP).
2. **Fetch** — Retrieves raw JSON from the configured API endpoint.
3. **Transform** — Strips the value from `<img src>` attributes using BeautifulSoup.
4. **Upload** — Writes the cleaned JSON to Blob Storage (`overwrite=True`,
   single source of truth).
5. **Reindex** — Calls the Azure AI Search REST API to run the indexer, refreshing
   the vector knowledge base used by the chatbot.

---

## Components

| Component               | Service              | Purpose                                  |
|-------------------------|----------------------|------------------------------------------|
| Preprocessing logic     | Azure Functions      | Fetch, transform, upload, trigger        |
| Cleaned content storage | Azure Blob Storage   | Stores `processed.json`                  |
| Knowledge base          | Azure AI Search      | Vector index queried by the chatbot      |
| Secrets management      | Azure Key Vault      | API keys, search admin key (recommended) |
| Identity                | Managed Identity     | Secure, keyless access to Storage        |
| Observability           | Application Insights | Logs, metrics, failures                  |

---

## Configuration

Set these as **Application Settings** in the Function App (or `local.settings.json` locally):

| Setting                      | Description                                    |
|------------------------------|------------------------------------------------|
| `API_ENDPOINT`               | URL of the raw JSON API                        |
| `STORAGE_ACCOUNT`            | Storage account name (for Managed Identity)    |
| `CONTAINER_NAME`             | Target Blob container                          |
| `BLOB_NAME`                  | Output blob name (default `processed.json`)    |
| `SEARCH_SERVICE_NAME`        | Azure AI Search service name                   |
| `SEARCH_INDEXER_NAME`        | Name of the indexer to run                     |
| `SEARCH_API_KEY`             | AI Search admin key (use Key Vault reference)  |
| `SEARCH_API_VERSION`         | REST API version (default `2024-07-01`)        |

---

## Triggers

| Trigger      | Schedule / Route             | Use Case                       |
|--------------|------------------------------|--------------------------------|
| Timer        | `0 0 2 * * *` (02:00 UTC)    | Scheduled refresh              |
| HTTP         | `POST /api/process`          | Manual / on-demand refresh     |

---

## Deployment

### Prerequisites
- Azure CLI + Azure Functions Core Tools
- Python 3.11+
- An existing Storage account, AI Search service, and indexer

### Steps
```bash
# 1. Login
az login

# 2. Deploy (from project root)
func azure functionapp publish <your-function-app-name>

# 3. Configure app settings
az functionapp config appsettings set \
  --name <your-function-app-name> \
  --resource-group <your-rg> \
  --settings API_ENDPOINT="..." CONTAINER_NAME="..." \
             SEARCH_SERVICE_NAME="..." SEARCH_INDEXER_NAME="..."
```

### Grant Managed Identity access to Storage
```bash
az role assignment create \
  --assignee <function-managed-identity-id> \
  --role "Storage Blob Data Contributor" \
  --scope <storage-account-resource-id>
```

---

## Security

- **Managed Identity** for keyless Blob Storage access (no connection strings).
- **Key Vault references** for the API key and AI Search admin key.
- HTTP trigger protected with **Function-level auth** (`AuthLevel.FUNCTION`).
- Least-privilege RBAC (`Storage Blob Data Contributor` only).

---

## Monitoring

- **Application Insights** captures logs, execution times, and exceptions.
- Each run logs: fetch start, transform, upload, and reindex status.
- Set up alerts on function failures for proactive monitoring.
