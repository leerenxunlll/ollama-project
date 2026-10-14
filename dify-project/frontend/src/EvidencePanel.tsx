import { useEffect, useMemo, useState } from 'react'

import {
  getClueEvents,
  getInvestigationLocations,
  getMyClues,
  getPublicClues,
  searchInvestigationLocation,
  shareClue,
  type ClueEvidence,
  type ClueHistoryEvent,
  type GameCharacterSummary,
  type MyClueState,
} from './api'

interface EvidencePanelProps {
  gameId: number
  humanGameCharacterId: number
  humanName: string
  aiCharacters: GameCharacterSummary[]
  canInvestigate: boolean
}

function EvidencePanel({
  gameId,
  humanGameCharacterId,
  humanName,
  aiCharacters,
  canInvestigate,
}: EvidencePanelProps) {
  const [myClues, setMyClues] = useState<MyClueState | null>(null)
  const [publicClues, setPublicClues] = useState<ClueEvidence[]>([])
  const [events, setEvents] = useState<ClueHistoryEvent[]>([])
  const [locations, setLocations] = useState<string[]>([])
  const [selectedLocation, setSelectedLocation] = useState('')
  const [selectedClueId, setSelectedClueId] = useState<number | null>(null)
  const [visibility, setVisibility] = useState<'private' | 'public'>('private')
  const [targetGameCharacterId, setTargetGameCharacterId] = useState<
    number | null
  >(aiCharacters[0]?.id ?? null)
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [searchNotice, setSearchNotice] = useState('')

  const selectableClues = useMemo(() => {
    const uniqueClues = new Map<number, ClueEvidence>()
    for (const clue of [
      ...(myClues?.acquired_clues ?? []),
      ...(myClues?.known_via_share_clues ?? []),
      ...(myClues?.publicly_disclosed_clues ?? []),
    ]) {
      uniqueClues.set(clue.clue_id, clue)
    }
    return [...uniqueClues.values()]
  }, [myClues])

  async function refreshEvidence() {
    const [loadedMine, loadedPublic, loadedEvents] = await Promise.all([
      getMyClues(gameId),
      getPublicClues(gameId),
      getClueEvents(gameId),
    ])
    setMyClues(loadedMine)
    setPublicClues(loadedPublic.clues)
    setEvents(loadedEvents)
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setNotice('')
    Promise.all([
      getMyClues(gameId),
      getPublicClues(gameId),
      getClueEvents(gameId),
      canInvestigate
        ? getInvestigationLocations(gameId)
        : Promise.resolve(null),
    ])
      .then(([loadedMine, loadedPublic, loadedEvents, loadedLocations]) => {
        if (!active) return
        setMyClues(loadedMine)
        setPublicClues(loadedPublic.clues)
        setEvents(loadedEvents)
        const nextLocations = loadedLocations?.locations ?? []
        setLocations(nextLocations)
        setSelectedLocation((current) =>
          nextLocations.includes(current) ? current : (nextLocations[0] ?? ''),
        )
      })
      .catch((loadError: unknown) => {
        if (active) {
          setError(
            loadError instanceof Error ? loadError.message : '读取线索信息失败',
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [canInvestigate, gameId, humanGameCharacterId])

  useEffect(() => {
    if (selectedClueId === null && selectableClues.length > 0) {
      setSelectedClueId(selectableClues[0].clue_id)
    } else if (
      selectedClueId !== null &&
      !selectableClues.some((clue) => clue.clue_id === selectedClueId)
    ) {
      setSelectedClueId(selectableClues[0]?.clue_id ?? null)
    }
  }, [selectableClues, selectedClueId])

  useEffect(() => {
    if (
      aiCharacters.some((character) => character.id === targetGameCharacterId)
    ) {
      return
    }
    setTargetGameCharacterId(aiCharacters[0]?.id ?? null)
  }, [aiCharacters, targetGameCharacterId])

  async function handleSearch() {
    if (!selectedLocation) return
    setAction('search')
    setError('')
    setSearchNotice('')
    try {
      const result = await searchInvestigationLocation(gameId, selectedLocation)
      setSearchNotice(
        result.found && result.clue
          ? `发现线索：${result.clue.name}`
          : '这个地点没有新的线索。',
      )
      await refreshEvidence()
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : '搜证失败')
    } finally {
      setAction('')
    }
  }

  async function handleShare() {
    if (selectedClueId === null) return
    if (visibility === 'private' && targetGameCharacterId === null) return
    const clue = selectableClues.find((item) => item.clue_id === selectedClueId)
    if (!clue) return

    setAction('share')
    setError('')
    setNotice('')
    try {
      const result = await shareClue(gameId, {
        clue_id: selectedClueId,
        visibility,
        target_game_character_id:
          visibility === 'private' ? targetGameCharacterId : null,
        client_request_id: crypto.randomUUID(),
      })
      const targetName = aiCharacters.find(
        (character) => character.id === targetGameCharacterId,
      )?.character.name
      setNotice(
        result.replayed
          ? '这条分享已记录，无需重复发送。'
          : visibility === 'public'
            ? `已向所有角色公开「${clue.name}」。`
            : `已私下分享「${clue.name}」给${targetName ?? '目标角色'}。`,
      )
      await refreshEvidence()
    } catch (shareError) {
      setError(
        shareError instanceof Error ? shareError.message : '分享线索失败',
      )
    } finally {
      setAction('')
    }
  }

  return (
    <section className="evidence-panel" aria-label="搜证与线索分享">
      <div className="dev-panel-heading">
        <div>
          <p className="eyebrow">INVESTIGATION & EVIDENCE</p>
          <h2>搜证与线索流转</h2>
          <p className="section-caption">当前玩家：{humanName}</p>
        </div>
        <button
          className="action-button"
          type="button"
          disabled={loading || action !== ''}
          onClick={() => {
            setLoading(true)
            refreshEvidence()
              .catch((refreshError: unknown) =>
                setError(
                  refreshError instanceof Error
                    ? refreshError.message
                    : '刷新线索失败',
                ),
              )
              .finally(() => setLoading(false))
          }}
        >
          刷新线索
        </button>
      </div>

      {error && (
        <p className="dev-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="dev-message" role="status">
          {notice}
        </p>
      )}

      {canInvestigate && (
        <div className="evidence-search">
          <div>
            <p className="eyebrow">当前可调查地点</p>
            {locations.length > 0 ? (
              <div className="evidence-search-controls">
                <select
                  className="dev-select"
                  aria-label="调查地点"
                  value={selectedLocation}
                  onChange={(event) => setSelectedLocation(event.target.value)}
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
                  disabled={loading || action !== '' || selectedLocation === ''}
                  onClick={handleSearch}
                >
                  {action === 'search' ? '搜证中…' : '调查地点'}
                </button>
              </div>
            ) : (
              <p className="section-caption">本幕没有预设调查地点。</p>
            )}
            {searchNotice && (
              <p className="dev-message" role="status">
                {searchNotice}
              </p>
            )}
          </div>
          <p className="section-caption">
            每次调查最多发现一条线索；地点列表不包含隐藏线索正文。
          </p>
        </div>
      )}

      <div className="evidence-columns">
        <EvidenceList
          title="我亲自搜到"
          clues={myClues?.acquired_clues ?? []}
        />
        <EvidenceList
          title="别人私下分享给我"
          clues={myClues?.known_via_share_clues ?? []}
        />
        <EvidenceList title="已经公开" clues={publicClues} />
      </div>

      <div className="evidence-share">
        <div>
          <p className="eyebrow">显式分享</p>
          <h3>选择已知线索</h3>
        </div>
        {selectableClues.length > 0 ? (
          <div className="evidence-share-controls">
            <select
              className="dev-select"
              aria-label="选择要分享的线索"
              value={selectedClueId ?? ''}
              onChange={(event) =>
                setSelectedClueId(Number(event.target.value))
              }
            >
              {selectableClues.map((clue) => (
                <option key={clue.clue_id} value={clue.clue_id}>
                  {clue.name}
                </option>
              ))}
            </select>
            <select
              className="dev-select"
              aria-label="分享范围"
              value={visibility}
              onChange={(event) =>
                setVisibility(event.target.value as 'private' | 'public')
              }
            >
              <option value="private">私下分享</option>
              <option value="public">公开展示</option>
            </select>
            {visibility === 'private' && (
              <select
                className="dev-select"
                aria-label="分享给角色"
                value={targetGameCharacterId ?? ''}
                onChange={(event) =>
                  setTargetGameCharacterId(Number(event.target.value))
                }
              >
                {aiCharacters.map((character) => (
                  <option key={character.id} value={character.id}>
                    {character.character.name}
                  </option>
                ))}
              </select>
            )}
            <button
              className="action-button"
              type="button"
              disabled={
                loading ||
                action !== '' ||
                (visibility === 'private' && targetGameCharacterId === null)
              }
              onClick={handleShare}
            >
              {action === 'share' ? '提交中…' : '正式分享线索'}
            </button>
          </div>
        ) : (
          <p className="section-caption">获得或收到线索后，才能在这里分享。</p>
        )}
      </div>

      <div className="evidence-history">
        <h3>可见线索事件</h3>
        {events.length === 0 ? (
          <p className="section-caption">暂无线索事件。</p>
        ) : (
          <ol>
            {events.map((event) => (
              <li key={event.event_id}>
                <span>{historyLabel(event)}</span>
                <strong>{event.clue_name}</strong>
                <small>
                  {event.actor_name}
                  {event.target_name ? ` → ${event.target_name}` : ''}
                </small>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  )
}

function EvidenceList({
  title,
  clues,
}: {
  title: string
  clues: ClueEvidence[]
}) {
  return (
    <section className="evidence-list">
      <h3>{title}</h3>
      {clues.length === 0 ? (
        <p className="section-caption">暂无线索。</p>
      ) : (
        <ul>
          {clues.map((clue) => (
            <li key={clue.clue_id}>
              <strong>{clue.name}</strong>
              <p>{clue.description}</p>
              <small>
                {clue.location} · {clue.act}
              </small>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function historyLabel(event: ClueHistoryEvent) {
  if (event.event_type === 'clue_acquired') return '搜证获得'
  if (event.event_type === 'clue_shared_privately') return '私下分享'
  return '公开展示'
}

export default EvidencePanel
