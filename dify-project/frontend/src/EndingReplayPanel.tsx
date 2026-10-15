import { useMemo, useState } from 'react'

import {
  getGameEnding,
  getGameReplay,
  type GameEnding,
  type GamePhase,
  type GameReplay,
  type GameReplayEvent,
} from './api'

const EVENT_LABELS: Record<GameReplayEvent['event_type'], string> = {
  game_started: '游戏开始',
  message: '发言',
  character_thought: '内心 OS',
  character_memory: '角色记忆',
  clue_acquired: '搜证获得',
  clue_disclosure: '线索分享',
  vote: '投票',
  game_ended: '游戏结束',
}

const PHASE_LABELS: Record<GamePhase, string> = {
  intro: '序章',
  act_1: '第一幕',
  investigation_1: '第一幕搜证',
  discussion_1: '第一幕讨论',
  act_2: '第二幕',
  investigation_2: '第二幕搜证',
  discussion_2: '第二幕讨论',
  final_discussion: '最终讨论',
  vote: '投票',
  ending: '结局',
}

interface EndingReplayPanelProps {
  gameId: number
  gameStatus: string
}

function EndingReplayPanel({ gameId, gameStatus }: EndingReplayPanelProps) {
  const [ending, setEnding] = useState<GameEnding | null>(null)
  const [replay, setReplay] = useState<GameReplay | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [phaseFilter, setPhaseFilter] = useState('all')
  const [actorFilter, setActorFilter] = useState('all')
  const [eventFilter, setEventFilter] = useState('all')

  const actors = useMemo(() => {
    if (!replay) return []
    return Array.from(
      new Map(
        replay.events
          .filter((event) => event.actor_game_character_id !== null)
          .map((event) => [
            event.actor_game_character_id,
            event.actor_name ?? `角色 #${event.actor_game_character_id}`,
          ]),
      ).entries(),
    )
  }, [replay])

  const filteredEvents = replay?.events.filter((event) => {
    if (phaseFilter !== 'all' && event.phase !== phaseFilter) return false
    if (
      actorFilter !== 'all' &&
      event.actor_game_character_id !== Number(actorFilter)
    ) {
      return false
    }
    return eventFilter === 'all' || event.event_type === eventFilter
  })

  async function loadEnding() {
    setBusy('ending')
    setError('')
    try {
      setEnding(await getGameEnding(gameId))
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : '读取结局失败',
      )
    } finally {
      setBusy('')
    }
  }

  async function loadReplay() {
    setBusy('replay')
    setError('')
    try {
      setReplay(await getGameReplay(gameId))
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '读取上帝视角回放失败',
      )
    } finally {
      setBusy('')
    }
  }

  const isFinished = gameStatus === 'finished'

  return (
    <section
      className="dev-panel detail-panel ending-replay-panel"
      aria-label="结局与上帝视角回放"
    >
      <div className="dev-panel-heading">
        <div>
          <p className="eyebrow">DEVELOPMENT ONLY · GOD VIEW</p>
          <h2>结局与上帝视角回放</h2>
        </div>
        <div className="ending-replay-actions">
          <button
            className="action-button"
            type="button"
            disabled={!isFinished || busy !== ''}
            onClick={() => void loadEnding()}
          >
            {busy === 'ending' ? '读取中…' : '揭晓结局'}
          </button>
          <button
            className="action-button secondary-button"
            type="button"
            disabled={!isFinished || busy !== ''}
            onClick={() => void loadReplay()}
          >
            {busy === 'replay' ? '读取中…' : '查看完整回放'}
          </button>
        </div>
      </div>

      {!isFinished && (
        <p className="debug-note">
          游戏结束且正式结算完成后，才会开放真相、他人私聊、记忆与内心 OS。
        </p>
      )}
      {isFinished && (
        <p className="debug-note">
          当前项目无登录认证；完整真相和私人记录仅在 Development 模式提供。
        </p>
      )}
      {error && (
        <p className="dev-message error-message" role="alert">
          {error}
        </p>
      )}

      {ending && (
        <div className="ending-content" aria-label="正式结局">
          <h3>{ending.ending_narrative}</h3>
          <div className="ending-truth-grid">
            <p>
              <strong>死者：</strong>
              {ending.truth.victim}
            </p>
            <p>
              <strong>凶手：</strong>
              {ending.culprit_name}
            </p>
            <p>
              <strong>动机：</strong>
              {ending.truth.motive}
            </p>
            <p>
              <strong>手法：</strong>
              {ending.truth.method}
            </p>
            <p>
              <strong>时间：</strong>
              {ending.truth.crime_time}
            </p>
            <p>
              <strong>地点：</strong>
              {ending.truth.crime_location}
            </p>
            <p>
              <strong>真人是否指认凶手：</strong>
              {ending.human_identified_culprit ? '是' : '否'}
            </p>
            <p>
              <strong>集体投票：</strong>
              {ending.is_tie
                ? '平局'
                : ending.vote_result === 'culprit_identified'
                  ? '指认正确'
                  : '指认错误'}
            </p>
          </div>
          <p>{ending.truth.case_summary}</p>
          <h4>关键因果事实</h4>
          <ul>
            {ending.truth.key_causal_facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
          <h4>案件真实时间线</h4>
          <ol>
            {ending.canonical_timeline.map((event) => (
              <li key={event.event_key}>
                <strong>
                  {event.time} · {event.location}
                </strong>
                ：{event.description}
              </li>
            ))}
          </ol>
          <h4>关键线索</h4>
          <ul>
            {ending.key_clues.map((clue) => (
              <li key={clue.clue_id}>
                {clue.name}：{clue.description}
              </li>
            ))}
          </ul>
          <h4>四人最终选票</h4>
          <ul>
            {ending.votes.map((vote) => (
              <li key={vote.vote_id}>
                {vote.voter_name} → {vote.target_name}
                {vote.reason ? `：${vote.reason}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {replay && (
        <div className="replay-content" aria-label="上帝视角事件时间线">
          <div className="replay-filters">
            <label>
              阶段
              <select
                value={phaseFilter}
                onChange={(event) => setPhaseFilter(event.target.value)}
              >
                <option value="all">全部阶段</option>
                {Object.entries(PHASE_LABELS).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              角色
              <select
                value={actorFilter ?? ''}
                onChange={(event) => setActorFilter(event.target.value)}
              >
                <option value="all">全部角色</option>
                {actors.map(([id, name]) => (
                  <option value={String(id)} key={String(id)}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              事件
              <select
                value={eventFilter}
                onChange={(event) => setEventFilter(event.target.value)}
              >
                <option value="all">全部事件</option>
                {Object.entries(EVENT_LABELS).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <ol className="replay-event-list">
            {(filteredEvents ?? []).map((event) => (
              <li className="replay-event" key={event.event_id}>
                <div className="replay-event-meta">
                  <strong>{EVENT_LABELS[event.event_type]}</strong>
                  <span>{new Date(event.timestamp).toLocaleString()}</span>
                  <span>
                    {event.phase ? PHASE_LABELS[event.phase] : '历史阶段未记录'}
                  </span>
                  <span>{event.actor_name ?? '系统'}</span>
                  <span>
                    {event.visibility === 'god'
                      ? '上帝视角'
                      : event.visibility === 'private'
                        ? '私密记录'
                        : '公开记录'}
                  </span>
                </div>
                {event.target_name && <p>对象：{event.target_name}</p>}
                {event.content && <p>{event.content}</p>}
                {event.inner_os && (
                  <p className="replay-inner-os">内心 OS：{event.inner_os}</p>
                )}
                {event.emotion && (
                  <p>
                    情绪：{event.emotion} · 意图：{event.intent}
                  </p>
                )}
                {event.subjective && (
                  <p className="debug-note">
                    主观记忆（不代表客观真相） · 重要度{' '}
                    {event.memory_importance}
                  </p>
                )}
              </li>
            ))}
          </ol>
          {(filteredEvents?.length ?? 0) === 0 && (
            <p className="debug-note">没有符合筛选条件的事件。</p>
          )}
        </div>
      )}
    </section>
  )
}

export default EndingReplayPanel
