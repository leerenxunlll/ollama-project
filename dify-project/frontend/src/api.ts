export interface HealthResponse {
  status: string
  app: string
}

export interface AiStatusResponse {
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
  created_at: string
  started_at: string | null
  ended_at: string | null
  game_characters: GameCharacterSummary[]
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
  gameCharacterId: number,
  location: string,
): Promise<InvestigationSearchResponse> {
  return requestJson(`/api/games/${gameId}/investigation/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      game_character_id: gameCharacterId,
      location,
    }),
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

export function getCharacterContext(
  gameId: number,
  gameCharacterId: number,
): Promise<CharacterContext> {
  return requestJson(
    `/api/games/${gameId}/characters/${gameCharacterId}/context`,
  )
}
