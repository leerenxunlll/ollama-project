export interface HealthResponse {
  status: string
  app: string
}

export interface AiStatusResponse {
  configured: boolean
}

export interface VoteWorkflowStatusResponse {
  configured: boolean
}

export interface MessageRead {
  id: number
  game_session_id: number
  sender_game_character_id: number
  channel_type: string
  receiver_game_character_id: number | null
  content: string
  created_at: string
}

export interface AiChatResponse {
  human_message: MessageRead
  ai_message: MessageRead
}

export interface PublicTurnResponse {
  human_message: MessageRead
  ai_responses: MessageRead[]
  status: 'completed' | 'partial'
  failures: Array<{
    game_character_id: number
    error_type: string
  }>
}

export interface AiStepResponse {
  ai_message: MessageRead
}

export type CharacterEmotion =
  | 'calm'
  | 'nervous'
  | 'angry'
  | 'afraid'
  | 'sad'
  | 'confident'
  | 'suspicious'
  | 'confused'

export type CharacterIntent =
  | 'cooperate'
  | 'hide_information'
  | 'seek_information'
  | 'accuse'
  | 'deflect'
  | 'persuade'
  | 'observe'
  | 'other'

export interface CharacterDebugState {
  game_id: number
  game_character_id: number
  current_emotion: CharacterEmotion | null
  latest_thought: {
    inner_os: string
    emotion: CharacterEmotion
    intent: CharacterIntent
    created_at: string
  } | null
  memories: Array<{
    id: number
    content: string
    importance: number
    source_message_id: number
    created_at: string
  }>
}

export interface ScriptSummary {
  id: number
  title: string
  summary: string | null
  theme: string | null
  status: string
}

export interface GameCharacterSummary {
  id: number
  character_id: number
  controller_type: 'human' | 'ai' | null
  character: {
    id: number
    name: string
  }
}

export type GameStatus =
  | 'waiting_for_character_selection'
  | 'ready'
  | 'in_progress'
  | 'finished'
  | 'completed'
  | 'abandoned'

export type GamePhase =
  | 'intro'
  | 'act_1'
  | 'investigation_1'
  | 'discussion_1'
  | 'act_2'
  | 'investigation_2'
  | 'discussion_2'
  | 'final_discussion'
  | 'vote'
  | 'ending'

export interface GameResponse {
  id: number
  script_id: number
  status: GameStatus
  current_phase: GamePhase
  human_intro_acknowledged_at: string | null
  created_at: string
  started_at: string | null
  ended_at: string | null
  game_characters: GameCharacterSummary[]
}

export type StoryUnlockPhase = 'intro' | 'act_1' | 'act_2'

export interface StoryChapterRead {
  chapter_id: number
  title: string
  chapter_order: number
  unlock_phase: StoryUnlockPhase
  content: string
}

export interface IntroAcknowledgementResponse {
  game_id: number
  acknowledged: boolean
  acknowledged_at: string | null
}

export interface GameStateResponse {
  game_id: number
  status: GameStatus
  current_phase: GamePhase
  started_at: string | null
  ended_at: string | null
  next_phase: GamePhase | null
  can_investigate: boolean
}

export interface GameFlowState {
  game_id: number
  status: GameStatus
  current_phase: GamePhase
  phase_started_at: string | null
  elapsed_seconds: number
  minimum_duration_seconds: number
  remaining_seconds: number
  minimum_time_satisfied: boolean
  can_investigate: boolean
  can_discuss: boolean
  can_public_speak: boolean
  can_vote: boolean
  can_advance: boolean
  is_finished: boolean
  vote_progress: {
    votes_cast: number
    total_voters: number
    voting_complete: boolean
  }
}

export interface GameRuntimeActionRead {
  id: number
  event_type: string
  action_type: string | null
  execution_status: 'processing' | 'completed' | 'failed' | 'skipped'
  reason_code: string | null
  started_at: string
  completed_at: string | null
  related_message_id: number | null
  related_recommendation_id: number | null
}

