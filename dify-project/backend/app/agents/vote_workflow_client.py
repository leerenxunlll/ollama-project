"""HTTP client for the independent blocking Character Vote Workflow."""

import json
from typing import Any

import httpx


class VoteWorkflowError(Exception):
    """Base error for secret-safe Vote Workflow failures."""


class VoteWorkflowConfigurationError(VoteWorkflowError):
    """The independent Vote Workflow URL or key is missing."""


class VoteWorkflowTimeoutError(VoteWorkflowError):
    """The Vote Workflow did not finish before the client timeout."""


class VoteWorkflowResponseError(VoteWorkflowError):
    """Dify returned an unsuccessful or malformed Vote Workflow result."""


class VoteWorkflowClient:
    """Submit one authorized role context without Dify conversation memory."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def run(self, vote_context_json: str, user_id: str) -> dict[str, Any]:
        """Return the structured ``data.outputs.result`` object."""
        if not self.api_url.strip() or not self.api_key.strip():
            raise VoteWorkflowConfigurationError(
                "Vote Workflow is not configured; set DIFY_API_URL and "
                "DIFY_VOTE_API_KEY"
            )

        try:
            response = httpx.post(
                f"{self.api_url}/workflows/run",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "inputs": {"vote_context": vote_context_json},
                    "response_mode": "blocking",
                    "user": user_id,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise VoteWorkflowTimeoutError("Vote Workflow request timed out") from error
        except httpx.RequestError as error:
            raise VoteWorkflowResponseError(
                "Could not connect to the Vote Workflow"
            ) from error

        if response.status_code >= 400:
            raise VoteWorkflowResponseError(
                f"Dify Vote Workflow returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise VoteWorkflowResponseError(
                "Dify Vote Workflow returned malformed JSON"
            ) from error

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or data.get("status") != "succeeded":
            raise VoteWorkflowResponseError(
                "Dify Vote Workflow did not complete successfully"
            )
        outputs = data.get("outputs")
        if not isinstance(outputs, dict) or "result" not in outputs:
            raise VoteWorkflowResponseError(
                "Dify Vote Workflow output is missing result"
            )
        result = outputs["result"]
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError as error:
                raise VoteWorkflowResponseError(
                    "Dify Vote Workflow result is not valid JSON"
                ) from error
        if not isinstance(result, dict):
            raise VoteWorkflowResponseError(
                "Dify Vote Workflow result must be a JSON object"
            )
        return result
