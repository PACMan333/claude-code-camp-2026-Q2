import json
import ssl
import time
import urllib.error
import urllib.request
from http.client import IncompleteRead

from .errors import ApiError

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    ConnectionError,
    IncompleteRead,
    ssl.SSLError,
)
MAX_RETRIES = 3
BASE_RETRY_DELAY = 0.5


class Client:
    def __init__(self, builder) -> None:
        self._builder = builder

    def call(self, *, max_output_tokens: int = 1024, tools=None):
        payload = json.dumps(
            self._builder.to_api_payload(max_output_tokens=max_output_tokens, tools=tools)
        ).encode("utf-8")
        request = urllib.request.Request(
            self._builder.url(),
            data=payload,
            headers=self._builder.headers(),
            method="POST",
        )

        attempts = 0
        while True:
            attempts += 1

            try:
                with urllib.request.urlopen(request) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as e:
                if e.code in RETRYABLE_STATUS_CODES and attempts <= MAX_RETRIES:
                    time.sleep(self._retry_delay(attempts))
                    continue

                if e.code == 401:
                    raise ApiError("authentication failed (401) — check your API key") from e

                body = e.read().decode("utf-8", errors="replace")
                raise ApiError(
                    "API request failed after {} attempt{} ({}): {}".format(
                        attempts, "" if attempts == 1 else "s", e.code, body
                    )
                ) from e
            except TRANSIENT_ERRORS as e:
                if attempts > MAX_RETRIES:
                    raise ApiError(
                        "API request failed after {} attempts: {}: {}".format(
                            attempts, type(e).__name__, e
                        )
                    ) from e

                time.sleep(self._retry_delay(attempts))

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return BASE_RETRY_DELAY * (2 ** (attempt - 1))