export interface GameRuntimeStatus {
  game_id: number
  game_status: GameStatus
  current_phase: GamePhase
  runtime_status: 'not_started' | 'enabled' | 'paused'
  phase_read_acknowledged: boolean
  ready_for_phase: GamePhase | null
  action_status: 'idle' | 'processing' | 'failed'
  last_tick_at: string | null
  last_director_analysis_at: string | null
  last_proactive_speech_at: string | null
  last_action_type: string | null
  last_error_code: string | null
  next_check_after_seconds: number
  recent_actions: GameRuntimeActionRead[]
}

export interface RuntimeStepResult {
  game_id: number
  runtime_status: 'not_started' | 'enabled' | 'paused'
  action_type:
    | 'none'
    | 'director_analysis'
    | 'proactive_speech'
    | 'ai_investigation'
    | 'ai_vote'
    | 'phase_advance'
    | 'advisory'
  execution_status: 'idle' | 'completed' | 'failed' | 'conflict'
  phase_before: GamePhase
  phase_after: GamePhase
  public_message_id: number | null
  vote_id: number | null
  recommendation_id: number | null
  reason_code: string
  next_check_after_seconds: number
}

export interface PhaseAcknowledgement {
  game_id: number
  phase: 'intro' | 'act_1' | 'act_2'
  acknowledged: boolean
  acknowledged_at: string
}

export interface RuntimeReadyResponse {
  game_id: number
  phase:
    | 'investigation_1'
    | 'discussion_1'
    | 'investigation_2'
    | 'discussion_2'
    | 'final_discussion'
  ready: boolean
  ready_at: string
}

export interface VoteRead {
  id: number
  game_session_id: number
  voter_game_character_id: number
  target_game_character_id: number
  created_at: string
}

export interface VoteResult {
  game_id: number
  vote_count_by_target: Record<number, number>
  winner_game_character_id: number | null
  is_tie: boolean
  votes_cast: number
  total_voters: number
  voting_complete: boolean
  submitted_voter_game_character_ids: number[]
}

export interface GameVoteStatus {
  game_id: number
  current_phase: GamePhase
  votes_cast: number
  total_voters: number
  human_has_voted: boolean
  ai_characters: {
    game_character_id: number
    character_name: string
    has_voted: boolean
  }[]
  voting_complete: boolean
}

export interface GameEnding {
  game_id: number
  script_id: number
  culprit_game_character_id: number
  culprit_name: string
  vote_result: 'culprit_identified' | 'wrong_accusation' | 'tie'
  accused_game_character_id: number | null
  is_tie: boolean
  human_vote_target_id: number
  human_identified_culprit: boolean
  case_outcome: 'culprit_identified' | 'wrong_accusation' | 'tie'
  ending_narrative: string
  resolved_at: string
  truth: {
    culprit_role_key: string
    victim: string
    motive: string
    method: string
    crime_time: string
    crime_location: string
    case_summary: string
    key_causal_facts: string[]
  }
  canonical_timeline: {
    event_key: string
    time: string
    location: string
    description: string
    involved_role_keys: string[]
    is_public_knowledge: boolean
  }[]
  key_clues: {
    clue_id: number
    name: string
    description: string
    act: string
    location: string
  }[]
  votes: {
    vote_id: number
    voter_game_character_id: number
    voter_name: string
    target_game_character_id: number
    target_name: string
    reason: string | null
    created_at: string
  }[]
}

export interface GameReplayEvent {
  event_id: string
  event_type:
    | 'game_started'
    | 'message'
    | 'character_thought'
    | 'character_memory'
    | 'clue_acquired'
    | 'clue_disclosure'
    | 'vote'
    | 'game_ended'
  timestamp: string
  phase: GamePhase | null
  actor_game_character_id: number | null
  actor_name: string | null
  target_game_character_id: number | null
  target_name: string | null
  visibility: 'public' | 'private' | 'god'
  content: string | null
  inner_os: string | null
  emotion: string | null
  intent: string | null
  memory_importance: number | null
  subjective: boolean
  related_message_id: number | null
  related_clue_id: number | null
  related_vote_id: number | null
}

