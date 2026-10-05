import { useEffect, useState, type FormEvent } from 'react'

import {
  createGame,
  advanceGamePhase,
  getCharacterContext,
  getAiStatus,
  getGame,
  getGameState,
  getGames,
  getInvestigationLocations,
  getMyCharacter,
  getScripts,
  getSelectableCharacters,
  selectCharacter,
  searchInvestigationLocation,
  sendAiChat,
  startGame,
  type AiChatResponse,
  type AiStatusResponse,
  type CharacterContext,
  type GameResponse,
  type GameStateResponse,
  type InvestigationSearchResponse,
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
  const [gameState, setGameState] = useState<GameStateResponse | null>(null)
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
  const [actionLoading, setActionLoading] = useState('')
  const [locations, setLocations] = useState<string[]>([])
  const [selectedLocation, setSelectedLocation] = useState('')
  const [searchResult, setSearchResult] =
    useState<InvestigationSearchResponse | null>(null)
  const [aiStatus, setAiStatus] = useState<AiStatusResponse | null>(null)
  const [aiStatusError, setAiStatusError] = useState('')
  const [aiChatGameId, setAiChatGameId] = useState<number | null>(null)
  const [aiTargetCharacterId, setAiTargetCharacterId] = useState<number | null>(
    null,
  )
  const [aiChatContent, setAiChatContent] = useState('')
  const [aiChatResponse, setAiChatResponse] = useState<AiChatResponse | null>(
    null,
  )
  const [aiChatError, setAiChatError] = useState('')
  const [aiChatLoading, setAiChatLoading] = useState(false)

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

    getAiStatus(controller.signal)
      .then((status) => setAiStatus(status))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setAiStatusError(
            error instanceof Error ? error.message : '读取 AI 配置状态失败',
          )
        }
      })

    return () => controller.abort()
  }, [])

  const inProgressGames = games.filter((item) => item.status === 'in_progress')
  const aiChatGame = inProgressGames.find((item) => item.id === aiChatGameId)
  const aiCharacters =
    aiChatGame?.game_characters.filter(
      (character) => character.controller_type === 'ai',
    ) ?? []
  const selectedAiTargetId = aiCharacters.some(
    (character) => character.id === aiTargetCharacterId,
  )
    ? aiTargetCharacterId
    : (aiCharacters[0]?.id ?? null)

  async function loadGameSession(gameId: number) {
    setGameError('')
    setContext(null)
    setSearchResult(null)
    setLocations([])
    setSelectedLocation('')

    try {
      const [loadedGame, loadedState] = await Promise.all([
        getGame(gameId),
        getGameState(gameId),
      ])
      setGame(loadedGame)
      setGameState(loadedState)
      setSelectedGameId(gameId)

      if (loadedGame.status === 'waiting_for_character_selection') {
        setMyCharacter(null)
        setContextCharacterId(loadedGame.game_characters[0]?.id ?? null)
        setSelectableCharacters(await getSelectableCharacters(gameId))
      } else {
        setSelectableCharacters([])
        let playerCharacter: MyCharacterCard | null = null
        try {
          playerCharacter = await getMyCharacter(gameId)
        } catch {
          playerCharacter = null
        }
        setMyCharacter(playerCharacter)
        setContextCharacterId(
          playerCharacter?.game_character_id ??
            loadedGame.game_characters[0]?.id ??
            null,
        )
        if (loadedState.can_investigate) {
          const available = await getInvestigationLocations(gameId)
          setLocations(available.locations)
          setSelectedLocation(available.locations[0] ?? '')
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

  async function handleStartGame() {
    if (selectedGameId === null) return

    setActionLoading('start')
    setGameError('')
    try {
      await startGame(selectedGameId)
      await loadGameSession(selectedGameId)
      setGames(await getGames())
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '开始游戏失败')
    } finally {
      setActionLoading('')
    }
  }

  async function handleAdvancePhase() {
    if (selectedGameId === null) return

    setActionLoading('advance')
    setGameError('')
    try {
      await advanceGamePhase(selectedGameId)
      await loadGameSession(selectedGameId)
      setGames(await getGames())
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '推进阶段失败')
    } finally {
      setActionLoading('')
    }
  }

  async function handleSearch() {
    if (
      selectedGameId === null ||
      myCharacter === null ||
      selectedLocation === ''
    ) {
      return
    }

    setActionLoading('search')
    setGameError('')
    setContext(null)
    try {
      const result = await searchInvestigationLocation(
        selectedGameId,
        myCharacter.game_character_id,
        selectedLocation,
      )
      setSearchResult(result)
      if (contextCharacterId === myCharacter.game_character_id) {
        setContext(
          await getCharacterContext(
            selectedGameId,
            myCharacter.game_character_id,
          ),
        )
      }
    } catch (error) {
      setGameError(error instanceof Error ? error.message : '搜证失败')
    } finally {
      setActionLoading('')
    }
  }

  async function handleAiChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (
      aiChatGameId === null ||
      selectedAiTargetId === null ||
      aiChatContent.trim() === ''
    ) {
      return
    }

    setAiChatLoading(true)
    setAiChatError('')
    setAiChatResponse(null)
    try {
      setAiChatResponse(
        await sendAiChat(
          aiChatGameId,
          selectedAiTargetId,
          aiChatContent.trim(),
        ),
      )
      setAiChatContent('')
    } catch (error) {
      setAiChatError(error instanceof Error ? error.message : 'AI 对话失败')
    } finally {
      setAiChatLoading(false)
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
          <span /> PHASE 04 / CHARACTER CHAT DEBUG
        </p>
        <h1>游戏规则与 AI 对话验证</h1>
        <p className="description">
          验证确定性游戏规则、角色信息边界与单个 AI 角色私聊链路。
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
                阶段{' '}
                <strong>
                  {gameState?.current_phase ?? game.current_phase}
                </strong>
              </span>
              <span>
                状态 <strong>{game.status}</strong>
              </span>
              {gameState && (
                <span>
                  下一阶段 <strong>{gameState.next_phase ?? '无'}</strong>
                </span>
              )}
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

          {game?.status === 'ready' && (
            <div className="game-action-row">
              <p className="section-caption">
                角色分配已锁定，可以开始这一局。
              </p>
              <button
                className="action-button"
                type="button"
                disabled={actionLoading !== ''}
                onClick={handleStartGame}
              >
                {actionLoading === 'start'
                  ? '开始中…'
                  : 'Start Game · 开始游戏'}
              </button>
            </div>
          )}

          {gameState?.status === 'in_progress' && (
            <div className="game-action-row">
              <p className="section-caption">
                当前阶段：{gameState.current_phase}
                {gameState.next_phase
                  ? ` · 下一阶段：${gameState.next_phase}`
                  : ' · 已到最后阶段'}
              </p>
              {gameState.next_phase && (
                <button
                  className="action-button"
                  type="button"
                  disabled={actionLoading !== ''}
                  onClick={handleAdvancePhase}
                >
                  {actionLoading === 'advance'
                    ? '推进中…'
                    : 'Advance Phase · 推进阶段'}
                </button>
              )}
            </div>
          )}

          {gameState?.can_investigate && (
            <div className="investigation-controls">
              <p className="eyebrow">DETERMINISTIC INVESTIGATION</p>
              <p className="section-caption">
                搜证角色：{myCharacter?.name ?? '尚未选择真人角色'}
              </p>
              {locations.length > 0 ? (
                <div className="investigation-action">
                  <label
                    className="field-label"
                    htmlFor="investigation-location"
                  >
                    选择地点
                  </label>
                  <select
                    className="dev-select"
                    id="investigation-location"
                    value={selectedLocation}
                    onChange={(event) =>
                      setSelectedLocation(event.target.value)
                    }
                  >
                    {locations.map((location) => (
                      <option key={location} value={location}>
                        {location}
                      </option>
                    ))}
                  </select>
                  <button
                    className="action-button"
                    type="button"
                    disabled={
                      actionLoading !== '' ||
                      myCharacter === null ||
                      selectedLocation === ''
                    }
                    onClick={handleSearch}
                  >
                    {actionLoading === 'search'
                      ? '搜证中…'
                      : 'Search · 搜索地点'}
                  </button>
                </div>
              ) : (
                <p className="dev-message">当前调查幕没有预设线索地点。</p>
              )}
              {searchResult && (
                <div className="search-result" role="status">
                  {searchResult.found && searchResult.clue ? (
                    <>
                      <strong>发现线索：{searchResult.clue.name}</strong>
                      <p>{searchResult.clue.description}</p>
                    </>
                  ) : (
                    <p>这个地点没有新的线索。</p>
                  )}
                </div>
              )}
            </div>
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

      <section className="dev-panel detail-panel" aria-label="AI 角色对话调试">
        <div className="dev-panel-heading">
          <div>
            <p className="eyebrow">DEVELOPMENT ONLY</p>
            <h2>AI Character Chat Debug</h2>
          </div>
          <span
            className={`ai-status-pill ${
              aiStatusError
                ? 'is-error'
                : aiStatus === null
                  ? 'is-loading'
                  : aiStatus.configured
                    ? 'is-ready'
                    : 'is-disabled'
            }`}
            role="status"
          >
            {aiStatusError
              ? '状态读取失败'
              : aiStatus === null
                ? '正在检查 AI 配置…'
                : aiStatus.configured
                  ? 'AI 已配置'
                  : 'AI 未配置'}
          </span>
        </div>

        {aiStatusError && (
          <p className="dev-message error-message" role="alert">
            {aiStatusError}
          </p>
        )}

        <form className="ai-chat-form" onSubmit={handleAiChat}>
          <div className="ai-chat-selectors">
            <div>
              <label className="field-label" htmlFor="ai-chat-game-select">
                进行中的 GameSession
              </label>
              <select
                className="dev-select"
                id="ai-chat-game-select"
                value={aiChatGameId ?? ''}
                disabled={inProgressGames.length === 0}
                onChange={(event) => {
                  const gameId = Number(event.target.value)
                  setAiChatGameId(gameId || null)
                  setAiTargetCharacterId(null)
                  setAiChatResponse(null)
                  setAiChatError('')
                }}
              >
                <option value="">
                  {inProgressGames.length === 0
                    ? '没有进行中的游戏'
                    : '选择 GameSession'}
                </option>
                {inProgressGames.map((item) => (
                  <option key={item.id} value={item.id}>
                    #{item.id} · Script #{item.script_id}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="field-label" htmlFor="ai-chat-character-select">
                AI 角色
              </label>
              <select
                className="dev-select"
                id="ai-chat-character-select"
                value={selectedAiTargetId ?? ''}
                disabled={aiCharacters.length === 0}
                onChange={(event) => {
                  setAiTargetCharacterId(Number(event.target.value) || null)
                  setAiChatResponse(null)
                  setAiChatError('')
                }}
              >
                {aiCharacters.length === 0 && (
                  <option value="">先选择有 AI 角色的游戏</option>
                )}
                {aiCharacters.map((character) => (
                  <option key={character.id} value={character.id}>
                    {character.character.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <label className="field-label" htmlFor="ai-chat-content">
            发给角色的话
          </label>
          <textarea
            className="ai-chat-input"
            id="ai-chat-content"
            rows={3}
            value={aiChatContent}
            placeholder="输入一条测试消息…"
            onChange={(event) => setAiChatContent(event.target.value)}
          />
          <div className="ai-chat-submit-row">
            {!aiStatus?.configured && (
              <p className="section-caption">
                配置 Dify 后端密钥后即可发送测试消息。
              </p>
            )}
            <button
              className="action-button"
              type="submit"
              disabled={
                !aiStatus?.configured ||
                aiChatGameId === null ||
                selectedAiTargetId === null ||
                aiChatContent.trim() === '' ||
                aiChatLoading
              }
            >
              {aiChatLoading ? '等待 AI 回复…' : '发送测试消息'}
            </button>
          </div>
        </form>

        {aiChatError && (
          <p className="dev-message error-message" role="alert">
            {aiChatError}
          </p>
        )}
        {aiChatResponse && (
          <div className="ai-chat-result" aria-live="polite">
            <article className="ai-chat-message human-message">
              <span>
                玩家 →{' '}
                {aiCharacters.find((item) => item.id === selectedAiTargetId)
                  ?.character.name ?? 'AI 角色'}
              </span>
              <p>{aiChatResponse.human_message.content}</p>
            </article>
            <article className="ai-chat-message">
              <span>AI 角色回复</span>
              <p>{aiChatResponse.ai_message.content}</p>
            </article>
          </div>
        )}
      </section>

      <footer className="footer">
        <span>仅用于验证角色信息边界与 AI 对话链路</span>
        <span className="footer-mark">
          PHASE 04 <i /> DEVELOPMENT DEBUG
        </span>
      </footer>
    </main>
  )
}

export default DevelopmentPage
