"""Shared HTTP helper: GET a URL, retrying on network errors."""

import logging
import time

import requests

logger = logging.getLogger(__name__)
USER_AGENT = "mf-lakehouse portfolio project"


def get(url, params=None, timeout=120, retries=3, backoff=5):
    """Return the response, or raise after `retries` failed attempts."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as err:
            status = err.response.status_code if err.response is not None else None
            if attempt == retries or (status is not None and status < 500):
                raise  # 4xx (e.g. 404 not found) will not fix itself, so don't retry
            wait = backoff * attempt
            logger.warning("GET %s failed (%s); retry %d/%d in %ds", url, err, attempt, retries, wait)
            time.sleep(wait)