export interface GameReplay {
  game_id: number
  started_at: string | null
  ended_at: string
  events: GameReplayEvent[]
}

export interface DirectorStatusResponse {
  configured: boolean
}

export type WriterDifficulty = 'easy' | 'medium' | 'hard'
export type WriterPhase = 'intro' | 'act_1' | 'act_2'

export interface WriterCreateRequest {
  theme: string
  era: string
  atmosphere: string
  difficulty: WriterDifficulty
  custom_requirements?: string | null
}

export interface WriterCharacterDraft {
  role_key: 'role_1' | 'role_2' | 'role_3' | 'role_4'
  name: string
  age: number | null
  identity: string
  public_background: string
  private_background: string
  personality: string
  speaking_style: string
  personal_goal: string
  personal_history: string
  relationship_to_victim: string
  pre_case_experience: string
  private_secrets: string[]
  initial_knowledge: string[]
}

export interface WriterBlueprint {
  script_metadata: {
    title: string
    summary: string
    theme: string
    era: string
    atmosphere: string
    difficulty: WriterDifficulty
  }
  case_truth: {
    culprit_role_key: WriterCharacterDraft['role_key']
    victim: string
    motive: string
    method: string
    crime_time: string
    crime_location: string
    case_summary: string
    key_causal_facts: string[]
  }
  canonical_timeline: Array<{
    event_key: string
    time: string
    location: string
    description: string
    involved_role_keys: WriterCharacterDraft['role_key'][]
    is_public_knowledge: boolean
  }>
  characters: WriterCharacterDraft[]
  clues: Array<{
    clue_key: string
    name: string
    description: string
    act: 'act_1' | 'act_2'
    location: string
    is_core: boolean
    importance: number
    related_event_keys: string[]
  }>
}

export interface WriterChapter {
  title: string
  content: string
  chapter_order: number
  unlock_phase: WriterPhase
}

export interface WriterChapterPack {
  phase: WriterPhase
  shared_chapter: WriterChapter
  character_chapters: Array<
    WriterChapter & {
      role_key: WriterCharacterDraft['role_key']
    }
  >
}

export interface WriterDraft {
  id: number
  status: string
  content_revision: number
  publication_status: 'unpublished' | 'publishing' | 'published'
  published_script_id: number | null
  generation_request: WriterCreateRequest
  blueprint: WriterBlueprint | null
  chapter_packs: Partial<Record<WriterPhase, WriterChapterPack>>
  step_durations_seconds: Record<string, number>
  failed_step: string | null
  last_error_type: string | null
  completed_steps: string[]
}

export interface WriterStatusResponse {
  configured: boolean
}

export interface ScriptQualityStatusResponse {
  configured: boolean
}

export type ScriptReviewSeverity = 'critical' | 'high' | 'medium' | 'low'
export type ScriptReviewVerdict = 'pass' | 'needs_revision' | 'blocked'

export interface ScriptReviewIssue {
  issue_code: string
  category: string
  severity: ScriptReviewSeverity
  description: string
  location: {
    scope:
      | 'blueprint'
      | 'case_truth'
      | 'timeline_event'
      | 'character'
      | 'clue'
      | 'shared_chapter'
      | 'character_chapter'
    field_path: string
    phase: WriterPhase | null
    role_key: WriterCharacterDraft['role_key'] | null
    event_key: string | null
    clue_key: string | null
  }
  evidence: string
  suggested_fix: string
}

export interface ScriptReviewRun {
  id: number
  draft_id: number
  content_revision: number
  review_status: 'completed' | 'failed' | 'stale'
  report: {
    verdict: ScriptReviewVerdict
    summary: string
    issues: ScriptReviewIssue[]
  } | null
  error_type: string | null
  created_at: string
  completed_at: string | null
}

