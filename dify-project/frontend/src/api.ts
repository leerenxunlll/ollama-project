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
  controller_type: 'human' | 'ai'
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
