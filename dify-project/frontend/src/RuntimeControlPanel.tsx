import { useCallback, useEffect, useRef, useState } from 'react'

import {
  acknowledgeRuntimePhase,
  getGameRuntime,
  markRuntimeReady,
  pauseGameRuntime,
  startGameRuntime,
  tickGameRuntime,
  type GamePhase,
  type GameRuntimeStatus,
  type RuntimeStepResult,
  type StoryChapterRead,
} from './api'

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

const ACTION_LABELS: Record<string, string> = {
  none: '无动作',
  director_analysis: '导演分析',
  proactive_speech: 'AI 主动发言',
  phase_advance: '推进阶段',
  advisory: '仅记录建议',
}

const REASON_LABELS: Record<string, string> = {
  runtime_not_started: 'Runtime 尚未启动',
  runtime_paused: 'Runtime 已暂停',
  game_not_started: '游戏尚未开始',
  game_finished: '游戏已结束',
  no_new_event: '没有新的调度事件',
  cooldown_active: '冷却时间尚未结束',
  reading_not_acknowledged: '等待玩家确认已阅读本阶段剧本',
  minimum_duration_not_elapsed: '尚未达到本阶段最低时长',
  investigation_not_completed: '等待玩家结束搜证',
  final_vote_not_acknowledged: '等待玩家确认进入投票',
  vote_incomplete: '等待所有角色完成投票',
  human_active: '玩家近期有发言，暂不打断讨论',
  director_not_configured: 'Director Dify 尚未配置',
  director_timeout: 'Director 请求超时',
  director_output_invalid: 'Director 输出格式无效',
  director_unavailable: 'Director 服务暂不可用',
  character_not_configured: 'Character Dify 尚未配置',
  character_timeout: 'Character 请求超时',
  character_output_invalid: 'Character 输出格式无效',
  character_unavailable: 'Character 服务暂不可用',
  stale_phase: '游戏阶段已变化，本次动作已取消',
  concurrent_tick_conflict: '另一个 Runtime 请求正在处理',
  phase_advanced: '阶段已推进',
  action_applied: '导演建议已处理',
  advisory_only: '建议已记录，没有自动改变游戏状态',
  recommendation_pending: '建议等待后续条件',
  no_eligible_action: '当前没有符合条件的动作',
  reading_completed: '阅读确认和最低时长均已满足',
  investigation_ready: '搜证已结束，可以推进',
  discussion_ready: '玩家已准备结束讨论',
  final_vote_ready: '玩家已准备进入投票',
  all_votes_cast: '所有角色已投票',
}

interface RuntimeControlPanelProps {
  gameId: number
  gameStatus: string
  currentPhase: GamePhase
  publicChapters: StoryChapterRead[]
  personalChapters: StoryChapterRead[]
  onRuntimeUpdate: () => void
}

