import { useEffect, useState } from 'react'

import {
  createGame,
  getGame,
  getScripts,
  type GameResponse,
  type ScriptSummary,
} from './api'

interface DevelopmentPageProps {
  onBack: () => void
}

function DevelopmentPage({ onBack }: DevelopmentPageProps) {
  const [scripts, setScripts] = useState<ScriptSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [game, setGame] = useState<GameResponse | null>(null)
  const [creatingScriptId, setCreatingScriptId] = useState<number | null>(null)
  const [gameError, setGameError] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    getScripts(controller.signal)
      .then(setScripts)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setListError(error instanceof Error ? error.message : '读取剧本失败')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [])

  async function handleCreateGame(scriptId: number) {
    setCreatingScriptId(scriptId)
    setGameError('')

    try {
      const created = await createGame(scriptId)
      setGame(await getGame(created.id))
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '创建游戏失败')
    } finally {
      setCreatingScriptId(null)
    }
  }

  return (
    <main className="page-shell dev-shell">
      <header className="topbar">
        <a className="brand" href="#home" onClick={onBack}>
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>AI MURDER MYSTERY</span>
        </a>
        <button className="back-link" type="button" onClick={onBack}>
          返回首页
        </button>
      </header>

      <section className="dev-intro">
        <p className="eyebrow"><span /> PHASE 01 / DEVELOPMENT</p>
        <h1>剧本数据验证</h1>
        <p className="description">
          查看本地测试剧本，启动一局游戏，并确认运行角色与控制类型。
        </p>
      </section>

      <section className="dev-grid" aria-label="开发数据验证">
        <div className="dev-panel">
          <div className="dev-panel-heading">
            <div>
              <p className="eyebrow">SCRIPT LIBRARY</p>
              <h2>可用剧本</h2>
            </div>
            <span className="record-count">{scripts.length} RECORDS</span>
          </div>

          {loading && <p className="dev-message">正在读取剧本…</p>}
          {!loading && listError && (
            <p className="dev-message error-message" role="alert">{listError}</p>
          )}
          {!loading && !listError && scripts.length === 0 && (
            <p className="dev-message">
              尚无剧本。请先在 backend 目录运行开发 seed 命令。
            </p>
          )}

          <div className="script-list">
            {scripts.map((script) => (
              <article className="script-row" key={script.id}>
                <div className="script-copy">
                  <div className="script-title-line">
                    <h3>{script.title}</h3>
                    <span className={`status-tag status-${script.status}`}>
                      {script.status === 'ready' ? 'READY' : 'DRAFT'}
                    </span>
                  </div>
                  <p>{script.summary || script.theme || '暂无简介'}</p>
                </div>
                <button
                  className="action-button"
                  type="button"
                  disabled={script.status !== 'ready' || creatingScriptId !== null}
                  onClick={() => handleCreateGame(script.id)}
                >
                  {creatingScriptId === script.id ? '创建中…' : '创建游戏'}
                </button>
              </article>
            ))}
          </div>
        </div>

        <div className="dev-panel session-panel">
          <div className="dev-panel-heading">
            <div>
              <p className="eyebrow">GAME SESSION</p>
              <h2>运行状态</h2>
            </div>
            {game && <span className="record-count">SESSION #{game.id}</span>}
          </div>

          {gameError && <p className="dev-message error-message" role="alert">{gameError}</p>}
          {!game && !gameError && (
            <p className="dev-message">选择一个 READY 剧本以创建游戏。</p>
          )}
          {game && (
            <>
              <div className="session-meta">
                <span>阶段 <strong>{game.current_phase}</strong></span>
                <span>状态 <strong>{game.status}</strong></span>
              </div>
              <ol className="game-character-list">
                {game.game_characters.map((character, index) => (
                  <li key={character.id}>
                    <span className="character-index">0{index + 1}</span>
                    <span className="character-name">{character.character.name}</span>
                    <span className={`controller-tag controller-${character.controller_type}`}>
                      {character.controller_type.toUpperCase()}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      </section>

      <footer className="footer">
        <span>仅用于验证核心数据模型与 API</span>
        <span className="footer-mark">PHASE 01 <i /> LOCAL</span>
      </footer>
    </main>
  )
}

export default DevelopmentPage
