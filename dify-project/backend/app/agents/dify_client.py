"""HTTP client for Dify Chatflow's blocking chat-messages API."""

import httpx


class DifyError(Exception):
    """Base class for failures returned while communicating with Dify."""


class DifyConfigurationError(DifyError):
    """Raised when the Dify URL or character API key is missing."""


class DifyTimeoutError(DifyError):
    """Raised when Dify does not answer before the configured timeout."""


class DifyConnectionError(DifyError):
    """Raised when the Dify endpoint cannot be reached."""


class DifyAuthenticationError(DifyError):
    """Raised when Dify rejects the API key."""


class DifyForbiddenError(DifyError):
    """Raised when Dify denies access to the Chatflow."""


class DifyRequestError(DifyError):
    """Raised when Dify rejects the request payload."""


class DifyProviderError(DifyError):
    """Raised when Dify returns a server-side failure."""


class DifyResponseError(DifyError):
    """Raised when Dify returns a malformed or empty chat response."""


class DifyClient:
    """Send one blocking chat request without knowing game or database rules."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        character_context: str,
        interaction_context: str,
        query: str,
        user_id: str,
    ) -> str:
        """Return Dify's answer text or raise a classified, secret-safe error."""
        if not self.api_url.strip() or not self.api_key.strip():
            raise DifyConfigurationError(
                "Dify character chat is not configured; set DIFY_API_URL and "
                "DIFY_CHARACTER_API_KEY"
            )

        try:
            response = httpx.post(
                f"{self.api_url}/chat-messages",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "inputs": {
                        "character_context": character_context,
                        "interaction_context": interaction_context,
                    },
                    "query": query,
                    "response_mode": "blocking",
                    "conversation_id": "",
                    "user": user_id,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise DifyTimeoutError("Dify chat request timed out") from error
        except httpx.RequestError as error:
            raise DifyConnectionError("Could not connect to Dify") from error
        except ValueError as error:
            raise DifyConnectionError(
                "Dify HTTP client configuration is invalid; check proxy settings"
            ) from error

        if response.status_code == 401:
            raise DifyAuthenticationError("Dify rejected the character API key")
        if response.status_code == 403:
            raise DifyForbiddenError("Dify denied access to the Chatflow")
        if 400 <= response.status_code < 500:
            raise DifyRequestError("Dify rejected the chat request")
        if response.status_code >= 500:
            raise DifyProviderError("Dify returned a server error")

        try:
            payload = response.json()
        except ValueError as error:
            raise DifyResponseError("Dify returned malformed JSON") from error

        answer = payload.get("answer") if isinstance(payload, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            raise DifyResponseError("Dify response did not contain an answer")
        return answer
