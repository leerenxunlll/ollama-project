"""Validate Director Workflow output without granting database access."""

from pydantic import ValidationError

from app.agents.director_workflow_client import DirectorWorkflowClient
from app.core.config import settings
from app.schemas.director import DirectorContext, DirectorRecommendation


class DirectorOutputValidationError(ValueError):
    """The Workflow returned data outside the Director recommendation contract."""


class DirectorAgent:
    """Convert one safe DirectorContext into one validated recommendation."""

    def __init__(self, workflow_client: DirectorWorkflowClient) -> None:
        self.workflow_client = workflow_client

    def analyze(self, context: DirectorContext) -> DirectorRecommendation:
        """Ask Dify for a structured observation; never load or mutate game state."""
        output = self.workflow_client.run(
            context.model_dump_json(), user_id=f"game-{context.game_id}-director"
        )
        try:
            return DirectorRecommendation.model_validate(output)
        except ValidationError as error:
            raise DirectorOutputValidationError(
                "Dify Director output did not match DirectorRecommendation"
            ) from error


def get_director_agent() -> DirectorAgent:
    """Build a request-scoped client with the Director-only credential."""
    return DirectorAgent(
        DirectorWorkflowClient(
            api_url=settings.dify_api_url,
            api_key=settings.dify_director_api_key,
        )
    )