export interface ScriptRevisionRecord {
  id: number
  draft_id: number
  from_revision: number
  to_revision: number
  phase: WriterPhase
  related_review_id: number
  issues_addressed: ScriptReviewIssue[]
  previous_chapter_pack: WriterChapterPack
  new_chapter_pack: WriterChapterPack
  created_at: string
}

export interface ScriptRevisionResponse {
  revision: ScriptRevisionRecord
  content_revision: number
}

export interface ScriptApprovalResponse {
  draft_id: number
  content_revision: number
  review_run_id: number
  accepted_medium_issue_indexes: number[]
  approved_at: string
}

export interface ScriptPublicationResponse {
  draft_id: number
  publication_status: 'unpublished' | 'publishing' | 'published'
  script_id: number | null
  content_revision: number
  title: string | null
  approved_revision: number | null
  approved_review_run_id: number | null
  approved_at: string | null
}

export interface DirectorRecommendationRecord {
  id: number
  game_session_id: number
  pace: string
  narrative_risk: string
  recommended_action: string
  target_game_character_id: number | null
  clue_id: number | null
  public_message_id: number | null
  reason: string
  status: 'pending' | 'applying' | 'applied' | 'rejected' | 'advisory'
  created_at: string
  applied_at: string | null
}

export interface DirectorApplyResult {
  recommendation_id: number
  status: 'applied' | 'rejected' | 'advisory'
  reason: string
  public_message?: MessageRead
  flow_state?: GameFlowState
}

export interface InvestigationLocationsResponse {
  game_id: number
  current_phase: GamePhase
  locations: string[]
}

export interface InvestigationSearchResponse {
  game_id: number
  game_character_id: number
  location: string
  found: boolean
  clue: {
    id: number
    name: string
    description: string
    act: string
    location: string
    is_core: boolean
    importance: number
  } | null
}

export type ClueKnowledgeSource =
  'direct_acquisition' | 'private_disclosure' | 'public_disclosure'

export interface ClueEvidence {
  clue_id: number
  name: string
  description: string
  act: string
  location: string
  importance: number
  knowledge_source: ClueKnowledgeSource
  first_known_at: string
  source_game_character_id: number | null
}

export interface MyClueState {
  game_id: number
  human_game_character_id: number
  acquired_clues: ClueEvidence[]
  known_via_share_clues: ClueEvidence[]
  publicly_disclosed_clues: ClueEvidence[]
}

export interface ClueHistoryEvent {
  event_id: string
  event_type:
    'clue_acquired' | 'clue_shared_privately' | 'clue_disclosed_publicly'
  clue_id: number
  clue_name: string
  actor_name: string
  target_name: string | null
  occurred_at: string
}

export interface ClueDisclosureResponse {
  id: number
  game_id: number
  clue_id: number
  source_game_character_id: number
  visibility: 'private' | 'public'
  target_game_character_id: number | null
  related_message_id: number
  created_at: string
  replayed: boolean
}

export interface SelectableCharacter {
  game_character_id: number
  character_id: number
  name: string
  age: number | null
  identity: string
  public_background: string
  personality: string
  speaking_style: string
}

export interface MyCharacterCard extends SelectableCharacter {
  private_background: string
  personal_goal: string
  personal_history: string | null
  relationship_to_victim: string | null
  pre_case_experience: string | null
  private_secrets: string[]
  initial_knowledge: string[]
  current_emotion: string | null
  current_goal: string | null
}

export interface CharacterContext {
  game: {
    id: number
    status: string
    current_phase: string
  }
  character: {
    game_character_id: number
    character_id: number
    name: string
    identity: string
    public_background: string
    private_background: string
    personality: string
    speaking_style: string
    personal_goal: string
    current_emotion: string | null
    current_goal: string | null
  }
  other_characters: Array<{
    game_character_id: number
    name: string
    identity: string
    public_background: string
  }>
  public_messages: ContextMessage[]
  private_messages: ContextMessage[]
  known_clues: Array<{
    clue_id: number
    name: string
    description: string
    act: string
    location: string
    is_core: boolean
    importance: number
    discovered_at: string
    source: string | null
  }>
  memories: Array<{
    content: string
    importance: number
    created_at: string
  }>
}

