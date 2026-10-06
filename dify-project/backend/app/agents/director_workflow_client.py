"""HTTP client for the independent blocking Dify Director Workflow."""

import json
from typing import Any

import httpx


class DirectorWorkflowError(Exception):
    """Base error for secret-safe Director Workflow failures."""


class DirectorWorkflowConfigurationError(DirectorWorkflowError):
    """The Director Workflow URL or its independent API key is missing."""


class DirectorWorkflowTimeoutError(DirectorWorkflowError):
    """The Director Workflow did not finish before the client timeout."""


class DirectorWorkflowResponseError(DirectorWorkflowError):
    """Dify returned an unsuccessful or malformed workflow result."""


class DirectorWorkflowClient:
    """Submit one bounded context without using Dify conversation memory."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def run(self, director_context_json: str, user_id: str) -> dict[str, Any]:
        """Return the workflow's structured ``recommendation`` output object."""
        if not self.api_url.strip() or not self.api_key.strip():
            raise DirectorWorkflowConfigurationError(
                "Director Workflow is not configured; set DIFY_API_URL and "
                "DIFY_DIRECTOR_API_KEY"
            )

        try:
            response = httpx.post(
                f"{self.api_url}/workflows/run",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "inputs": {"director_context": director_context_json},
                    "response_mode": "blocking",
                    "user": user_id,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise DirectorWorkflowTimeoutError(
                "Director Workflow request timed out"
            ) from error
        except (httpx.RequestError, ValueError) as error:
            raise DirectorWorkflowResponseError(
                "Could not connect to the Director Workflow"
            ) from error

        if response.status_code >= 400:
            raise DirectorWorkflowResponseError(
                f"Dify Director Workflow returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise DirectorWorkflowResponseError(
                "Dify Director Workflow returned malformed JSON"
            ) from error

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or data.get("status") != "succeeded":
            raise DirectorWorkflowResponseError(
                "Dify Director Workflow did not complete successfully"
            )
        outputs = data.get("outputs")
        if not isinstance(outputs, dict) or "recommendation" not in outputs:
            raise DirectorWorkflowResponseError(
                "Dify Director Workflow output is missing recommendation"
            )
        recommendation = outputs["recommendation"]
        if isinstance(recommendation, str):
            try:
                recommendation = json.loads(recommendation)
            except ValueError as error:
                raise DirectorWorkflowResponseError(
                    "Dify Director recommendation is not valid JSON"
                ) from error
        if not isinstance(recommendation, dict):
            raise DirectorWorkflowResponseError(
                "Dify Director recommendation must be a JSON object"
            )
        return recommendation
