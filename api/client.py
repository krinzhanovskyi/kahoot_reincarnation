"""Shared HTTP requests and user-facing API errors."""

import requests

from api.config import HEADERS, REQUEST_TIMEOUT


class KahootAPIError(Exception):
    """A request failure with a message safe to display in the interface."""


def get_json(url, *, params=None):
    try:
        with requests.get(
            url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT
        ) as response:
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise KahootAPIError("Kahoot returned invalid JSON. Try again later.") from exc
    except requests.Timeout as exc:
        raise KahootAPIError("Kahoot took too long to respond. Please try again.") from exc
    except requests.ConnectionError as exc:
        raise KahootAPIError("Could not connect to Kahoot. Check your connection.") from exc
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        messages = {
            401: "Kahoot requires authorization for this request.",
            403: "Kahoot denied access to this request.",
            404: "The requested Kahoot resource was not found.",
            429: "Too many requests. Please wait before trying again.",
        }
        message = messages.get(status)
        if message is None:
            if status is not None and 500 <= status < 600:
                message = f"Kahoot server error (HTTP {status}). Try again later."
            else:
                message = f"Kahoot request failed (HTTP {status or 'unknown'})."
        raise KahootAPIError(message) from exc
    except requests.RequestException as exc:
        raise KahootAPIError("The request to Kahoot failed. Please try again.") from exc