export interface ContextMessage {
  id: number
  sender_game_character_id: number | null
  channel_type: 'public' | 'private' | 'system'
  receiver_game_character_id: number | null
  content: string
  created_at: string
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

function publishDebugEvent(detail: {
  message: string
  method: string
  path: string
  status?: number
}) {
  const eventDetail = {
    source: 'api',
    timestamp: new Date().toISOString(),
    ...detail,
  }
  window.dispatchEvent(new CustomEvent('amm:debug', { detail: eventDetail }))
  console.debug('[AMM]', eventDetail)
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = init.method ?? 'GET'
  let responseStatus: number | undefined

  try {
    const response = await fetch(`${apiBaseUrl}${path}`, init)
    responseStatus = response.status
    if (!response.ok) {
      let message = `后端返回 HTTP ${response.status}`
      try {
        const errorPayload = (await response.json()) as { detail?: unknown }
        if (typeof errorPayload.detail === 'string') {
          message = errorPayload.detail
        } else if (
          typeof errorPayload.detail === 'object' &&
          errorPayload.detail !== null &&
          'message' in errorPayload.detail &&
          typeof errorPayload.detail.message === 'string'
        ) {
          message = errorPayload.detail.message
        }
      } catch {
        // Some development server errors do not return JSON.
      }
      throw new Error(message)
    }

    const payload = (await response.json()) as T
    publishDebugEvent({
      message: `${method} ${path} 成功`,
      method,
      path,
      status: response.status,
    })
    return payload
  } catch (error) {
    publishDebugEvent({
      message: `${method} ${path} 失败`,
      method,
      path,
      status: responseStatus,
    })
    throw error
  }
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson('/api/health', { signal })
}

export function getAiStatus(signal?: AbortSignal): Promise<AiStatusResponse> {
  return requestJson('/api/ai/status', { signal })
}

export function getVoteWorkflowStatus(
  signal?: AbortSignal,
): Promise<VoteWorkflowStatusResponse> {
  return requestJson('/api/ai/vote/status', { signal })
}

export function sendAiChat(
  gameId: number,
  targetGameCharacterId: number,
  content: string,
): Promise<AiChatResponse> {
  return requestJson(`/api/games/${gameId}/ai-chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_game_character_id: targetGameCharacterId,
      content,
    }),
  })
}

export function sendPublicTurn(
  gameId: number,
  content: string,
): Promise<PublicTurnResponse> {
  return requestJson(`/api/games/${gameId}/public-turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
}

export function getPublicMessages(gameId: number): Promise<MessageRead[]> {
  return requestJson(`/api/games/${gameId}/public-messages`)
}

export function requestAiStep(gameId: number): Promise<AiStepResponse> {
  return requestJson(`/api/games/${gameId}/ai-step`, { method: 'POST' })
}

export function getScripts(signal?: AbortSignal): Promise<ScriptSummary[]> {
  return requestJson('/api/scripts', { signal })
}

export function getGames(signal?: AbortSignal): Promise<GameResponse[]> {
  return requestJson('/api/games', { signal })
}

export function createGame(scriptId: number): Promise<GameResponse> {
  return requestJson('/api/games', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script_id: scriptId }),
  })
}

export function getGame(gameId: number): Promise<GameResponse> {
  return requestJson(`/api/games/${gameId}`)
}

export function getGameState(gameId: number): Promise<GameStateResponse> {
  return requestJson(`/api/games/${gameId}/state`)
}

export function getGameFlow(gameId: number): Promise<GameFlowState> {
  return requestJson(`/api/games/${gameId}/flow`)
}

export function getGameRuntime(gameId: number): Promise<GameRuntimeStatus> {
  return requestJson(`/api/games/${gameId}/runtime`)
}

export function startGameRuntime(gameId: number): Promise<GameRuntimeStatus> {
  return requestJson(`/api/games/${gameId}/runtime/start`, { method: 'POST' })
}

