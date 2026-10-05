export interface HealthResponse {
  status: string
  app: string
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

export interface GameResponse {
  id: number
  script_id: number
  status: string
  current_phase: string
  created_at: string
  started_at: string | null
  ended_at: string | null
  game_characters: GameCharacterSummary[]
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
      throw new Error(`后端返回 HTTP ${response.status}`)
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
