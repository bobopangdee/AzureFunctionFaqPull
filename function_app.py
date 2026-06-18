import azure.functions as func
import json
import logging
import os

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from bs4 import BeautifulSoup

app = func.FunctionApp()

API_ENDPOINT = os.environ["API_ENDPOINT"]
STORAGE_ACCOUNT = os.environ["STORAGE_ACCOUNT"]
CONTAINER_NAME = os.environ["CONTAINER_NAME"]
BLOB_NAME = os.environ.get("BLOB_NAME", "processed.json")

SEARCH_SERVICE_NAME = os.environ["SEARCH_SERVICE_NAME"]
SEARCH_INDEXER_NAME = os.environ["SEARCH_INDEXER_NAME"]
SEARCH_API_KEY = os.environ["SEARCH_API_KEY"]
SEARCH_API_VERSION = os.environ.get("SEARCH_API_VERSION", "2024-07-01")

_CREDENTIAL = DefaultAzureCredential()
_BLOB_SERVICE = BlobServiceClient(
    account_url=f"https://{STORAGE_ACCOUNT}.blob.core.windows.net",
    credential=_CREDENTIAL,
)


def strip_img_src(raw_json: dict) -> dict:
    """Remove data content from <img src> attributes to reduce noise."""
    html = raw_json.get("content", "")
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        if img.has_attr("src"):
            img["src"] = ""
    raw_json["content"] = str(soup)
    return raw_json


def fetch_and_transform() -> dict:
    logging.info("Fetching raw content from API...")
    try:
        response = requests.get(API_ENDPOINT, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        logging.exception("Failed to fetch content from API endpoint: %s", API_ENDPOINT)
        raise

    try:
        raw = response.json()
    except requests.exceptions.JSONDecodeError:
        logging.exception(
            "API endpoint returned invalid JSON: %s (status=%s)",
            API_ENDPOINT,
            response.status_code,
        )
        raise
    logging.info("Transforming content...")
    return strip_img_src(raw)


def get_blob_client():
    return _BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=BLOB_NAME)


def upload_to_blob(data: dict) -> None:
    blob_client = get_blob_client()
    blob_client.upload_blob(
        json.dumps(data, ensure_ascii=False, indent=2),
        overwrite=True,
    )
    logging.info("Uploaded processed content to %s/%s", CONTAINER_NAME, BLOB_NAME)


def trigger_search_reindex() -> None:
    """Run the Azure AI Search indexer to refresh the knowledge base."""
    url = (
        f"https://{SEARCH_SERVICE_NAME}.search.windows.net"
        f"/indexers/{SEARCH_INDEXER_NAME}/run"
        f"?api-version={SEARCH_API_VERSION}"
    )
    headers = {
        "Content-Type": "application/json",
        "api-key": SEARCH_API_KEY,
    }
    try:
        response = requests.post(url, headers=headers, timeout=30)
    except requests.RequestException:
        logging.exception(
            "Failed to call AI Search indexer run API for '%s'",
            SEARCH_INDEXER_NAME,
        )
        raise

    if response.status_code == 202:
        logging.info("AI Search indexer run triggered successfully.")
    else:
        logging.error(
            "Failed to trigger indexer '%s'. Status: %s, Body: %s",
            SEARCH_INDEXER_NAME,
            response.status_code,
            response.text,
        )
        response.raise_for_status()


def run_pipeline() -> None:
    data = fetch_and_transform()
    upload_to_blob(data)
    trigger_search_reindex()


@app.timer_trigger(schedule="0 0 2 * * *", arg_name="timer", run_on_startup=False)
def scheduled_process(timer: func.TimerRequest) -> None:
    logging.info("Scheduled pipeline run started.")
    try:
        run_pipeline()
        logging.info("Scheduled pipeline run completed.")
    except Exception:
        logging.exception("Scheduled pipeline failed")
        raise


@app.route(route="process", auth_level=func.AuthLevel.FUNCTION)
def manual_process(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Manual pipeline run triggered.")
    try:
        run_pipeline()
        return func.HttpResponse(
            "Pipeline completed: fetched, transformed, uploaded, reindexed.",
            status_code=200,
        )
    except Exception as exc:
        logging.exception("Pipeline failed")
        return func.HttpResponse(f"Error: {str(exc)}", status_code=500)
