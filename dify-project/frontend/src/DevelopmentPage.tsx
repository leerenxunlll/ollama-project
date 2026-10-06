import { useEffect, useState, type FormEvent } from 'react'

import {
  advanceGamePhase,
  analyzeGameSituation,
  applyDirectorRecommendation,
  createGame,
  getAiStatus,
  getCharacterContext,
  getCharacterThoughts,
  getDirectorStatus,
  getGame,
  getGameFlow,
  getGames,
  getGameState,
  getGameVoteResult,
  getInvestigationLocations,
  getMyCharacter,
  getPublicMessages,
  getScripts,
  getSelectableCharacters,
  requestAiStep,
  searchInvestigationLocation,
  selectCharacter,
  sendAiChat,
  sendPublicTurn,
  startGame,
  submitGameVote,
  type AiChatResponse,
  type AiStatusResponse,
  type CharacterContext,
  type CharacterDebugState,
  type DirectorApplyResult,
  type DirectorRecommendationRecord,
  type DirectorStatusResponse,
  type GameFlowState,
  type GameResponse,
  type GameStateResponse,
  type InvestigationSearchResponse,
  type MessageRead,
  type MyCharacterCard,
  type PublicTurnResponse,
  type ScriptSummary,
  type SelectableCharacter,
  type VoteResult,
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
  const [characterDebugState, setCharacterDebugState] =
    useState<CharacterDebugState | null>(null)
  const [characterDebugLoading, setCharacterDebugLoading] = useState(false)
  const [characterDebugError, setCharacterDebugError] = useState('')
  const [publicMessage, setPublicMessage] = useState('')
  const [publicMessages, setPublicMessages] = useState<MessageRead[]>([])
  const [publicRoomError, setPublicRoomError] = useState('')
  const [publicRoomLoading, setPublicRoomLoading] = useState('')
  const [publicTurnResult, setPublicTurnResult] =
    useState<PublicTurnResponse | null>(null)
  const [gameFlow, setGameFlow] = useState<GameFlowState | null>(null)
  const [gameFlowError, setGameFlowError] = useState('')
  const [gameFlowLoading, setGameFlowLoading] = useState(false)
  const [gameFlowUpdatedAt, setGameFlowUpdatedAt] = useState(0)
  const [flowClock, setFlowClock] = useState(Date.now())
  const [voteResult, setVoteResult] = useState<VoteResult | null>(null)
  const [voteError, setVoteError] = useState('')
  const [voteLoading, setVoteLoading] = useState(false)
  const [voteSubmitting, setVoteSubmitting] = useState(false)
  const [voteMessage, setVoteMessage] = useState('')
  const [voterGameCharacterId, setVoterGameCharacterId] = useState<
    number | null
  >(null)
  const [targetGameCharacterId, setTargetGameCharacterId] = useState<
    number | null
  >(null)
  const [directorStatus, setDirectorStatus] =
    useState<DirectorStatusResponse | null>(null)
  const [directorStatusError, setDirectorStatusError] = useState('')
  const [directorRecommendation, setDirectorRecommendation] =
    useState<DirectorRecommendationRecord | null>(null)
  const [directorOutcome, setDirectorOutcome] =
    useState<DirectorApplyResult | null>(null)
  const [directorError, setDirectorError] = useState('')
  const [directorLoading, setDirectorLoading] = useState('')

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

    getDirectorStatus(controller.signal)
      .then((status) => setDirectorStatus(status))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setDirectorStatusError(
            error instanceof Error
              ? error.message
              : '读取 Director 配置状态失败',
          )
        }
      })

    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (aiChatGameId === null) {
      setPublicMessages([])
      return
    }

    let active = true
    getPublicMessages(aiChatGameId)
      .then((messages) => {
        if (active) setPublicMessages(messages)
      })
      .catch((error: unknown) => {
        if (active) {
          setPublicRoomError(
            error instanceof Error ? error.message : '读取公共记录失败',
          )
        }
      })

    return () => {
      active = false
    }
  }, [aiChatGameId])

  useEffect(() => {
    if (selectedGameId === null) {
      setGameFlow(null)
      setVoteResult(null)
      return
    }

    let active = true
    const gameId = selectedGameId
    setGameFlow(null)
    setGameFlowError('')
    setGameFlowLoading(true)
    setVoteResult(null)
    setVoteError('')
    setVoteLoading(true)
    setVoteMessage('')
    setDirectorRecommendation(null)
    setDirectorOutcome(null)
    setDirectorError('')

    async function refreshFlow() {
      try {
        const loadedFlow = await getGameFlow(gameId)
        if (active) {
          setGameFlow(loadedFlow)
          setGameFlowUpdatedAt(Date.now())
          setGameFlowError('')
        }
      } catch (error) {
        if (active) {
          setGameFlowError(
            error instanceof Error ? error.message : '读取游戏流程失败',
          )
        }
      } finally {
        if (active) setGameFlowLoading(false)
      }
    }

    async function refreshVotes() {
      try {
        const loadedResult = await getGameVoteResult(gameId)
        if (active) {
          setVoteResult(loadedResult)
          setVoteError('')
        }
      } catch (error) {
        if (active) {
          setVoteError(
            error instanceof Error ? error.message : '读取投票统计失败',
          )
        }
      } finally {
        if (active) setVoteLoading(false)
      }
    }

    void refreshFlow()
    void refreshVotes()
    const intervalId = window.setInterval(() => {
      void refreshFlow()
    }, 5000)

    return () => {
      active = false
      window.clearInterval(intervalId)
    }
  }, [selectedGameId])

  useEffect(() => {
    if (selectedGameId === null) return undefined
    const intervalId = window.setInterval(() => setFlowClock(Date.now()), 1000)
    return () => window.clearInterval(intervalId)
  }, [selectedGameId])

  useEffect(() => {
    const characters = game?.id === selectedGameId ? game.game_characters : []
    setVoterGameCharacterId(characters[0]?.id ?? null)
    setTargetGameCharacterId(characters[1]?.id ?? characters[0]?.id ?? null)
  }, [game?.id, selectedGameId])

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

  const visibleCharacterDebugState =
    characterDebugState?.game_id === aiChatGameId &&
    characterDebugState?.game_character_id === selectedAiTargetId
      ? characterDebugState
      : null
  const selectedGame = game?.id === selectedGameId ? game : null
  const currentGameFlow = gameFlow?.game_id === selectedGameId ? gameFlow : null
  const flowElapsedSeconds = currentGameFlow
    ? currentGameFlow.elapsed_seconds +
      Math.max(0, Math.floor((flowClock - gameFlowUpdatedAt) / 1000))
    : 0
  const flowRemainingSeconds = currentGameFlow
    ? Math.max(
        0,
        currentGameFlow.remaining_seconds -
          Math.max(0, Math.floor((flowClock - gameFlowUpdatedAt) / 1000)),
      )
    : 0
  const selectedVoterGameCharacterId = selectedGame?.game_characters.some(
    (character) => character.id === voterGameCharacterId,
  )
    ? voterGameCharacterId
    : (selectedGame?.game_characters[0]?.id ?? null)
  const selectedTargetGameCharacterId = selectedGame?.game_characters.some(
    (character) => character.id === targetGameCharacterId,
  )
    ? targetGameCharacterId
    : (selectedGame?.game_characters[1]?.id ??
      selectedGame?.game_characters[0]?.id ??
      null)

  function formatDuration(totalSeconds: number): string {
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  }

  async function handleRefreshGameFlow() {
    if (selectedGameId === null) return
    setGameFlowLoading(true)
    setGameFlowError('')
    try {
      setGameFlow(await getGameFlow(selectedGameId))
      setGameFlowUpdatedAt(Date.now())
    } catch (error) {
      setGameFlowError(
        error instanceof Error ? error.message : '读取游戏流程失败',
      )
    } finally {
      setGameFlowLoading(false)
    }
  }

  async function handleRefreshVoteTally() {
    if (selectedGameId === null) return
    setVoteLoading(true)
    setVoteError('')
    try {
      setVoteResult(await getGameVoteResult(selectedGameId))
    } catch (error) {
      setVoteError(error instanceof Error ? error.message : '读取投票统计失败')
    } finally {
      setVoteLoading(false)
    }
  }

  async function handleSubmitDebugVote() {
    if (
      selectedGameId === null ||
      selectedVoterGameCharacterId === null ||
      selectedTargetGameCharacterId === null
    ) {
      return
    }

    setVoteSubmitting(true)
    setVoteError('')
    setVoteMessage('')
    try {
      await submitGameVote(
        selectedGameId,
        selectedVoterGameCharacterId,
        selectedTargetGameCharacterId,
      )
      setVoteMessage('测试投票已提交。')
      await handleRefreshVoteTally()
    } catch (error) {
      setVoteError(error instanceof Error ? error.message : '提交投票失败')
    } finally {
      setVoteSubmitting(false)
    }
  }

  async function handleAnalyzeDirectorSituation() {
    if (selectedGameId === null) return
    setDirectorLoading('analyze')
    setDirectorError('')
    setDirectorOutcome(null)
    try {
      setDirectorRecommendation(await analyzeGameSituation(selectedGameId))
    } catch (error) {
      setDirectorError(
        error instanceof Error ? error.message : 'Director 分析失败',
      )
    } finally {
      setDirectorLoading('')
    }
  }

  async function handleApplyDirectorRecommendation() {
    if (selectedGameId === null || directorRecommendation === null) return
    setDirectorLoading('apply')
    setDirectorError('')
    try {
      const outcome = await applyDirectorRecommendation(
        selectedGameId,
        directorRecommendation.id,
      )
      setDirectorOutcome(outcome)
      setDirectorRecommendation((current) =>
        current === null
          ? null
          : {
              ...current,
              status: outcome.status,
              applied_at:
                outcome.status === 'applied'
                  ? new Date().toISOString()
                  : current.applied_at,
            },
      )
      if (outcome.flow_state) {
        setGameFlow(outcome.flow_state)
        setGameFlowUpdatedAt(Date.now())
      }
    } catch (error) {
      setDirectorError(
        error instanceof Error ? error.message : '应用 Director 建议失败',
      )
    } finally {
      setDirectorLoading('')
    }
  }

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
    setCharacterDebugError('')
    try {
      const response = await sendAiChat(
        aiChatGameId,
        selectedAiTargetId,
        aiChatContent.trim(),
      )
      setAiChatResponse(response)
      setAiChatContent('')
      setCharacterDebugLoading(true)
      try {
        setCharacterDebugState(
          await getCharacterThoughts(aiChatGameId, selectedAiTargetId),
        )
      } catch (error) {
        setCharacterDebugError(
          error instanceof Error ? error.message : '读取角色私有状态失败',
        )
      } finally {
        setCharacterDebugLoading(false)
      }
    } catch (error) {
      setAiChatError(error instanceof Error ? error.message : 'AI 对话失败')
    } finally {
      setAiChatLoading(false)
    }
  }

  async function handlePublicTurn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (aiChatGameId === null || publicMessage.trim() === '') return

    setPublicRoomLoading('public-turn')
    setPublicRoomError('')
    try {
      const response = await sendPublicTurn(aiChatGameId, publicMessage.trim())
      setPublicMessages((messages) => [
        ...messages,
        ...[response.human_message, ...response.ai_responses].filter(
          (message) => message.channel_type === 'public',
        ),
      ])
      setPublicTurnResult(response)
      setPublicMessage('')
    } catch (error) {
      setPublicRoomError(
        error instanceof Error ? error.message : '公共回合失败',
      )
    } finally {
      setPublicRoomLoading('')
    }
  }

  async function handleAiStep() {
    if (aiChatGameId === null) return

    setPublicRoomLoading('ai-step')
    setPublicRoomError('')
    try {
      const response = await requestAiStep(aiChatGameId)
      if (response.ai_message.channel_type === 'public') {
        setPublicMessages((messages) => [...messages, response.ai_message])
      }
    } catch (error) {
      setPublicRoomError(
        error instanceof Error ? error.message : 'AI 主动发言失败',
      )
    } finally {
      setPublicRoomLoading('')
    }
  }

  async function handleLoadCharacterDebug() {
    if (aiChatGameId === null || selectedAiTargetId === null) return

    setCharacterDebugLoading(true)
    setCharacterDebugError('')
    try {
      setCharacterDebugState(
        await getCharacterThoughts(aiChatGameId, selectedAiTargetId),
      )
    } catch (error) {
      setCharacterDebugError(
        error instanceof Error ? error.message : '读取角色私有状态失败',
      )
    } finally {
      setCharacterDebugLoading(false)
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
          <span /> PHASE 07 / GAME FLOW & DIRECTOR DEBUG
        </p>
        <h1>游戏规则与 AI 对话验证</h1>
        <p className="description">验证阶段计时、投票统计与导演建议应用。</p>
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

      <section
        className="dev-panel detail-panel"
        aria-label="游戏流程与投票开发调试"
      >
        <div className="dev-panel-heading">
          <div>
            <p className="eyebrow">DEBUG ONLY · GAME FLOW</p>
            <h2>阶段计时与动作资格</h2>
          </div>
          <button
            className="action-button"
            type="button"
            disabled={selectedGameId === null || gameFlowLoading}
            onClick={handleRefreshGameFlow}
          >
            {gameFlowLoading ? '刷新中…' : '刷新流程状态'}
          </button>
        </div>

        {gameFlowError && (
          <p className="dev-message error-message" role="alert">
            {gameFlowError}
          </p>
        )}
        {!selectedGame && (
          <p className="dev-message">请先在上方选择一局 GameSession。</p>
        )}
        {selectedGame && !currentGameFlow && !gameFlowError && (
          <p className="dev-message">
            {gameFlowLoading ? '正在读取流程状态…' : '暂无流程状态。'}
          </p>
        )}
        {selectedGame && currentGameFlow && (
          <>
            <div className="flow-summary-grid">
              <div className="flow-stat">
                <span>当前阶段</span>
                <strong>{currentGameFlow.current_phase}</strong>
              </div>
              <div className="flow-stat">
                <span>阶段已用时间</span>
                <strong>{formatDuration(flowElapsedSeconds)}</strong>
              </div>
              <div className="flow-stat">
                <span>最低时长剩余</span>
                <strong>{formatDuration(flowRemainingSeconds)}</strong>
              </div>
              <div className="flow-stat">
                <span>阶段状态</span>
                <strong>
                  {currentGameFlow.minimum_time_satisfied
                    ? '已满足最低时长'
                    : `最低 ${formatDuration(currentGameFlow.minimum_duration_seconds)}`}
                </strong>
              </div>
            </div>

            <div className="flow-eligibility" aria-label="当前动作资格">
              <span>动作资格</span>
              {[
                ['搜证', currentGameFlow.can_investigate],
                ['讨论', currentGameFlow.can_discuss],
                ['投票', currentGameFlow.can_vote],
                ['推进阶段', currentGameFlow.can_advance],
                ['游戏结束', currentGameFlow.is_finished],
              ].map(([label, available]) => (
                <span
                  className={`eligibility-tag ${available ? 'is-allowed' : ''}`}
                  key={label as string}
                >
                  {label as string} · {available ? '允许' : '不可用'}
                </span>
              ))}
            </div>

            {currentGameFlow.phase_started_at && (
              <p className="debug-note">
                阶段开始时间：
                {new Date(currentGameFlow.phase_started_at).toLocaleString()}
              </p>
            )}

            <div className="vote-debug-panel">
              <div className="character-debug-heading">
                <div>
                  <p className="eyebrow">DEVELOPMENT VOTE DEBUG</p>
                  <h3>投票提交流程</h3>
                </div>
                <button
                  className="action-button"
                  type="button"
                  disabled={voteLoading}
                  onClick={handleRefreshVoteTally}
                >
                  {voteLoading ? '刷新中…' : '刷新统计'}
                </button>
              </div>

              <div className="vote-controls">
                <div>
                  <label className="field-label" htmlFor="debug-voter-select">
                    投票人（本局任意角色）
                  </label>
                  <select
                    className="dev-select"
                    id="debug-voter-select"
                    value={selectedVoterGameCharacterId ?? ''}
                    onChange={(event) =>
                      setVoterGameCharacterId(
                        Number(event.target.value) || null,
                      )
                    }
                  >
                    {selectedGame.game_characters.map((character) => (
                      <option key={character.id} value={character.id}>
                        {character.character.name} · #{character.id}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="debug-target-select">
                    投票目标
                  </label>
                  <select
                    className="dev-select"
                    id="debug-target-select"
                    value={selectedTargetGameCharacterId ?? ''}
                    onChange={(event) =>
                      setTargetGameCharacterId(
                        Number(event.target.value) || null,
                      )
                    }
                  >
                    {selectedGame.game_characters.map((character) => (
                      <option key={character.id} value={character.id}>
                        {character.character.name} · #{character.id}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  className="action-button"
                  type="button"
                  disabled={
                    !currentGameFlow.can_vote ||
                    selectedVoterGameCharacterId === null ||
                    selectedTargetGameCharacterId === null ||
                    voteSubmitting ||
                    voteResult?.submitted_voter_game_character_ids.includes(
                      selectedVoterGameCharacterId ?? -1,
                    ) === true
                  }
                  onClick={handleSubmitDebugVote}
                >
                  {voteSubmitting ? '提交中…' : '提交测试投票'}
                </button>
              </div>

              <div className="vote-progress-line">
                <span>
                  当前进度：
                  {voteResult?.votes_cast ??
                    currentGameFlow.vote_progress.votes_cast}{' '}
                  /{' '}
                  {voteResult?.total_voters ??
                    currentGameFlow.vote_progress.total_voters}{' '}
                  票
                </span>
                <strong>
                  {(voteResult?.voting_complete ??
                  currentGameFlow.vote_progress.voting_complete)
                    ? '投票完成'
                    : '投票进行中'}
                </strong>
              </div>
              {voteMessage && (
                <p className="dev-message" role="status">
                  {voteMessage}
                </p>
              )}
              {voteError && (
                <p className="dev-message error-message" role="alert">
                  {voteError}
                </p>
              )}
              <div className="vote-tally-list" aria-label="按目标统计票数">
                {selectedGame.game_characters.map((character) => (
                  <div className="vote-tally-row" key={character.id}>
                    <span>
                      {character.character.name} · #{character.id}
                    </span>
                    <strong>
                      {voteResult?.vote_count_by_target[character.id] ?? 0} 票
                    </strong>
                  </div>
                ))}
              </div>
              {voteResult && voteResult.is_tie && (
                <p className="debug-note">当前票数并列。</p>
              )}
              {voteResult?.winner_game_character_id !== null &&
                voteResult?.winner_game_character_id !== undefined && (
                  <p className="debug-note">
                    当前最高票角色：
                    {selectedGame.game_characters.find(
                      (character) =>
                        character.id === voteResult.winner_game_character_id,
                    )?.character.name ??
                      `角色 #${voteResult.winner_game_character_id}`}
                  </p>
                )}
              {!currentGameFlow.can_vote && (
                <p className="debug-note">
                  当前阶段不允许投票；仍可查看投票进度与统计。
                </p>
              )}
            </div>
          </>
        )}
      </section>

      <section
        className="dev-panel detail-panel"
        aria-label="Director 开发调试"
      >
        <div className="dev-panel-heading">
          <div>
            <p className="eyebrow">DEBUG ONLY · DIRECTOR</p>
            <h2>导演建议调试</h2>
          </div>
          <span
            className={`ai-status-pill ${
              directorStatusError
                ? 'is-error'
                : directorStatus === null
                  ? 'is-loading'
                  : directorStatus.configured
                    ? 'is-ready'
                    : 'is-disabled'
            }`}
            role="status"
          >
            {directorStatusError
              ? '状态读取失败'
              : directorStatus === null
                ? '正在检查配置…'
                : directorStatus.configured
                  ? 'Director 已配置'
                  : 'Director 未配置'}
          </span>
        </div>
        {directorStatusError && (
          <p className="dev-message error-message" role="alert">
            {directorStatusError}
          </p>
        )}
        {directorError && (
          <p className="dev-message error-message" role="alert">
            {directorError}
          </p>
        )}
        <div className="director-action-row">
          <p className="section-caption">
            对所选 GameSession 请求一次导演局势分析。
          </p>
          <button
            className="action-button"
            type="button"
            disabled={
              !directorStatus?.configured ||
              selectedGameId === null ||
              directorLoading !== ''
            }
            onClick={handleAnalyzeDirectorSituation}
          >
            {directorLoading === 'analyze'
              ? '分析中…'
              : 'Analyze Situation · 分析局势'}
          </button>
        </div>
        {selectedGameId === null && (
          <p className="dev-message">请先在上方选择一局 GameSession。</p>
        )}
        {directorRecommendation &&
          directorRecommendation.game_session_id === selectedGameId && (
            <article className="director-recommendation">
              <div className="character-debug-heading">
                <div>
                  <p className="eyebrow">
                    RECOMMENDATION #{directorRecommendation.id}
                  </p>
                  <h3>{directorRecommendation.recommended_action}</h3>
                </div>
                <span className="status-tag">
                  {directorRecommendation.status.toUpperCase()}
                </span>
              </div>
              <dl className="director-details">
                <div>
                  <dt>节奏 Pace</dt>
                  <dd>{directorRecommendation.pace}</dd>
                </div>
                <div>
                  <dt>叙事风险 Risk</dt>
                  <dd>{directorRecommendation.narrative_risk}</dd>
                </div>
                <div className="director-reason">
                  <dt>建议理由</dt>
                  <dd>{directorRecommendation.reason}</dd>
                </div>
                <div className="director-references">
                  <dt>引用</dt>
                  <dd>
                    {directorRecommendation.target_game_character_id !== null &&
                      directorRecommendation.target_game_character_id !==
                        undefined && (
                        <span>
                          角色：
                          {selectedGame?.game_characters.find(
                            (character) =>
                              character.id ===
                              directorRecommendation.target_game_character_id,
                          )?.character.name ??
                            `#${directorRecommendation.target_game_character_id}`}
                        </span>
                      )}
                    {directorRecommendation.clue_id !== null &&
                      directorRecommendation.clue_id !== undefined && (
                        <span>线索 #{directorRecommendation.clue_id}</span>
                      )}
                    {directorRecommendation.public_message_id !== null &&
                      directorRecommendation.public_message_id !==
                        undefined && (
                        <span>
                          公共消息 #{directorRecommendation.public_message_id}
                        </span>
                      )}
                    {directorRecommendation.target_game_character_id === null &&
                      directorRecommendation.clue_id === null &&
                      directorRecommendation.public_message_id === null && (
                        <span>无引用</span>
                      )}
                  </dd>
                </div>
              </dl>
              <div className="director-apply-row">
                <span className="debug-note">
                  推荐记录只显示动作摘要、理由与引用标识。
                </span>
                <button
                  className="action-button"
                  type="button"
                  disabled={
                    directorLoading !== '' ||
                    ['applied', 'rejected', 'advisory'].includes(
                      directorRecommendation.status,
                    )
                  }
                  onClick={handleApplyDirectorRecommendation}
                >
                  {directorLoading === 'apply' ? '应用中…' : 'Apply · 应用建议'}
                </button>
              </div>
            </article>
          )}
        {directorOutcome &&
          directorOutcome.recommendation_id === directorRecommendation?.id && (
            <div
              className={`director-outcome outcome-${directorOutcome.status}`}
              role="status"
            >
              <strong>
                {directorOutcome.status === 'applied'
                  ? '已应用'
                  : directorOutcome.status === 'rejected'
                    ? '已拒绝'
                    : '仅供参考'}
              </strong>
              <p>{directorOutcome.reason}</p>
            </div>
          )}
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

      <section
        className="dev-panel detail-panel"
        aria-label="多智能体公共房间调试"
      >
        <div className="dev-panel-heading">
          <div>
            <p className="eyebrow">DEVELOPMENT ONLY</p>
            <h2>Multi-Agent Public Room Debug</h2>
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

        <div className="public-room-controls">
          <div>
            <label className="field-label" htmlFor="public-room-game-select">
              进行中的 GameSession
            </label>
            <select
              className="dev-select"
              id="public-room-game-select"
              value={aiChatGameId ?? ''}
              disabled={inProgressGames.length === 0}
              onChange={(event) => {
                const gameId = Number(event.target.value)
                setAiChatGameId(gameId || null)
                setAiTargetCharacterId(null)
                setPublicMessages([])
                setPublicMessage('')
                setPublicTurnResult(null)
                setPublicRoomError('')
                setAiChatResponse(null)
                setAiChatError('')
                setCharacterDebugState(null)
                setCharacterDebugError('')
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
          <button
            className="action-button"
            type="button"
            disabled={
              !aiStatus?.configured ||
              aiChatGameId === null ||
              publicRoomLoading !== ''
            }
            onClick={handleAiStep}
          >
            {publicRoomLoading === 'ai-step'
              ? '等待 AI 发言…'
              : 'AI Proactive Step · AI 主动发言'}
          </button>
        </div>

        <form className="public-room-form" onSubmit={handlePublicTurn}>
          <label className="field-label" htmlFor="public-room-message">
            公共发言
          </label>
          <textarea
            className="ai-chat-input"
            id="public-room-message"
            rows={3}
            value={publicMessage}
            placeholder="输入所有角色都能听到的话…"
            onChange={(event) => setPublicMessage(event.target.value)}
          />
          <div className="ai-chat-submit-row">
            {!aiStatus?.configured && (
              <p className="section-caption">
                配置 Dify 后端密钥后即可运行公共回合。
              </p>
            )}
            <button
              className="action-button"
              type="submit"
              disabled={
                !aiStatus?.configured ||
                aiChatGameId === null ||
                publicMessage.trim() === '' ||
                publicRoomLoading !== ''
              }
            >
              {publicRoomLoading === 'public-turn'
                ? '公共回合处理中…'
                : '发送 Public Turn · 发送公共回合'}
            </button>
          </div>
        </form>

        {publicRoomError && (
          <p className="dev-message error-message" role="alert">
            {publicRoomError}
          </p>
        )}
        {publicTurnResult?.status === 'partial' && (
          <div className="partial-failure-notice" role="status">
            <strong>本次公共回合部分失败</strong>
            {publicTurnResult.failures.length === 0 ? (
              <p>一个或多个 AI 角色未能回应。</p>
            ) : (
              <ul>
                {publicTurnResult.failures.map((failure) => {
                  const failedCharacter = aiChatGame?.game_characters.find(
                    (character) => character.id === failure.game_character_id,
                  )
                  return (
                    <li key={failure.game_character_id}>
                      {failedCharacter?.character.name ??
                        `角色 #${failure.game_character_id}`}
                      ：{failure.error_type}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )}

        <div className="public-room-transcript" aria-live="polite">
          {publicMessages.length === 0 ? (
            <p className="dev-message">
              {aiChatGameId === null
                ? '选择一局进行中的游戏后即可测试公共对话。'
                : '公共记录将在本页面发送或触发 AI 发言后显示。'}
            </p>
          ) : (
            publicMessages.map((message) => {
              const sender = aiChatGame?.game_characters.find(
                (character) =>
                  character.id === message.sender_game_character_id,
              )
              const senderType =
                sender?.controller_type === 'human'
                  ? 'HUMAN'
                  : sender?.controller_type === 'ai'
                    ? 'AI'
                    : 'SYSTEM'

              return (
                <article
                  className={`ai-chat-message ${
                    senderType === 'HUMAN' ? 'human-message' : ''
                  }`}
                  key={message.id}
                >
                  <span>
                    {senderType} · {sender?.character.name ?? '系统'} · PUBLIC
                  </span>
                  <p>{message.content}</p>
                </article>
              )
            })
          )}
        </div>
      </section>

      <section className="dev-panel detail-panel" aria-label="AI 角色对话调试">
        <div className="dev-panel-heading">
          <div>
            <p className="eyebrow">DEVELOPMENT ONLY</p>
            <h2>AI Character Chat Debug</h2>
          </div>
        </div>

        <form className="ai-chat-form" onSubmit={handleAiChat}>
          <div className="ai-chat-selectors">
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
                  setCharacterDebugState(null)
                  setCharacterDebugError('')
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
          <p className="debug-note">
            私聊测试使用公共房间中选择的 GameSession。
          </p>

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
                HUMAN ·{' '}
                {aiChatGame?.game_characters.find(
                  (item) => item.controller_type === 'human',
                )?.character.name ?? '玩家'}{' '}
                · PRIVATE →{' '}
                {aiCharacters.find((item) => item.id === selectedAiTargetId)
                  ?.character.name ?? 'AI 角色'}
              </span>
              <p>{aiChatResponse.human_message.content}</p>
            </article>
            <article className="ai-chat-message">
              <span>
                AI ·{' '}
                {aiCharacters.find((item) => item.id === selectedAiTargetId)
                  ?.character.name ?? 'AI 角色'}{' '}
                · PRIVATE
              </span>
              <p>{aiChatResponse.ai_message.content}</p>
            </article>
          </div>
        )}

        <div className="character-debug-inspector">
          <div className="character-debug-heading">
            <div>
              <p className="eyebrow">DEBUG ONLY</p>
              <h3>AI Character State Inspector</h3>
            </div>
            <button
              className="action-button"
              type="button"
              disabled={
                aiChatGameId === null ||
                selectedAiTargetId === null ||
                characterDebugLoading
              }
              onClick={handleLoadCharacterDebug}
            >
              {characterDebugLoading ? '读取中…' : '读取角色状态'}
            </button>
          </div>
          {characterDebugError && (
            <p className="dev-message error-message" role="alert">
              {characterDebugError}
            </p>
          )}
          {visibleCharacterDebugState && (
            <div className="character-debug-grid">
              <div>
                <span>当前情绪</span>
                <strong>
                  {visibleCharacterDebugState.current_emotion ?? '暂无'}
                </strong>
              </div>
              <div>
                <span>最新意图</span>
                <strong>
                  {visibleCharacterDebugState.latest_thought?.intent ?? '暂无'}
                </strong>
              </div>
              <article>
                <span>最新 inner_os</span>
                <p>
                  {visibleCharacterDebugState.latest_thought?.inner_os ??
                    '尚无角色内心记录。'}
                </p>
              </article>
              <article>
                <span>长期记忆</span>
                {visibleCharacterDebugState.memories.length === 0 ? (
                  <p>尚无已保存记忆。</p>
                ) : (
                  <ul>
                    {visibleCharacterDebugState.memories.map((memory) => (
                      <li key={memory.id}>
                        <span>重要度 {memory.importance}</span>
                        {memory.content}
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            </div>
          )}
          {!visibleCharacterDebugState && !characterDebugLoading && (
            <p className="debug-note">
              这里仅用于开发检查；玩家正常对话只会看到角色 speech。
            </p>
          )}
        </div>
      </section>

      <footer className="footer">
        <span>仅用于验证角色信息边界与 AI 对话链路</span>
        <span className="footer-mark">
          PHASE 07 <i /> DEVELOPMENT DEBUG
        </span>
      </footer>
    </main>
  )
}

export default DevelopmentPage
