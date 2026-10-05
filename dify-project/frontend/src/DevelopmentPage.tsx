import { useEffect, useState } from 'react'

import {
  createGame,
  getCharacterContext,
  getGame,
  getGames,
  getMyCharacter,
  getScripts,
  getSelectableCharacters,
  selectCharacter,
  type CharacterContext,
  type GameResponse,
  type MyCharacterCard,
  type ScriptSummary,
  type SelectableCharacter,
} from './api'

interface DevelopmentPageProps {
  onBack: () => void
}

function DevelopmentPage({ onBack }: DevelopmentPageProps) {
  const [scripts, setScripts] = useState<ScriptSummary[]>([])
  const [games, setGames] = useState<GameResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [game, setGame] = useState<GameResponse | null>(null)
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null)
  const [selectableCharacters, setSelectableCharacters] = useState<
    SelectableCharacter[]
  >([])
  const [myCharacter, setMyCharacter] = useState<MyCharacterCard | null>(null)
  const [creatingScriptId, setCreatingScriptId] = useState<number | null>(null)
  const [selectingCharacterId, setSelectingCharacterId] = useState<
    number | null
  >(null)
  const [gameError, setGameError] = useState('')
  const [contextCharacterId, setContextCharacterId] = useState<number | null>(
    null,
  )
  const [context, setContext] = useState<CharacterContext | null>(null)
  const [contextLoading, setContextLoading] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    Promise.all([getScripts(controller.signal), getGames(controller.signal)])
      .then(([loadedScripts, loadedGames]) => {
        setScripts(loadedScripts)
        setGames(loadedGames)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setListError(
            error instanceof Error ? error.message : '读取开发数据失败',
          )
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [])

  async function loadGameSession(gameId: number) {
    setGameError('')
    setContext(null)

    try {
      const loadedGame = await getGame(gameId)
      setGame(loadedGame)
      setSelectedGameId(gameId)
      setContextCharacterId(loadedGame.game_characters[0]?.id ?? null)

      if (loadedGame.status === 'waiting_for_character_selection') {
        setMyCharacter(null)
        setSelectableCharacters(await getSelectableCharacters(gameId))
      } else {
        setSelectableCharacters([])
        try {
          setMyCharacter(await getMyCharacter(gameId))
        } catch {
          setMyCharacter(null)
        }
      }
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '读取游戏失败')
    }
  }

  async function handleCreateGame(scriptId: number) {
    setCreatingScriptId(scriptId)
    setGameError('')

    try {
      const created = await createGame(scriptId)
      setGames(await getGames())
      await loadGameSession(created.id)
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '创建游戏失败')
    } finally {
      setCreatingScriptId(null)
    }
  }

  async function handleSelectCharacter(gameCharacterId: number) {
    if (selectedGameId === null) return

    setSelectingCharacterId(gameCharacterId)
    setGameError('')
    try {
      await selectCharacter(selectedGameId, gameCharacterId)
      await loadGameSession(selectedGameId)
      setGames(await getGames())
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '角色选择失败')
    } finally {
      setSelectingCharacterId(null)
    }
  }

  async function handleLoadContext() {
    if (selectedGameId === null || contextCharacterId === null) return

    setContextLoading(true)
    setGameError('')
    try {
      setContext(await getCharacterContext(selectedGameId, contextCharacterId))
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '读取 Context 失败')
    } finally {
      setContextLoading(false)
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
        <p className="eyebrow">
          <span /> PHASE 02 / DEVELOPMENT DEBUG
        </p>
        <h1>角色与信息边界验证</h1>
        <p className="description">
          选择测试游戏和公开角色卡，验证真人分配、私人角色卡与授权上下文。
        </p>
      </section>

      {listError && (
        <p className="dev-message error-message" role="alert">
          {listError}
        </p>
      )}
      {gameError && (
        <p className="dev-message error-message" role="alert">
          {gameError}
        </p>
      )}

      <section className="dev-grid" aria-label="开发数据验证">
        <div className="dev-panel">
          <div className="dev-panel-heading">
            <div>
              <p className="eyebrow">SCRIPT LIBRARY</p>
              <h2>开发剧本</h2>
            </div>
            <span className="record-count">{scripts.length} RECORDS</span>
          </div>

          {loading && <p className="dev-message">正在读取开发数据…</p>}
          {!loading && scripts.length === 0 && !listError && (
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
                  disabled={
                    script.status !== 'ready' || creatingScriptId !== null
                  }
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
              <h2>角色选择</h2>
            </div>
            {game && <span className="record-count">SESSION #{game.id}</span>}
          </div>

          <label className="field-label" htmlFor="game-session-select">
            选择一局测试游戏
          </label>
          <select
            className="dev-select"
            id="game-session-select"
            value={selectedGameId ?? ''}
            onChange={(event) => {
              const gameId = Number(event.target.value)
              if (gameId) void loadGameSession(gameId)
            }}
          >
            <option value="">选择 GameSession</option>
            {games.map((item) => (
              <option key={item.id} value={item.id}>
                #{item.id} · {item.status} · Script #{item.script_id}
              </option>
            ))}
          </select>

          {game && (
            <div className="session-meta">
              <span>
                阶段 <strong>{game.current_phase}</strong>
              </span>
              <span>
                状态 <strong>{game.status}</strong>
              </span>
            </div>
          )}
          {!game && !gameError && (
            <p className="dev-message">
              选择一局游戏，或从左侧 READY 剧本创建新游戏。
            </p>
          )}

          {game?.status === 'waiting_for_character_selection' && (
            <div className="role-card-list">
              <p className="section-caption">公开角色卡 · 选择后将锁定分配</p>
              {selectableCharacters.map((character) => (
                <article
                  className="role-card"
                  key={character.game_character_id}
                >
                  <div className="script-title-line">
                    <h3>{character.name}</h3>
                    <span className="record-count">
                      {character.identity} ·{' '}
                      {character.age === null
                        ? '年龄未设定'
                        : `${character.age} 岁`}
                    </span>
                  </div>
                  <p>{character.public_background}</p>
                  <p className="role-card-traits">
                    {character.personality} · {character.speaking_style}
                  </p>
                  <button
                    className="action-button"
                    type="button"
                    disabled={selectingCharacterId !== null}
                    onClick={() =>
                      handleSelectCharacter(character.game_character_id)
                    }
                  >
                    {selectingCharacterId === character.game_character_id
                      ? '分配中…'
                      : '选择此角色'}
                  </button>
                </article>
              ))}
            </div>
          )}

          {game && game.status !== 'waiting_for_character_selection' && (
            <ol className="game-character-list">
              {game.game_characters.map((character, index) => (
                <li key={character.id}>
                  <span className="character-index">0{index + 1}</span>
                  <span className="character-name">
                    {character.character.name}
                  </span>
                  <span
                    className={`controller-tag controller-${character.controller_type ?? 'unassigned'}`}
                  >
                    {(character.controller_type ?? 'UNASSIGNED').toUpperCase()}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>

      {myCharacter && (
        <section className="dev-panel detail-panel" aria-label="真人角色卡">
          <div className="dev-panel-heading">
            <div>
              <p className="eyebrow">HUMAN ROLE CARD</p>
              <h2>{myCharacter.name} · 私人角色卡</h2>
            </div>
          </div>
          <dl className="private-card-grid">
            <div>
              <dt>身份</dt>
              <dd>{myCharacter.identity}</dd>
            </div>
            <div>
              <dt>年龄</dt>
              <dd>
                {myCharacter.age === null ? '未设定' : `${myCharacter.age} 岁`}
              </dd>
            </div>
            <div>
              <dt>公开背景</dt>
              <dd>{myCharacter.public_background}</dd>
            </div>
            <div>
              <dt>私人背景</dt>
              <dd>{myCharacter.private_background}</dd>
            </div>
            <div>
              <dt>性格与说话方式</dt>
              <dd>
                {myCharacter.personality} · {myCharacter.speaking_style}
              </dd>
            </div>
            <div>
              <dt>个人目标</dt>
              <dd>{myCharacter.personal_goal}</dd>
            </div>
          </dl>
          <p className="debug-note">
            当前通过 GameSession 中唯一的 HUMAN 角色识别玩家；尚未接入登录认证。
          </p>
        </section>
      )}

      {game && game.game_characters.length > 0 && (
        <section className="dev-panel detail-panel" aria-label="开发上下文调试">
          <div className="dev-panel-heading">
            <div>
              <p className="eyebrow">DEVELOPMENT ONLY</p>
              <h2>Character Context Debug</h2>
            </div>
          </div>
          <div className="context-controls">
            <label className="field-label" htmlFor="context-character-select">
              选择运行角色
            </label>
            <select
              className="dev-select"
              id="context-character-select"
              value={contextCharacterId ?? ''}
              onChange={(event) =>
                setContextCharacterId(Number(event.target.value))
              }
            >
              {game.game_characters.map((character) => (
                <option key={character.id} value={character.id}>
                  {character.character.name} ·{' '}
                  {character.controller_type ?? 'unassigned'}
                </option>
              ))}
            </select>
            <button
              className="action-button"
              type="button"
              disabled={contextLoading || contextCharacterId === null}
              onClick={handleLoadContext}
            >
              {contextLoading ? '读取中…' : '查看授权 Context'}
            </button>
          </div>
          {context && (
            <pre className="context-viewer">
              {JSON.stringify(context, null, 2)}
            </pre>
          )}
        </section>
      )}

      <footer className="footer">
        <span>仅用于验证角色分配与信息边界</span>
        <span className="footer-mark">
          PHASE 02 <i /> DEVELOPMENT DEBUG
        </span>
      </footer>
    </main>
  )
}

export default DevelopmentPage
