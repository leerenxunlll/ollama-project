import { expect, test, type Route } from '@playwright/test'
import type {
  ScriptPublicationResponse,
  ScriptReviewRun,
  WriterDraft,
} from '../src/api'

const draftId = 91
const draftPath = '/api/writer/drafts/' + draftId
const currentTime = '2026-10-11T12:00:00Z'

test('reviews, revises, approves, and publishes only the current Draft revision', async ({
  page,
}) => {
  let revision = 1
  let reviewCount = 0
  let published = false
  let approved = false
  const reviews: ScriptReviewRun[] = []
  const revisions: Array<Record<string, unknown>> = []

  const draft: WriterDraft = {
    id: draftId,
    status: 'draft_complete',
    content_revision: revision,
    publication_status: 'unpublished',
    published_script_id: null,
    generation_request: {
      theme: '封闭空间悬疑',
      era: '现代',
      atmosphere: '冷峻',
      difficulty: 'medium',
      custom_requirements: null,
    },
    blueprint: null,
    chapter_packs: {},
    step_durations_seconds: {},
    failed_step: null,
    last_error_type: null,
    completed_steps: ['blueprint', 'intro', 'act_1', 'act_2'],
  }

  function makeReport(verdict: 'pass' | 'needs_revision') {
    return {
      verdict,
      summary:
        verdict === 'pass'
          ? '复审通过，未发现阻塞问题。'
          : '第一幕需要补充转场信息。',
      issues:
        verdict === 'pass'
          ? []
          : [
              {
                issue_code: 'missing_transition',
                category: 'narrative_continuity',
                severity: 'high' as const,
                description: '人物进入档案室的过程没有交代。',
                location: {
                  scope: 'shared_chapter' as const,
                  field_path: 'shared_chapter.content',
                  phase: 'act_1' as const,
                  role_key: null,
                  event_key: null,
                  clue_key: null,
                },
                evidence: '第一幕没有从走廊转场至档案室的叙述。',
                suggested_fix: '补充一段简短的转场描写。',
              },
            ],
    }
  }

  function makeReview(verdict: 'pass' | 'needs_revision'): ScriptReviewRun {
    reviewCount += 1
    return {
      id: reviewCount,
      draft_id: draftId,
      content_revision: revision,
      review_status: 'completed',
      report: makeReport(verdict),
      error_type: null,
      created_at: currentTime,
      completed_at: currentTime,
    }
  }

  function makePublication(): ScriptPublicationResponse {
    return {
      draft_id: draftId,
      publication_status: published ? 'published' : 'unpublished',
      script_id: published ? 987 : null,
      content_revision: revision,
      title: published ? '雾钟档案' : null,
      approved_revision: approved ? revision : null,
      approved_review_run_id: approved ? (reviews[0]?.id ?? null) : null,
      approved_at: approved ? currentTime : null,
    }
  }

  await page.addInitScript((id) => {
    sessionStorage.setItem('amm.writerDraftId', String(id))
  }, draftId)
  await page.route('**/api/**', async (route: Route) => {
    const { pathname } = new URL(route.request().url())
    const method = route.request().method()
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })

    if (pathname === '/api/health') {
      await json({ status: 'ok', app: 'AI Murder Mystery' })
    } else if (pathname === '/api/scripts' || pathname === '/api/games') {
      await json([])
    } else if (
      pathname === '/api/ai/status' ||
      pathname === '/api/director/status' ||
      pathname === '/api/writer/status'
    ) {
      await json({ configured: false })
    } else if (pathname === '/api/writer/quality/status') {
      await json({ configured: true })
    } else if (pathname === draftPath) {
      draft.content_revision = revision
      await json(draft)
    } else if (pathname === draftPath + '/reviews') {
      await json(reviews)
    } else if (pathname === draftPath + '/revisions') {
      await json(revisions)
    } else if (pathname === draftPath + '/publication' && method === 'GET') {
      await json(makePublication())
    } else if (pathname === draftPath + '/review' && method === 'POST') {
      const next = makeReview(reviewCount === 0 ? 'needs_revision' : 'pass')
      reviews.unshift(next)
      await json(next, 201)
    } else if (pathname === draftPath + '/revise/act_1' && method === 'POST') {
      revision += 1
      approved = false
      revisions.unshift({
        id: 1,
        draft_id: draftId,
        from_revision: 1,
        to_revision: 2,
        phase: 'act_1',
        related_review_id: reviews[0]?.id,
        issues_addressed: reviews[0]?.report?.issues ?? [],
        previous_chapter_pack: {
          phase: 'act_1',
          shared_chapter: {
            title: '第一幕',
            content: '旧内容',
            chapter_order: 2,
            unlock_phase: 'act_1',
          },
          character_chapters: [],
        },
        new_chapter_pack: {
          phase: 'act_1',
          shared_chapter: {
            title: '第一幕',
            content: '已补充转场',
            chapter_order: 2,
            unlock_phase: 'act_1',
          },
          character_chapters: [],
        },
        created_at: currentTime,
      })
      await json({ revision: revisions[0], content_revision: revision })
    } else if (pathname === draftPath + '/approve' && method === 'POST') {
      approved = true
      await json({
        draft_id: draftId,
        content_revision: revision,
        review_run_id: reviews[0]?.id,
        accepted_medium_issue_indexes: [],
        approved_at: currentTime,
      })
    } else if (pathname === draftPath + '/publish' && method === 'POST') {
      published = true
      await json(makePublication())
    } else {
      await json({ detail: 'Not found' }, 404)
    }
  })

  await page.goto('/')
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await expect(
    page.getByRole('heading', { name: '一致性审查与正式发布' }),
  ).toBeVisible()
  await expect(page.getByText('Draft #91 · draft_complete')).toBeVisible()

  await page.getByRole('button', { name: /Run Consistency Review/ }).click()
  await expect(page.getByText('审查结论：needs_revision')).toBeVisible()
  await page.getByLabel('修订阶段').selectOption('act_1')
  await page.getByRole('button', { name: /Revise Chapter Pack/ }).click()
  await expect(page.getByText('当前内容版本：2')).toBeVisible()
  await expect(
    page.getByRole('button', { name: /Approve Current Revision/ }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /Publish Script/ }),
  ).toBeDisabled()

  await page.getByRole('button', { name: /Run Consistency Review/ }).click()
  await expect(page.getByText('审查结论：pass')).toBeVisible()
  await page.getByRole('button', { name: /Approve Current Revision/ }).click()
  await expect(
    page.getByRole('button', { name: /Publish Script/ }),
  ).toBeEnabled()
  page.on('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: /Publish Script/ }).click()
  await expect(page.getByText(/已发布为正式 Script #987/)).toBeVisible()
})