function RuntimeControlPanel({
  gameId,
  gameStatus,
  currentPhase,
  publicChapters,
  personalChapters,
  onRuntimeUpdate,
}: RuntimeControlPanelProps) {
  const [runtime, setRuntime] = useState<GameRuntimeStatus | null>(null)
  const [autoTick, setAutoTick] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [lastResult, setLastResult] = useState<RuntimeStepResult | null>(null)
  const tickInFlight = useRef(false)
  const onRuntimeUpdateRef = useRef(onRuntimeUpdate)

  useEffect(() => {
    onRuntimeUpdateRef.current = onRuntimeUpdate
  }, [onRuntimeUpdate])

  const refreshRuntime = useCallback(async () => {
    const result = await getGameRuntime(gameId)
    setRuntime(result)
    return result
  }, [gameId])

  useEffect(() => {
    let active = true
    setRuntime(null)
    setError('')
    setLastResult(null)
    setAutoTick(false)
    getGameRuntime(gameId)
      .then((result) => {
        if (active) setRuntime(result)
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : '读取 Runtime 状态失败',
          )
        }
      })
    return () => {
      active = false
    }
  }, [gameId])

  const runTick = useCallback(async () => {
    if (tickInFlight.current) return
    tickInFlight.current = true
    try {
      const result = await tickGameRuntime(gameId)
      setLastResult(result)
      await refreshRuntime()
      onRuntimeUpdateRef.current()
      setError('')
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Runtime Tick 执行失败',
      )
    } finally {
      tickInFlight.current = false
    }
  }, [gameId, refreshRuntime])

  useEffect(() => {
    if (!autoTick || runtime?.runtime_status !== 'enabled') return undefined

    const intervalId = window.setInterval(() => {
      void runTick()
    }, 10_000)
    return () => window.clearInterval(intervalId)
  }, [autoTick, runTick, runtime?.runtime_status])

  async function handleControl(action: 'start' | 'pause' | 'tick') {
    setBusy(action)
    setError('')
    try {
      if (action === 'start') {
        setRuntime(await startGameRuntime(gameId))
      } else if (action === 'pause') {
        setRuntime(await pauseGameRuntime(gameId))
        setAutoTick(false)
      } else {
        await runTick()
      }
      if (action !== 'tick') onRuntimeUpdateRef.current()
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Runtime 操作失败',
      )
    } finally {
      setBusy('')
    }
  }

  async function handlePhaseAction(action: 'acknowledge' | 'ready') {
    setBusy(action)
    setError('')
    try {
      if (action === 'acknowledge') {
        await acknowledgeRuntimePhase(gameId)
      } else {
        await markRuntimeReady(gameId)
      }
      await refreshRuntime()
      onRuntimeUpdateRef.current()
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : '阶段确认失败',
      )
    } finally {
      setBusy('')
    }
  }

  const phaseChapters = (chapters: StoryChapterRead[]) =>
    chapters.filter((chapter) => chapter.unlock_phase === currentPhase)

  const readingPhase = ['intro', 'act_1', 'act_2'].includes(currentPhase)
  const readyPhase = [
    'investigation_1',
    'discussion_1',
    'investigation_2',
    'discussion_2',
    'final_discussion',
  ].includes(currentPhase)
  const readyLabel =
    currentPhase === 'investigation_1' || currentPhase === 'investigation_2'
      ? '结束搜证并继续'
      : currentPhase === 'final_discussion'
        ? '准备进入投票'
        : '准备结束讨论'

  return (
    <section
      className="dev-panel detail-panel runtime-panel"
      aria-label="Runtime 控制面板"
    >
      <div className="dev-panel-heading">
        <div>
          <p className="eyebrow">DEBUG ONLY · BOUNDED GAME RUNTIME</p>
          <h2>自主运行控制</h2>
        </div>
        <span
          className={`runtime-status runtime-${runtime?.runtime_status ?? 'loading'}`}
          role="status"
        >
          {runtime?.runtime_status === 'enabled'
            ? '运行中'
            : runtime?.runtime_status === 'paused'
              ? '已暂停'
              : runtime?.runtime_status === 'not_started'
                ? '尚未启动'
                : '读取中'}
        </span>
      </div>

      <div className="runtime-summary-grid">
        <div className="flow-stat">
          <span>当前阶段</span>
          <strong>{PHASE_LABELS[currentPhase]}</strong>
        </div>
        <div className="flow-stat">
          <span>Runtime 动作</span>
          <strong>
            {runtime?.action_status === 'processing'
              ? '处理中'
              : runtime?.action_status === 'failed'
                ? '上次失败'
                : '空闲'}
          </strong>
        </div>
        <div className="flow-stat">
          <span>最近导演分析</span>
          <strong>{formatTimestamp(runtime?.last_director_analysis_at)}</strong>
        </div>
        <div className="flow-stat">
          <span>最近主动发言</span>
          <strong>{formatTimestamp(runtime?.last_proactive_speech_at)}</strong>
        </div>
        <div className="flow-stat">
          <span>下次检查</span>
          <strong>
            {runtime ? `${runtime.next_check_after_seconds} 秒后` : '—'}
          </strong>
        </div>
      </div>

      <div className="runtime-controls">
        <button
          className="action-button"
          type="button"
          disabled={
            gameStatus !== 'in_progress' ||
            busy !== '' ||
            runtime?.runtime_status === 'enabled'
          }
          onClick={() => void handleControl('start')}
        >
          {busy === 'start' ? '启动中…' : 'Start Runtime'}
        </button>
        <button
          className="action-button secondary-button"
          type="button"
          disabled={busy !== '' || runtime?.runtime_status !== 'enabled'}
          onClick={() => void handleControl('pause')}
        >
          {busy === 'pause' ? '暂停中…' : 'Pause Runtime'}
        </button>
        <button
          className="action-button secondary-button"
          type="button"
          disabled={busy !== '' || runtime?.runtime_status !== 'enabled'}
          onClick={() => void handleControl('tick')}
        >
          {busy === 'tick' ? 'Tick 中…' : 'Manual Tick'}
        </button>
        <label className="runtime-auto-toggle">
          <input
            type="checkbox"
            checked={autoTick}
            disabled={runtime?.runtime_status !== 'enabled'}
            onChange={(event) => setAutoTick(event.target.checked)}
          />
          Auto Tick（每 10 秒）
        </label>
      </div>

      {readingPhase && (
        <div className="runtime-reading" aria-label="当前阶段剧本阅读">
          <p className="section-caption">
            请阅读本阶段已解锁的公共剧本与个人剧本，再确认已阅读。
          </p>
          <div className="runtime-script-columns">
            <article>
              <h3>公共剧本 · {PHASE_LABELS[currentPhase]}</h3>
              {phaseChapters(publicChapters).length > 0 ? (
                phaseChapters(publicChapters).map((chapter) => (
                  <details key={chapter.chapter_id} open>
                    <summary>{chapter.title}</summary>
                    <p>{chapter.content}</p>
                  </details>
                ))
              ) : (
                <p className="debug-note">当前没有已解锁的公共章节。</p>
              )}
            </article>
            <article>
              <h3>个人剧本 · {PHASE_LABELS[currentPhase]}</h3>
              {phaseChapters(personalChapters).length > 0 ? (
                phaseChapters(personalChapters).map((chapter) => (
                  <details key={chapter.chapter_id} open>
                    <summary>{chapter.title}</summary>
                    <p>{chapter.content}</p>
                  </details>
                ))
              ) : (
                <p className="debug-note">当前没有已解锁的个人章节。</p>
              )}
            </article>
          </div>
          <button
            className="action-button"
            type="button"
            disabled={
              busy !== '' ||
              runtime?.phase_read_acknowledged === true ||
              gameStatus !== 'in_progress'
            }
            onClick={() => void handlePhaseAction('acknowledge')}
          >
            {runtime?.phase_read_acknowledged
              ? '本阶段已确认阅读'
              : busy === 'acknowledge'
                ? '确认中…'
                : '确认已阅读'}
          </button>
        </div>
      )}

      {readyPhase && (
        <div className="runtime-ready-row">
          <p className="section-caption">
            {runtime?.ready_for_phase === currentPhase
              ? '已记录当前阶段的准备状态。'
              : '由后端验证最低时长和阶段资格。'}
          </p>
          <button
            className="action-button"
            type="button"
            disabled={
              busy !== '' ||
              runtime?.ready_for_phase === currentPhase ||
              gameStatus !== 'in_progress'
            }
            onClick={() => void handlePhaseAction('ready')}
          >
            {busy === 'ready' ? '记录中…' : readyLabel}
          </button>
        </div>
      )}

      {lastResult && (
        <p
          className="dev-message runtime-result"
          role="status"
          data-testid="runtime-result"
        >
          {ACTION_LABELS[lastResult.action_type] ?? lastResult.action_type}：
          {REASON_LABELS[lastResult.reason_code] ?? lastResult.reason_code}
          {lastResult.phase_before !== lastResult.phase_after &&
            `（${PHASE_LABELS[lastResult.phase_before]} → ${PHASE_LABELS[lastResult.phase_after]}）`}
        </p>
      )}
      {error && (
        <p className="dev-message error-message" role="alert">
          {error}
        </p>
      )}
      {runtime?.last_error_code && (
        <p className="debug-note" role="status">
          最近错误：
          {REASON_LABELS[runtime.last_error_code] ?? runtime.last_error_code}
        </p>
      )}

      <div className="runtime-action-log" aria-label="最近 Runtime 动作">
        <h3>最近动作</h3>
        {runtime?.recent_actions.length ? (
          <ol>
            {runtime.recent_actions.map((action) => (
              <li key={action.id}>
                <span>{formatTimestamp(action.started_at)}</span>
                <strong>
                  {ACTION_LABELS[action.action_type ?? 'none'] ??
                    action.action_type}
                </strong>
                <span>
                  {REASON_LABELS[action.reason_code ?? ''] ??
                    action.reason_code ??
                    '处理中'}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="debug-note">暂无 Runtime 动作记录。</p>
        )}
      </div>
    </section>
  )
}

function formatTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '暂无'
}

export default RuntimeControlPanel
