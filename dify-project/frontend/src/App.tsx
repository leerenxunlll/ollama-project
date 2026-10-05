import { useEffect, useState } from 'react'

import { getHealth, type HealthResponse } from './api'
import DevelopmentPage from './DevelopmentPage'

type ConnectionState = 'loading' | 'success' | 'error'
type PageName = 'home' | 'scripts'

const entrances = [
  { number: '01', title: '创建剧本', symbol: '✳', available: false },
  { number: '02', title: '载入剧本', symbol: '⌑', available: true },
  { number: '03', title: '进入游戏', symbol: '↗', available: false },
]

function App() {
  const [page, setPage] = useState<PageName>('home')
  const [connectionState, setConnectionState] =
    useState<ConnectionState>('loading')
  const [health, setHealth] = useState<HealthResponse | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    getHealth(controller.signal)
      .then((result) => {
        setHealth(result)
        setConnectionState('success')
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setConnectionState('error')
        }
      })

    return () => controller.abort()
  }, [])

  if (page === 'scripts') {
    return <DevelopmentPage onBack={() => setPage('home')} />
  }

  const connectionCopy = {
    loading: { label: '正在连接后端', detail: '请稍候', icon: '◌' },
    success: {
      label: '后端连接正常',
      detail: health?.app ?? 'API 已响应',
      icon: '●',
    },
    error: {
      label: '后端暂不可用',
      detail: '请确认 FastAPI 服务已启动',
      icon: '!',
    },
  }[connectionState]

  return (
    <main className="page-shell">
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />

      <header className="topbar">
        <a className="brand" href="#home" aria-label="AI Murder Mystery 首页">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>AI MURDER MYSTERY</span>
        </a>
        <span className="phase-label">
          PHASE 04 <i /> CHARACTER CHAT
        </span>
      </header>

      <section className="intro" id="home">
        <div className="intro-copy">
          <p className="eyebrow">
            <span /> 一场尚未落幕的悬疑
          </p>
          <h1>
            真相，
            <br />
            <em>藏在每个人心里。</em>
          </h1>
          <p className="description">
            与 AI 角色共赴一场沉浸式剧本杀。聆听每个故事，寻找被掩盖的真相。
          </p>
        </div>

        <aside
          className={`connection-card state-${connectionState}`}
          aria-live="polite"
        >
          <span className="connection-icon" aria-hidden="true">
            {connectionCopy.icon}
          </span>
          <span className="connection-copy">
            <strong>{connectionCopy.label}</strong>
            <small>{connectionCopy.detail}</small>
          </span>
          <span className="connection-pulse" aria-hidden="true" />
        </aside>
      </section>

      <section className="entrances" aria-label="功能入口">
        {entrances.map((entrance) => (
          <button
            className="entrance-card"
            type="button"
            disabled={!entrance.available}
            key={entrance.number}
            onClick={() => setPage('scripts')}
          >
            <span className="entrance-topline">
              <span>{entrance.number} / 03</span>
              <span className="entrance-symbol" aria-hidden="true">
                {entrance.symbol}
              </span>
            </span>
            <span className="entrance-title">{entrance.title}</span>
            <span className="entrance-note">
              {entrance.available ? '开发验证页' : '即将开放'}
            </span>
          </button>
        ))}
      </section>

      <footer className="footer">
        <span>一个关于秘密、选择与真相的故事</span>
        <span className="footer-mark">
          AMM <i /> 2026
        </span>
      </footer>
    </main>
  )
}

export default App
