import { useCallback, useEffect, useState } from 'react'

import {
  getGameVoteStatus,
  getVoteWorkflowStatus,
  submitGameVote,
  type GameCharacterSummary,
  type GamePhase,
  type GameVoteStatus,
} from './api'

interface VotingPanelProps {
  gameId: number
  gameStatus: string
  currentPhase: GamePhase
  canVote: boolean
  characters: GameCharacterSummary[]
}

function VotingPanel({
  gameId,
  gameStatus,
  currentPhase,
  canVote,
  characters,
}: VotingPanelProps) {
  const [voteStatus, setVoteStatus] = useState<GameVoteStatus | null>(null)
  const [voteConfigured, setVoteConfigured] = useState<boolean | null>(null)
  const [targetId, setTargetId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const human = characters.find(
    (character) => character.controller_type === 'human',
  )
  const candidates = characters.filter(
    (character) => character.id !== human?.id,
  )
  const selectedTarget = candidates.find(
    (character) => character.id === targetId,
  )

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setVoteStatus(await getGameVoteStatus(gameId))
      setError('')
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '读取投票进度失败',
      )
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    setVoteStatus(null)
    setError('')
    setMessage('')
    setTargetId(null)
    void refresh()
    getVoteWorkflowStatus()
      .then((result) => setVoteConfigured(result.configured))
      .catch(() => setVoteConfigured(false))
    const intervalId = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(intervalId)
  }, [gameId, refresh])

  async function handleSubmitVote() {
    if (!human || !selectedTarget || !canVote) return
    const confirmed = window.confirm(
      `确认投票给${selectedTarget.character.name}吗？投票提交后不可撤销或修改。`,
    )
    if (!confirmed) return

    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      await submitGameVote(gameId, human.id, selectedTarget.id)
      setMessage(`已投票给${selectedTarget.character.name}。此票不可撤销。`)
      await refresh()
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : '投票提交失败',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section
      className="dev-panel detail-panel voting-panel"
      aria-label="投票面板"
    >
      <div className="dev-panel-heading">
        <div>
          <p className="eyebrow">VOTING · 1 HUMAN + 3 AI</p>
          <h2>最终投票</h2>
        </div>
        <button
          className="action-button secondary-button"
          type="button"
          disabled={loading}
          onClick={() => void refresh()}
        >
          {loading ? '刷新中…' : '刷新进度'}
        </button>
      </div>

      <p className="section-caption">
        真人和三个 AI 分别投出一票。投票目标和 AI 理由在结算前不会显示。
      </p>
      {human ? (
        <div className="vote-controls">
          <div className="flow-stat">
            <span>真人角色</span>
            <strong>{human.character.name}</strong>
          </div>
          <div>
            <label className="field-label" htmlFor="human-vote-target">
              选择怀疑对象
            </label>
            <select
              className="dev-select"
              id="human-vote-target"
              value={targetId ?? ''}
              disabled={
                !canVote ||
                voteStatus?.human_has_voted === true ||
                candidates.length === 0
              }
              onChange={(event) =>
                setTargetId(Number(event.target.value) || null)
              }
            >
              <option value="">选择一名角色</option>
              {candidates.map((character) => (
                <option key={character.id} value={character.id}>
                  {character.character.name}
                </option>
              ))}
            </select>
          </div>
          <button
            className="action-button"
            type="button"
            disabled={
              !canVote ||
              !targetId ||
              voteStatus?.human_has_voted === true ||
              submitting
            }
            onClick={() => void handleSubmitVote()}
          >
            {submitting
              ? '提交中…'
              : voteStatus?.human_has_voted
                ? '已投票'
                : '确认投票'}
          </button>
        </div>
      ) : (
        <p className="dev-message error-message" role="alert">
          当前游戏未找到真人角色，无法投票。
        </p>
      )}

      {voteStatus && (
        <div className="vote-status-grid" aria-label="安全投票进度">
          <p className="vote-progress-line">
            已完成 {voteStatus.votes_cast} / {voteStatus.total_voters} 票
          </p>
          <p className="vote-progress-line">
            真人：{voteStatus.human_has_voted ? '已投票' : '待投票'}
          </p>
          {voteStatus.ai_characters.map((character) => (
            <p className="vote-progress-line" key={character.game_character_id}>
              {character.character_name}：
              {character.has_voted ? '已投票' : '待投票'}
            </p>
          ))}
        </div>
      )}

      {currentPhase === 'vote' && gameStatus === 'in_progress' && (
        <p className="debug-note">
          AI 通过已启用的 Runtime Tick 逐一调用 Character Vote Workflow。
        </p>
      )}
      {voteConfigured === false && (
        <p className="dev-message error-message" role="status">
          Character Vote Workflow 未配置。请在 .env 填写 DIFY_VOTE_API_KEY；AI
          不会被程序代投。
        </p>
      )}
      {message && (
        <p className="dev-message" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="dev-message error-message" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}

export default VotingPanel
