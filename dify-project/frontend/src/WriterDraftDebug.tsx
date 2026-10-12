import { useEffect, useState, type FormEvent } from 'react'

import {
  approveWriterDraft,
  createWriterDraft,
  generateWriterBlueprint,
  generateWriterChapterPack,
  getScriptQualityStatus,
  getWriterDraft,
  getWriterDraftPublication,
  getWriterDraftRevisions,
  getWriterDraftReviews,
  getWriterStatus,
  publishWriterDraft,
  reviewWriterDraft,
  reviseWriterDraft,
  type ScriptPublicationResponse,
  type ScriptRevisionRecord,
  type ScriptReviewRun,
  type WriterCreateRequest,
  type WriterDraft,
  type WriterPhase,
  type WriterStatusResponse,
} from './api'

const draftStorageKey = 'amm.writerDraftId'
const phases: WriterPhase[] = ['intro', 'act_1', 'act_2']
const phaseLabels: Record<WriterPhase, string> = {
  intro: '序章',
  act_1: '第一幕',
  act_2: '第二幕',
}
const roleKeys = ['role_1', 'role_2', 'role_3', 'role_4'] as const

function WriterDraftDebug() {
  const [writerStatus, setWriterStatus] = useState<WriterStatusResponse | null>(
    null,
  )
  const [statusError, setStatusError] = useState('')
  const [draft, setDraft] = useState<WriterDraft | null>(null)
  const [qualityStatus, setQualityStatus] = useState<{
    configured: boolean
  } | null>(null)
  const [qualityStatusError, setQualityStatusError] = useState('')
  const [reviewRuns, setReviewRuns] = useState<ScriptReviewRun[]>([])
  const [revisionRecords, setRevisionRecords] = useState<
    ScriptRevisionRecord[]
  >([])
  const [publication, setPublication] =
    useState<ScriptPublicationResponse | null>(null)
  const [revisionPhase, setRevisionPhase] = useState<WriterPhase>('intro')
  const [acceptedMediumIndexes, setAcceptedMediumIndexes] = useState<number[]>(
    [],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [phase, setPhase] = useState<WriterPhase>('intro')
  const [roleKey, setRoleKey] = useState<(typeof roleKeys)[number] | 'public'>(
    'public',
  )
  const [form, setForm] = useState<WriterCreateRequest>({
    theme: '封闭空间悬疑',
    era: '现代',
    atmosphere: '压抑、克制',
    difficulty: 'medium',
    custom_requirements: '',
  })

  useEffect(() => {
    const controller = new AbortController()
    getWriterStatus(controller.signal)
      .then(setWriterStatus)
      .catch((statusErrorValue: unknown) => {
        if (!controller.signal.aborted) {
          setStatusError(
            statusErrorValue instanceof Error
              ? statusErrorValue.message
              : '读取 Writer 配置状态失败',
          )
        }
      })
    getScriptQualityStatus(controller.signal)
      .then(setQualityStatus)
      .catch((qualityError: unknown) => {
        if (!controller.signal.aborted) {
          setQualityStatusError(
            qualityError instanceof Error
              ? qualityError.message
              : '读取 Quality Workflow 状态失败',
          )
        }
      })

    const storedId = Number(sessionStorage.getItem(draftStorageKey))
    if (Number.isInteger(storedId) && storedId > 0) {
      getWriterDraft(storedId)
        .then((loadedDraft) => {
          setDraft(loadedDraft)
          void loadQualityArtifacts(storedId)
        })
        .catch(() => sessionStorage.removeItem(draftStorageKey))
    }
    return () => controller.abort()
  }, [])

  async function loadQualityArtifacts(draftId: number) {
    const [loadedReviews, loadedRevisions, loadedPublication] =
      await Promise.allSettled([
        getWriterDraftReviews(draftId),
        getWriterDraftRevisions(draftId),
        getWriterDraftPublication(draftId),
      ])
    if (loadedReviews.status === 'fulfilled') {
      setReviewRuns(loadedReviews.value)
    }
    if (loadedRevisions.status === 'fulfilled') {
      setRevisionRecords(loadedRevisions.value)
    }
    if (loadedPublication.status === 'fulfilled') {
      setPublication(loadedPublication.value)
    }
  }

  async function handleCreateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const created = await createWriterDraft({
        ...form,
        custom_requirements: form.custom_requirements?.trim() || null,
      })
      setDraft(created)
      setReviewRuns([])
      setRevisionRecords([])
      setPublication(null)
      setAcceptedMediumIndexes([])
      sessionStorage.setItem(draftStorageKey, String(created.id))
    } catch (createError) {
      setError(
        createError instanceof Error ? createError.message : '创建 Draft 失败',
      )
    } finally {
      setBusy(false)
    }
  }

  async function runStep(action: () => Promise<WriterDraft>) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      setDraft(await action())
    } catch (stepError) {
      setError(
        stepError instanceof Error ? stepError.message : 'Writer 生成失败',
      )
      if (draft) {
        try {
          setDraft(await getWriterDraft(draft.id))
        } catch {
          // Keep the current draft view if the refresh also fails.
        }
      }
    } finally {
      setBusy(false)
    }
  }

  async function runQualityAction(action: () => Promise<unknown>) {
    if (busy || !draft) return
    setBusy(true)
    setError('')
    try {
      await action()
      setDraft(await getWriterDraft(draft.id))
      await loadQualityArtifacts(draft.id)
      setAcceptedMediumIndexes([])
    } catch (qualityActionError) {
      setError(
        qualityActionError instanceof Error
          ? qualityActionError.message
          : 'Quality 操作失败',
      )
      await loadQualityArtifacts(draft.id)
    } finally {
      setBusy(false)
    }
  }

  const blueprint = draft?.blueprint
  const selectedPack = draft?.chapter_packs[phase]
  const selectedChapter =
    roleKey === 'public'
      ? selectedPack?.shared_chapter
      : selectedPack?.character_chapters.find(
          (chapter) => chapter.role_key === roleKey,
        )
  const canResume = (step: string) =>
    draft?.failed_step === step || draft?.status === `generating_${step}`

  const currentReview = reviewRuns.find(
    (review) =>
      review.review_status === 'completed' &&
      review.content_revision === draft?.content_revision,
  )
  const currentReport = currentReview?.report
  const currentPhaseIssues =
    currentReport?.issues.filter(
      (issue) => issue.location.phase === revisionPhase,
    ) ?? []
  const mediumIssueIndexes =
    currentReport?.issues.flatMap((issue, index) =>
      issue.severity === 'medium' ? [index + 1] : [],
    ) ?? []
  const allMediumIssuesAccepted = mediumIssueIndexes.every((index) =>
    acceptedMediumIndexes.includes(index),
  )
  const hasBlockingIssues =
    currentReport?.verdict !== 'pass' ||
    currentReport.issues.some((issue) =>
      ['critical', 'high'].includes(issue.severity),
    )
  const isApproved = Boolean(
    publication &&
    publication.approved_revision === draft?.content_revision &&
    publication.approved_review_run_id === currentReview?.id,
  )

  return (
    <section
      className="dev-panel detail-panel writer-draft-panel"
      aria-label="Writer Draft 调试"
    >
      <div className="dev-panel-heading">
        <div>
          <p className="eyebrow">DEVELOPMENT ONLY · SPOILERS</p>
          <h2>AI Writer · Script Draft</h2>
        </div>
        <span
          className={`ai-status-pill ${
            statusError
              ? 'is-error'
              : writerStatus === null
                ? 'is-loading'
                : writerStatus.configured
                  ? 'is-ready'
                  : 'is-disabled'
          }`}
          role="status"
        >
          {statusError
            ? '状态读取失败'
            : writerStatus === null
              ? '正在检查配置…'
              : writerStatus.configured
                ? 'Writer 已配置'
                : 'Writer 未配置'}
        </span>
      </div>

      <p className="debug-note">
        本面板只生成未发布草稿。真相、凶手和角色秘密仅供开发调试，不能用于普通玩家页面。
      </p>
      {statusError && (
        <p className="dev-message error-message">{statusError}</p>
      )}
      {error && (
        <p className="dev-message error-message" role="alert">
          {error}
        </p>
      )}

      <form className="writer-request-form" onSubmit={handleCreateDraft}>
        <label className="field-label">
          主题
          <input
            className="dev-input"
            maxLength={120}
            required
            value={form.theme}
            onChange={(event) =>
              setForm((current) => ({ ...current, theme: event.target.value }))
            }
          />
        </label>
        <label className="field-label">
          时代
          <input
            className="dev-input"
            maxLength={120}
            required
            value={form.era}
            onChange={(event) =>
              setForm((current) => ({ ...current, era: event.target.value }))
            }
          />
        </label>
        <label className="field-label">
          氛围
          <input
            className="dev-input"
            maxLength={120}
            required
            value={form.atmosphere}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                atmosphere: event.target.value,
              }))
            }
          />
        </label>
        <label className="field-label">
          难度
          <select
            className="dev-select"
            value={form.difficulty}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                difficulty: event.target
                  .value as WriterCreateRequest['difficulty'],
              }))
            }
          >
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
        </label>
        <label className="field-label writer-requirements-field">
          自定义要求
          <textarea
            className="dev-input writer-requirements"
            maxLength={3000}
            value={form.custom_requirements ?? ''}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                custom_requirements: event.target.value,
              }))
            }
          />
        </label>
        <button className="action-button" type="submit" disabled={busy}>
          {busy && !draft ? '创建中…' : 'Create Draft · 创建草稿'}
        </button>
      </form>

      {draft && (
        <>
          <div className="writer-draft-status" role="status">
            <strong>
              Draft #{draft.id} · {draft.status}
            </strong>
            {draft.failed_step && (
              <span>
                失败步骤：{draft.failed_step}（{draft.last_error_type}）
              </span>
            )}
            {draft.status.startsWith('generating_') && (
              <span>
                生成任务正在运行；服务中断后同一步可在 10
                分钟租约过期后重新认领。
              </span>
            )}
          </div>
          <ol className="writer-step-list" aria-label="Writer 生成步骤">
            <li>
              <span>Step 1 · 案件蓝图</span>
              <span>
                {blueprint
                  ? '已完成'
                  : draft.status === 'generating_blueprint'
                    ? '生成中'
                    : '待生成'}
              </span>
              <button
                className="action-button"
                type="button"
                disabled={
                  busy || !writerStatus?.configured || Boolean(blueprint)
                }
                onClick={() => runStep(() => generateWriterBlueprint(draft.id))}
              >
                {canResume('blueprint') ? '恢复/重试' : 'Generate Blueprint'}
              </button>
            </li>
            {phases.map((currentPhase) => {
              const pack = draft.chapter_packs[currentPhase]
              const isFailed = draft.failed_step === currentPhase
              const isGenerating = draft.status === `generating_${currentPhase}`
              const previousReady =
                currentPhase === 'intro'
                  ? Boolean(blueprint)
                  : Boolean(
                      draft.chapter_packs[
                        phases[phases.indexOf(currentPhase) - 1]
                      ],
                    )
              return (
                <li key={currentPhase}>
                  <span>
                    Step {phases.indexOf(currentPhase) + 2} ·{' '}
                    {phaseLabels[currentPhase]}
                  </span>
                  <span>
                    {pack ? '已完成' : isGenerating ? '生成中' : '待生成'}
                  </span>
                  <button
                    className="action-button"
                    type="button"
                    disabled={
                      busy ||
                      !writerStatus?.configured ||
                      !previousReady ||
                      Boolean(pack)
                    }
                    onClick={() =>
                      runStep(() =>
                        generateWriterChapterPack(draft.id, currentPhase),
                      )
                    }
                  >
                    {isFailed || isGenerating
                      ? '恢复/重试'
                      : `Generate ${phaseLabels[currentPhase]}`}
                  </button>
                  {draft.step_durations_seconds[currentPhase] !== undefined && (
                    <small>
                      {draft.step_durations_seconds[currentPhase]} 秒
                    </small>
                  )}
                </li>
              )
            })}
          </ol>

          {blueprint && (
            <div className="writer-spoiler-content">
              <h3>{blueprint.script_metadata.title}</h3>
              <p>{blueprint.script_metadata.summary}</p>
              <details>
                <summary>DEVELOPMENT ONLY / SPOILERS · 案件真相</summary>
                <dl className="writer-truth-grid">
                  <div>
                    <dt>凶手</dt>
                    <dd>{blueprint.case_truth.culprit_role_key}</dd>
                  </div>
                  <div>
                    <dt>被害者</dt>
                    <dd>{blueprint.case_truth.victim}</dd>
                  </div>
                  <div>
                    <dt>动机</dt>
                    <dd>{blueprint.case_truth.motive}</dd>
                  </div>
                  <div>
                    <dt>手法</dt>
                    <dd>{blueprint.case_truth.method}</dd>
                  </div>
                  <div>
                    <dt>案发时间</dt>
                    <dd>{blueprint.case_truth.crime_time}</dd>
                  </div>
                  <div>
                    <dt>案发地点</dt>
                    <dd>{blueprint.case_truth.crime_location}</dd>
                  </div>
                </dl>
                <p className="story-chapter-content">
                  {blueprint.case_truth.case_summary}
                </p>
              </details>
              <details>
                <summary>DEVELOPMENT ONLY / SPOILERS · 四名角色</summary>
                <div className="writer-character-grid">
                  {blueprint.characters.map((character) => (
                    <article
                      className="writer-character-card"
                      key={character.role_key}
                    >
                      <h4>
                        {character.name} · {character.role_key}
                      </h4>
                      <p>
                        {character.identity} · {character.age ?? '年龄未设定'}
                      </p>
                      <p>{character.public_background}</p>
                      <p>
                        <strong>私人背景：</strong>
                        {character.private_background}
                      </p>
                      <p>
                        <strong>个人经历：</strong>
                        {character.personal_history}
                      </p>
                      <p>
                        <strong>对被害者：</strong>
                        {character.relationship_to_victim}
                      </p>
                      <p>
                        <strong>秘密：</strong>
                        {character.private_secrets.join('；')}
                      </p>
                      <p>
                        <strong>初始认知：</strong>
                        {character.initial_knowledge.join('；')}
                      </p>
                    </article>
                  ))}
                </div>
              </details>
              <details>
                <summary>DEVELOPMENT ONLY / SPOILERS · 时间线与线索</summary>
                <h4>真实时间线</h4>
                {blueprint.canonical_timeline.map((event) => (
                  <p className="story-chapter-content" key={event.event_key}>
                    {event.event_key} · {event.time} · {event.location}：
                    {event.description}
                  </p>
                ))}
                <h4>预设线索</h4>
                {blueprint.clues.map((clue) => (
                  <p className="story-chapter-content" key={clue.clue_key}>
                    {clue.clue_key} · {clue.name} · {clue.act}：
                    {clue.description}
                  </p>
                ))}
              </details>
            </div>
          )}

          <div className="writer-preview">
            <div className="dev-panel-heading">
              <div>
                <p className="eyebrow">DRAFT PREVIEW · SPOILERS</p>
                <h3>章节预览</h3>
              </div>
            </div>
            <div className="writer-preview-controls">
              <label className="field-label">
                阶段
                <select
                  className="dev-select"
                  value={phase}
                  onChange={(event) =>
                    setPhase(event.target.value as WriterPhase)
                  }
                >
                  {phases.map((value) => (
                    <option value={value} key={value}>
                      {phaseLabels[value]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                阅读视角
                <select
                  className="dev-select"
                  value={roleKey}
                  onChange={(event) =>
                    setRoleKey(event.target.value as typeof roleKey)
                  }
                >
                  <option value="public">公共章节</option>
                  {roleKeys.map((value) => (
                    <option value={value} key={value}>
                      {blueprint?.characters.find(
                        (character) => character.role_key === value,
                      )?.name ?? value}{' '}
                      私人章节
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {selectedChapter ? (
              <article className="story-chapter">
                <p className="eyebrow">
                  DEVELOPMENT ONLY / SPOILERS · {phaseLabels[phase]}
                </p>
                <h4>{selectedChapter.title}</h4>
                <p className="story-chapter-content">
                  {selectedChapter.content}
                </p>
              </article>
            ) : (
              <p className="dev-message">该阶段章节尚未生成。</p>
            )}
          </div>

          <section
            className="writer-quality-panel"
            aria-label="一致性审查与发布"
          >
            <div className="dev-panel-heading">
              <div>
                <p className="eyebrow">DEVELOPMENT ONLY · SPOILERS</p>
                <h3>一致性审查与正式发布</h3>
              </div>
              <span
                className={
                  'ai-status-pill ' +
                  (qualityStatusError
                    ? 'is-error'
                    : qualityStatus === null
                      ? 'is-loading'
                      : qualityStatus.configured
                        ? 'is-ready'
                        : 'is-disabled')
                }
                role="status"
              >
                {qualityStatusError
                  ? 'Quality 状态读取失败'
                  : qualityStatus === null
                    ? '正在检查 Quality 配置…'
                    : qualityStatus.configured
                      ? 'Quality Workflow 已配置'
                      : '缺少独立 Quality Key'}
              </span>
            </div>
            <p className="debug-note">
              当前内容版本：{draft.content_revision}
              。每次修订后必须重新审查；审查通过不会自动发布。
            </p>
            {qualityStatusError && (
              <p className="dev-message error-message">{qualityStatusError}</p>
            )}
            <div className="writer-quality-actions">
              <button
                className="action-button"
                type="button"
                disabled={
                  busy ||
                  draft.status !== 'draft_complete' ||
                  !qualityStatus?.configured
                }
                onClick={() =>
                  runQualityAction(() => reviewWriterDraft(draft.id))
                }
              >
                Run Consistency Review · 运行一致性审查
              </button>
              <label className="field-label">
                修订阶段
                <select
                  className="dev-select"
                  value={revisionPhase}
                  onChange={(event) =>
                    setRevisionPhase(event.target.value as WriterPhase)
                  }
                >
                  {phases.map((value) => (
                    <option value={value} key={value}>
                      {phaseLabels[value]}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="action-button"
                type="button"
                disabled={
                  busy ||
                  !qualityStatus?.configured ||
                  currentReport?.verdict !== 'needs_revision' ||
                  currentPhaseIssues.length === 0
                }
                onClick={() =>
                  runQualityAction(() =>
                    reviseWriterDraft(draft.id, revisionPhase),
                  )
                }
              >
                Revise Chapter Pack · 受控修订
              </button>
            </div>

            {currentReview && currentReport && (
              <article className="writer-review-report">
                <div className="dev-panel-heading">
                  <div>
                    <p className="eyebrow">
                      REVIEW #{currentReview.id} · REVISION{' '}
                      {currentReview.content_revision}
                    </p>
                    <h4>审查结论：{currentReport.verdict}</h4>
                  </div>
                </div>
                <p>{currentReport.summary}</p>
                {currentReport.issues.length === 0 ? (
                  <p className="dev-message">未报告问题。</p>
                ) : (
                  <ol className="writer-review-issues">
                    {currentReport.issues.map((issue, index) => (
                      <li key={String(currentReview.id) + '-' + index}>
                        <strong>
                          {index + 1}. {issue.severity} · {issue.issue_code}
                        </strong>
                        <p>{issue.description}</p>
                        <p>
                          <strong>位置：</strong>
                          {issue.location.scope} · {issue.location.field_path}
                          {issue.location.phase
                            ? ' · ' + phaseLabels[issue.location.phase]
                            : ''}
                          {issue.location.role_key
                            ? ' · ' + issue.location.role_key
                            : ''}
                          {issue.location.event_key
                            ? ' · ' + issue.location.event_key
                            : ''}
                          {issue.location.clue_key
                            ? ' · ' + issue.location.clue_key
                            : ''}
                        </p>
                        <p>
                          <strong>依据：</strong>
                          {issue.evidence}
                        </p>
                        <p>
                          <strong>建议：</strong>
                          {issue.suggested_fix}
                        </p>
                      </li>
                    ))}
                  </ol>
                )}
                {mediumIssueIndexes.length > 0 && (
                  <fieldset className="writer-medium-acceptance">
                    <legend>人工接受中等问题（逐项确认）</legend>
                    {mediumIssueIndexes.map((index) => {
                      const issue = currentReport.issues[index - 1]
                      return (
                        <label key={index}>
                          <input
                            type="checkbox"
                            checked={acceptedMediumIndexes.includes(index)}
                            onChange={(event) =>
                              setAcceptedMediumIndexes((current) =>
                                event.target.checked
                                  ? [...current, index].sort((a, b) => a - b)
                                  : current.filter((item) => item !== index),
                              )
                            }
                          />
                          接受问题 {index}：{issue.issue_code}
                        </label>
                      )
                    })}
                  </fieldset>
                )}
                <button
                  className="action-button"
                  type="button"
                  disabled={
                    busy ||
                    !qualityStatus?.configured ||
                    hasBlockingIssues ||
                    !allMediumIssuesAccepted ||
                    currentReview.content_revision !== draft.content_revision
                  }
                  onClick={() =>
                    runQualityAction(() =>
                      approveWriterDraft(
                        draft.id,
                        currentReview.id,
                        acceptedMediumIndexes,
                      ),
                    )
                  }
                >
                  Approve Current Revision · 批准当前版本
                </button>
              </article>
            )}

            {publication?.publication_status === 'published' ? (
              <p className="dev-message" role="status">
                已发布为正式 Script #{publication.script_id}：
                {publication.title}
              </p>
            ) : (
              <button
                className="action-button"
                type="button"
                disabled={busy || !isApproved || hasBlockingIssues}
                onClick={() => {
                  if (
                    window.confirm(
                      '确认将当前已审核、已批准的草稿发布为正式剧本？发布后可用于创建游戏。',
                    )
                  ) {
                    void runQualityAction(() => publishWriterDraft(draft.id))
                  }
                }}
              >
                Publish Script · 发布正式剧本
              </button>
            )}

            {revisionRecords.length > 0 && (
              <details className="writer-revision-history">
                <summary>修订历史（{revisionRecords.length}）</summary>
                {revisionRecords.map((record) => (
                  <article key={record.id}>
                    <strong>
                      {record.from_revision} → {record.to_revision} ·{' '}
                      {phaseLabels[record.phase]}
                    </strong>
                    <p>关联审查：#{record.related_review_id}</p>
                    <details>
                      <summary>查看修订前后章节</summary>
                      <h5>
                        修订前：
                        {record.previous_chapter_pack.shared_chapter.title}
                      </h5>
                      <p>
                        {record.previous_chapter_pack.shared_chapter.content}
                      </p>
                      <h5>
                        修订后：{record.new_chapter_pack.shared_chapter.title}
                      </h5>
                      <p>{record.new_chapter_pack.shared_chapter.content}</p>
                    </details>
                  </article>
                ))}
              </details>
            )}

            {reviewRuns.length > 0 && (
              <details className="writer-review-history">
                <summary>审查记录（{reviewRuns.length}）</summary>
                {reviewRuns.map((review) => (
                  <p key={review.id}>
                    #{review.id} · revision {review.content_revision} ·{' '}
                    {review.review_status} ·{' '}
                    {review.report?.verdict ?? review.error_type}
                  </p>
                ))}
              </details>
            )}
          </section>
        </>
      )}
    </section>
  )
}

export default WriterDraftDebug
