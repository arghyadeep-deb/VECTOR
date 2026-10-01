from loguru import logger
import os

__all__ = [
    "AlphaVantageRateLimitError",
    "API_BASE_URL",
    "format_datetime_for_api",
    "get_api_key",
]

import requests
import pandas as pd
import json
from datetime import datetime
from io import StringIO

API_BASE_URL = "https://www.alphavantage.co/query"

def get_api_key() -> str:
    """Retrieve the API key for Alpha Vantage from environment variables."""
    from core.config import CONFIG as _C
    api_key = _C.get("vector_finagent", {}).get("alpha_vantage_key", "")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")
    return api_key

def format_datetime_for_api(date_input) -> str:
    """Convert various date formats to YYYYMMDDTHHMM format required by Alpha Vantage API."""
    if isinstance(date_input, str):
        # If already in correct format, return as-is
        if len(date_input) == 13 and 'T' in date_input:
            return date_input
        # Try to parse common date formats
        try:
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.strftime("%Y%m%dT0000")
        except ValueError:
            try:
                dt = datetime.strptime(date_input, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y%m%dT%H%M")
            except ValueError:
                raise ValueError(f"Unsupported date format: {date_input}")
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")

class AlphaVantageRateLimitError(Exception):
    """Exception raised when Alpha Vantage API rate limit is exceeded."""
    pass

def _make_api_request(function_name: str, params: dict) -> dict | str:
    """Helper function to make API requests and handle responses.
    
    Raises:
        AlphaVantageRateLimitError: When API rate limit is exceeded
    """
    # Create a copy of params to avoid modifying the original
    api_params = params.copy()
    api_params.update({
        "function": function_name,
        "apikey": get_api_key(),
        "source": "trading_agents",
    })
    
    # Handle entitlement parameter if present in params or global variable
    current_entitlement = globals().get('_current_entitlement')
    entitlement = api_params.get("entitlement") or current_entitlement
    
    if entitlement:
        api_params["entitlement"] = entitlement
    elif "entitlement" in api_params:
        # Remove entitlement if it's None or empty
        api_params.pop("entitlement", None)
    
    try:
        response = requests.get(API_BASE_URL, params=api_params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        # requests embeds the full URL (including ``apikey=``) in its error
        # text; never let that reach logs, callers or LLM prompts.
        logger.warning("[VECTOR][alpha_vantage] {} request failed: {}", function_name, type(exc).__name__)
        raise RuntimeError(
            f"Alpha Vantage {function_name} request failed: {type(exc).__name__}"
        ) from None

    response_text = response.text

    # Alpha Vantage reports errors as HTTP 200 with a JSON body; CSV data is
    # not valid JSON, so a successful decode into a dict means an API message.
    try:
        response_json = json.loads(response_text)
    except json.JSONDecodeError:
        response_json = None  # CSV payload: the normal success case
    if isinstance(response_json, dict):
        if not response_json:
            raise ValueError(f"Alpha Vantage {function_name} returned an empty response (unknown symbol?)")
        if "Error Message" in response_json:
            raise ValueError(f"Alpha Vantage error: {response_json['Error Message']}")
        for key in ("Information", "Note"):
            if key in response_json:
                raise AlphaVantageRateLimitError(
                    f"Alpha Vantage rate limit/usage notice: {response_json[key]}"
                )

    return response_text



def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    """
    Filter CSV data to include only rows within the specified date range.

    Args:
        csv_data: CSV string from Alpha Vantage API
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Filtered CSV string
    """
    if not csv_data or csv_data.strip() == "":
        return csv_data

    try:
        # Parse CSV data
        df = pd.read_csv(StringIO(csv_data))

        # Assume the first column is the date column (timestamp)
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])

        # Filter by date range
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        filtered_df = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]

        # Convert back to CSV string
        return filtered_df.to_csv(index=False)

    except Exception as e:
        # Returning the unfiltered CSV would leak rows after end_date
        # (look-ahead) or pass an error body off as data.
        logger.error("[VECTOR][alpha_vantage] failed to filter CSV by date range: {}", e)
        raise ValueError(f"Alpha Vantage CSV could not be parsed/filtered: {e}") from None
