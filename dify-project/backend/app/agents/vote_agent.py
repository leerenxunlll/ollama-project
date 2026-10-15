"""Validate one AI voting decision without giving the Agent database access."""

from pydantic import ValidationError

from app.agents.vote_workflow_client import VoteWorkflowClient
from app.core.config import settings
from app.schemas.voting import CharacterVoteContext, CharacterVoteDecision


class VoteDecisionValidationError(ValueError):
    """The Workflow returned a decision outside the strict vote contract."""


class CharacterVoteAgent:
    """Convert a permission-filtered vote context into one validated decision."""

    def __init__(self, workflow_client: VoteWorkflowClient) -> None:
        self.workflow_client = workflow_client

    @property
    def configured(self) -> bool:
        """Whether the Vote-only URL and credential are present."""
        return bool(
            self.workflow_client.api_url.strip()
            and self.workflow_client.api_key.strip()
        )

    def decide(self, context: CharacterVoteContext) -> CharacterVoteDecision:
        output = self.workflow_client.run(
            context.model_dump_json(),
            user_id=(f"game-{context.game_id}-voter-{context.voter_game_character_id}"),
        )
        try:
            return CharacterVoteDecision.model_validate(output)
        except ValidationError as error:
            raise VoteDecisionValidationError(
                "Dify Vote Workflow output did not match CharacterVoteDecision"
            ) from error


def get_character_vote_agent() -> CharacterVoteAgent:
    """Build a request-scoped client using only the Vote Workflow credential."""
    return CharacterVoteAgent(
        VoteWorkflowClient(
            api_url=settings.dify_api_url,
            api_key=settings.dify_vote_api_key,
        )
    )