export function pauseGameRuntime(gameId: number): Promise<GameRuntimeStatus> {
  return requestJson(`/api/games/${gameId}/runtime/pause`, { method: 'POST' })
}

export function tickGameRuntime(gameId: number): Promise<RuntimeStepResult> {
  return requestJson(`/api/games/${gameId}/runtime/tick`, { method: 'POST' })
}

export function acknowledgeRuntimePhase(
  gameId: number,
): Promise<PhaseAcknowledgement> {
  return requestJson(`/api/games/${gameId}/runtime/acknowledge-phase`, {
    method: 'POST',
  })
}

export function markRuntimeReady(
  gameId: number,
): Promise<RuntimeReadyResponse> {
  return requestJson(`/api/games/${gameId}/runtime/ready`, { method: 'POST' })
}

export function submitGameVote(
  gameId: number,
  voterGameCharacterId: number,
  targetGameCharacterId: number,
): Promise<VoteRead> {
  return requestJson(`/api/games/${gameId}/votes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      voter_game_character_id: voterGameCharacterId,
      target_game_character_id: targetGameCharacterId,
    }),
  })
}

export function getGameVoteResult(gameId: number): Promise<VoteResult> {
  return requestJson(`/api/games/${gameId}/votes/result`)
}

export function getGameVoteStatus(gameId: number): Promise<GameVoteStatus> {
  return requestJson(`/api/games/${gameId}/vote/status`)
}

export function getGameEnding(gameId: number): Promise<GameEnding> {
  return requestJson(`/api/games/${gameId}/ending`)
}

export function getGameReplay(gameId: number): Promise<GameReplay> {
  return requestJson(`/api/games/${gameId}/replay`)
}

export function getDirectorStatus(
  signal?: AbortSignal,
): Promise<DirectorStatusResponse> {
  return requestJson('/api/director/status', { signal })
}

export function getWriterStatus(
  signal?: AbortSignal,
): Promise<WriterStatusResponse> {
  return requestJson('/api/writer/status', { signal })
}

export function getScriptQualityStatus(
  signal?: AbortSignal,
): Promise<ScriptQualityStatusResponse> {
  return requestJson('/api/writer/quality/status', { signal })
}

export function createWriterDraft(
  request: WriterCreateRequest,
): Promise<WriterDraft> {
  return requestJson('/api/writer/drafts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function getWriterDraft(draftId: number): Promise<WriterDraft> {
  return requestJson(`/api/writer/drafts/${draftId}`)
}

export function generateWriterBlueprint(draftId: number): Promise<WriterDraft> {
  return requestJson(`/api/writer/drafts/${draftId}/generate-blueprint`, {
    method: 'POST',
  })
}

export function generateWriterChapterPack(
  draftId: number,
  phase: WriterPhase,
): Promise<WriterDraft> {
  return requestJson(
    `/api/writer/drafts/${draftId}/generate-chapter-pack/${phase}`,
    { method: 'POST' },
  )
}

export function reviewWriterDraft(draftId: number): Promise<ScriptReviewRun> {
  return requestJson('/api/writer/drafts/' + draftId + '/review', {
    method: 'POST',
  })
}

export function getWriterDraftReviews(
  draftId: number,
): Promise<ScriptReviewRun[]> {
  return requestJson('/api/writer/drafts/' + draftId + '/reviews')
}

export function reviseWriterDraft(
  draftId: number,
  phase: WriterPhase,
): Promise<ScriptRevisionResponse> {
  return requestJson('/api/writer/drafts/' + draftId + '/revise/' + phase, {
    method: 'POST',
  })
}

export function getWriterDraftRevisions(
  draftId: number,
): Promise<ScriptRevisionRecord[]> {
  return requestJson('/api/writer/drafts/' + draftId + '/revisions')
}

export function approveWriterDraft(
  draftId: number,
  reviewRunId: number,
  acceptedMediumIssueIndexes: number[],
): Promise<ScriptApprovalResponse> {
  return requestJson('/api/writer/drafts/' + draftId + '/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      review_run_id: reviewRunId,
      accepted_medium_issue_indexes: acceptedMediumIssueIndexes,
    }),
  })
}

export function publishWriterDraft(
  draftId: number,
): Promise<ScriptPublicationResponse> {
  return requestJson('/api/writer/drafts/' + draftId + '/publish', {
    method: 'POST',
  })
}

export function getWriterDraftPublication(
  draftId: number,
): Promise<ScriptPublicationResponse> {
  return requestJson('/api/writer/drafts/' + draftId + '/publication')
}

export function analyzeGameSituation(
  gameId: number,
): Promise<DirectorRecommendationRecord> {
  return requestJson(`/api/games/${gameId}/director/analyze`, {
    method: 'POST',
  })
}

export function applyDirectorRecommendation(
  gameId: number,
  recommendationId: number,
): Promise<DirectorApplyResult> {
  return requestJson(
    `/api/games/${gameId}/director/recommendations/${recommendationId}/apply`,
    { method: 'POST' },
  )
}

export function startGame(gameId: number): Promise<GameStateResponse> {
  return requestJson(`/api/games/${gameId}/start`, { method: 'POST' })
}

export function advanceGamePhase(gameId: number): Promise<GameStateResponse> {
  return requestJson(`/api/games/${gameId}/advance-phase`, { method: 'POST' })
}

export function getInvestigationLocations(
  gameId: number,
): Promise<InvestigationLocationsResponse> {
  return requestJson(`/api/games/${gameId}/investigation/locations`)
}

export function searchInvestigationLocation(
  gameId: number,
  location: string,
): Promise<InvestigationSearchResponse> {
  return requestJson(`/api/games/${gameId}/investigation/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ location }),
  })
}

