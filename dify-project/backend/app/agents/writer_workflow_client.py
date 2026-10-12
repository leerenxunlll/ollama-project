"""Secret-safe HTTP client for the independent Dify Writer Workflow."""

import json
from typing import Any

import httpx


class WriterWorkflowError(Exception):
    """Base error for Writer Workflow failures safe to expose by category."""

    error_type = "writer_workflow_error"
    public_message = "Writer Workflow failed"


class WriterNotConfiguredError(WriterWorkflowError):
    error_type = "writer_not_configured"
    public_message = "Writer Dify is not configured"


class WriterTimeoutError(WriterWorkflowError):
    error_type = "dify_timeout"
    public_message = "Writer Dify request timed out"


class WriterConnectionError(WriterWorkflowError):
    error_type = "dify_connection_failed"
    public_message = "Could not connect to Writer Dify; check network or proxy settings"


class WriterHTTPError(WriterWorkflowError):
    error_type = "dify_http_failure"
    public_message = "Writer Dify returned an HTTP error"


class WriterWorkflowFailedError(WriterWorkflowError):
    error_type = "workflow_failed"
    public_message = "Writer Workflow did not complete successfully"


class WriterOutputError(WriterWorkflowError):
    error_type = "invalid_workflow_output"
    public_message = "Writer Workflow result must be a JSON object"


class WriterMalformedJSONError(WriterWorkflowError):
    error_type = "malformed_json"
    public_message = "Writer Workflow returned malformed JSON"


class WriterMissingResultError(WriterWorkflowError):
    error_type = "missing_output_result"
    public_message = "Writer Workflow output is missing result"


class WriterWorkflowClient:
    """Call blocking Workflow API without Dify conversation memory."""

    def __init__(
        self, api_url: str, api_key: str, timeout_seconds: float = 180.0
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def run(self, task_type: str, payload: str, user_id: str) -> dict[str, Any]:
        """Return ``data.outputs.result`` as a JSON object."""
        if not self.api_url.strip() or not self.api_key.strip():
            raise WriterNotConfiguredError

        try:
            response = httpx.post(
                f"{self.api_url}/workflows/run",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "inputs": {"task_type": task_type, "payload": payload},
                    "response_mode": "blocking",
                    "user": user_id,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise WriterTimeoutError from error
        except (httpx.RequestError, ValueError) as error:
            raise WriterConnectionError from error

        if response.status_code >= 400:
            raise WriterHTTPError
        try:
            envelope = response.json()
        except ValueError as error:
            raise WriterMalformedJSONError from error

        data = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(data, dict):
            raise WriterOutputError
        if data.get("status") != "succeeded":
            raise WriterWorkflowFailedError
        outputs = data.get("outputs")
        if not isinstance(outputs, dict) or "result" not in outputs:
            raise WriterMissingResultError

        result = outputs["result"]
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError as error:
                raise WriterMalformedJSONError from error
        if not isinstance(result, dict):
            raise WriterOutputError
        return result
