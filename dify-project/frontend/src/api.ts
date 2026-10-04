export interface HealthResponse {
  status: string
  app: string
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/api/health`, { signal })

  if (!response.ok) {
    throw new Error(`后端返回 HTTP ${response.status}`)
  }

  return response.json() as Promise<HealthResponse>
}