export function getMyClues(gameId: number): Promise<MyClueState> {
  return requestJson(`/api/games/${gameId}/me/clues`)
}

export function getPublicClues(
  gameId: number,
): Promise<{ game_id: number; clues: ClueEvidence[] }> {
  return requestJson(`/api/games/${gameId}/clues/public`)
}

export function getClueEvents(gameId: number): Promise<ClueHistoryEvent[]> {
  return requestJson(`/api/games/${gameId}/clues/events`)
}

export function shareClue(
  gameId: number,
  payload: {
    clue_id: number
    visibility: 'private' | 'public'
    target_game_character_id: number | null
    client_request_id: string
  },
): Promise<ClueDisclosureResponse> {
  return requestJson(`/api/games/${gameId}/clues/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getSelectableCharacters(
  gameId: number,
): Promise<SelectableCharacter[]> {
  return requestJson(`/api/games/${gameId}/characters/selectable`)
}

export function selectCharacter(
  gameId: number,
  gameCharacterId: number,
): Promise<GameResponse> {
  return requestJson(`/api/games/${gameId}/select-character`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game_character_id: gameCharacterId }),
  })
}

export function getMyCharacter(gameId: number): Promise<MyCharacterCard> {
  return requestJson(`/api/games/${gameId}/me/character`)
}

export function getPublicStory(gameId: number): Promise<StoryChapterRead[]> {
  return requestJson(`/api/games/${gameId}/story/public`)
}

export function getMyStory(gameId: number): Promise<StoryChapterRead[]> {
  return requestJson(`/api/games/${gameId}/me/story`)
}

export function acknowledgeIntro(
  gameId: number,
): Promise<IntroAcknowledgementResponse> {
  return requestJson(`/api/games/${gameId}/me/acknowledge-intro`, {
    method: 'POST',
  })
}

export function getCharacterContext(
  gameId: number,
  gameCharacterId: number,
): Promise<CharacterContext> {
  return requestJson(
    `/api/games/${gameId}/characters/${gameCharacterId}/context`,
  )
}

export function getCharacterThoughts(
  gameId: number,
  gameCharacterId: number,
): Promise<CharacterDebugState> {
  return requestJson(
    `/api/games/${gameId}/characters/${gameCharacterId}/thoughts`,
  )
}
