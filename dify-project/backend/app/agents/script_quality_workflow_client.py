"""Secret-safe client for the independent Dify Script Quality Workflow."""

import json
from typing import Any

import httpx


class ScriptQualityWorkflowError(Exception):
    """Base error with a safe error category for the development API."""

    error_type = "quality_workflow_error"
    public_message = "Script Quality Workflow failed"


class ScriptQualityNotConfiguredError(ScriptQualityWorkflowError):
    error_type = "quality_not_configured"
    public_message = "Script Quality Dify is not configured"


class ScriptQualityTimeoutError(ScriptQualityWorkflowError):
    error_type = "dify_timeout"
    public_message = "Script Quality Dify request timed out"


class ScriptQualityConnectionError(ScriptQualityWorkflowError):
    error_type = "dify_connection_failed"
    public_message = (
        "Could not connect to Script Quality Dify; check network or proxy settings"
    )


class ScriptQualityHTTPError(ScriptQualityWorkflowError):
    error_type = "dify_http_failure"
    public_message = "Script Quality Dify returned an HTTP error"


class ScriptQualityWorkflowFailedError(ScriptQualityWorkflowError):
    error_type = "workflow_failed"
    public_message = "Script Quality Workflow did not complete successfully"


class ScriptQualityOutputError(ScriptQualityWorkflowError):
    error_type = "invalid_workflow_output"
    public_message = "Script Quality Workflow result must be a JSON object"


class ScriptQualityMalformedJSONError(ScriptQualityWorkflowError):
    error_type = "malformed_json"
    public_message = "Script Quality Workflow returned malformed JSON"


class ScriptQualityMissingResultError(ScriptQualityWorkflowError):
    error_type = "missing_output_result"
    public_message = "Script Quality Workflow output is missing result"


class ScriptQualityWorkflowClient:
    """Run blocking review/revision tasks without conversation memory."""

    def __init__(
        self, api_url: str, api_key: str, timeout_seconds: float = 180.0
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def run(self, task_type: str, payload: str, user_id: str) -> dict[str, Any]:
        """Return the Dify workflow result as a JSON object."""
        if not self.api_url.strip() or not self.api_key.strip():
            raise ScriptQualityNotConfiguredError
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
            raise ScriptQualityTimeoutError from error
        except (httpx.RequestError, ValueError) as error:
            raise ScriptQualityConnectionError from error
        if response.status_code >= 400:
            raise ScriptQualityHTTPError
        try:
            envelope = response.json()
        except ValueError as error:
            raise ScriptQualityMalformedJSONError from error
        data = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(data, dict):
            raise ScriptQualityOutputError
        if data.get("status") != "succeeded":
            raise ScriptQualityWorkflowFailedError
        outputs = data.get("outputs")
        if not isinstance(outputs, dict) or "result" not in outputs:
            raise ScriptQualityMissingResultError
        result = outputs["result"]
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError as error:
                raise ScriptQualityMalformedJSONError from error
        if not isinstance(result, dict):
            raise ScriptQualityOutputError
        return result
