import { expect, test, type Route } from '@playwright/test'

const gameId = 77

const game = {
  id: gameId,
  script_id: 12,
  status: 'in_progress',
  current_phase: 'vote',
  created_at: '2026-10-06T08:00:00Z',
  started_at: '2026-10-06T08:00:00Z',
  ended_at: null,
  game_characters: [
    {
      id: 41,
      character_id: 101,
      controller_type: 'human',
      character: { id: 101, name: '林澈' },
    },
    {
      id: 42,
      character_id: 102,
      controller_type: 'ai',
      character: { id: 102, name: '许棠' },
    },
    {
      id: 43,
      character_id: 103,
      controller_type: 'ai',
      character: { id: 103, name: '陈默' },
    },
    {
      id: 44,
      character_id: 104,
      controller_type: 'ai',
      character: { id: 104, name: '周岚' },
    },
  ],
}

let submittedVoterId: number | null = null
let submittedTargetId: number | null = null

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}

test('shows the Phase 7 game flow and Director debug without private context', async ({
  page,
}) => {
  submittedVoterId = null
  submittedTargetId = null

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    const method = request.method()

    if (pathname === '/api/health' && method === 'GET') {
      await fulfillJson(route, { status: 'ok', app: 'AI Murder Mystery' })
      return
    }
    if (pathname === '/api/scripts' && method === 'GET') {
      await fulfillJson(route, [
        {
          id: 12,
          title: '雾港来信',
          summary: '一份测试剧本',
          theme: '悬疑',
          status: 'ready',
        },
      ])
      return
    }
    if (pathname === '/api/games' && method === 'GET') {
      await fulfillJson(route, [game])
      return
    }
    if (pathname === '/api/ai/status' && method === 'GET') {
      await fulfillJson(route, { configured: false })
      return
    }
    if (pathname === '/api/director/status' && method === 'GET') {
      await fulfillJson(route, { configured: true })
      return
    }
    if (pathname === `/api/games/${gameId}` && method === 'GET') {
      await fulfillJson(route, game)
      return
    }
    if (pathname === `/api/games/${gameId}/state` && method === 'GET') {
      await fulfillJson(route, {
        game_id: gameId,
        status: 'in_progress',
        current_phase: 'vote',
        started_at: game.started_at,
        ended_at: null,
        next_phase: 'ending',
        can_investigate: false,
      })
      return
    }
    if (pathname === `/api/games/${gameId}/me/character` && method === 'GET') {
      await fulfillJson(
        route,
        { detail: 'No player card in this debug fixture' },
        404,
      )
      return
    }
    if (pathname === `/api/games/${gameId}/flow` && method === 'GET') {
      await fulfillJson(route, {
        game_id: gameId,
        status: 'in_progress',
        current_phase: 'vote',
        phase_started_at: '2026-10-06T08:00:00Z',
        elapsed_seconds: 90,
        minimum_duration_seconds: 120,
        remaining_seconds: 30,
        minimum_time_satisfied: false,
        can_investigate: false,
        can_discuss: false,
        can_public_speak: false,
        can_vote: true,
        can_advance: false,
        is_finished: false,
        vote_progress: {
          votes_cast: submittedVoterId === null ? 0 : 1,
          total_voters: 4,
          voting_complete: false,
        },
      })
      return
    }
    if (pathname === `/api/games/${gameId}/votes/result` && method === 'GET') {
      await fulfillJson(route, {
        game_id: gameId,
        vote_count_by_target:
          submittedTargetId === null ? {} : { [submittedTargetId]: 1 },
        winner_game_character_id: submittedTargetId,
        is_tie: false,
        votes_cast: submittedVoterId === null ? 0 : 1,
        total_voters: 4,
        voting_complete: false,
        submitted_voter_game_character_ids:
          submittedVoterId === null ? [] : [submittedVoterId],
      })
      return
    }
    if (pathname === `/api/games/${gameId}/votes` && method === 'POST') {
      const body = request.postDataJSON() as {
        voter_game_character_id: number
        target_game_character_id: number
      }
      submittedVoterId = body.voter_game_character_id
      submittedTargetId = body.target_game_character_id
      await fulfillJson(route, {
        id: 501,
        game_session_id: gameId,
        voter_game_character_id: submittedVoterId,
        target_game_character_id: submittedTargetId,
        created_at: '2026-10-06T08:02:00Z',
      })
      return
    }
    if (
      pathname === `/api/games/${gameId}/director/analyze` &&
      method === 'POST'
    ) {
      await fulfillJson(route, {
        id: 900,
        game_session_id: gameId,
        pace: 'stalled',
        narrative_risk: 'low',
        recommended_action: 'request_ai_speaker',
        target_game_character_id: 42,
        clue_id: null,
        public_message_id: null,
        reason: '公开讨论节奏偏慢，可请一位角色补充发言。',
        status: 'pending',
        created_at: '2026-10-06T08:02:00Z',
        applied_at: null,
        director_context: {
          script: {
            culprit_character_id: 43,
            characters: [
              {
                is_killer: true,
                private_background: 'PRIVATE_BACKGROUND_SECRET_SENTINEL',
              },
            ],
          },
          marker: 'DIRECTOR_CONTEXT_SECRET_SENTINEL',
        },
        culprit: 'CULPRIT_SECRET_SENTINEL',
        private_background: 'PRIVATE_BACKGROUND_SECRET_SENTINEL',
      })
      return
    }
    if (
      pathname === `/api/games/${gameId}/director/recommendations/900/apply` &&
      method === 'POST'
    ) {
      await fulfillJson(route, {
        recommendation_id: 900,
        status: 'applied',
        reason: '建议已通过规则校验并应用。',
        public_message: null,
        flow_state: null,
      })
      return
    }

    await fulfillJson(
      route,
      { detail: `Unmocked test endpoint: ${method} ${pathname}` },
      404,
    )
  })

  await page.goto('/')
  await expect(page.getByText('后端连接正常')).toBeVisible()
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await expect(
    page.getByRole('heading', { name: '游戏规则与 AI 对话验证' }),
  ).toBeVisible()

  await page.locator('#game-session-select').selectOption(String(gameId))
  await expect(page.locator('.flow-summary-grid')).toContainText('vote')
  await expect(page.locator('.flow-summary-grid').nth(0)).toContainText(
    /1:3[0-9]/,
  )
  await expect(page.locator('.flow-summary-grid')).toContainText(
    /0:2[0-9]|0:30/,
  )
  await expect(page.getByText('公开发言 · 不可用')).toBeVisible()
  await expect(page.getByText('投票 · 允许')).toBeVisible()
  await expect(
    page.getByRole('heading', { name: '投票提交流程' }),
  ).toBeVisible()
  await expect(page.locator('.vote-progress-line')).toContainText('0 / 4 票')

  await page.locator('#debug-voter-select').selectOption('42')
  await page.locator('#debug-target-select').selectOption('43')
  await page.getByRole('button', { name: '提交测试投票' }).click()
  await expect(page.getByText('测试投票已提交。')).toBeVisible()
  await expect(
    page.locator('.vote-tally-row').filter({ hasText: '陈默 · #43' }),
  ).toContainText('1 票')

  await expect(page.getByText('Director 已配置')).toBeVisible()
  await page.getByRole('button', { name: /Analyze Situation/ }).click()
  await expect(page.getByText('request_ai_speaker')).toBeVisible()
  await expect(
    page.getByText('公开讨论节奏偏慢，可请一位角色补充发言。'),
  ).toBeVisible()
  await expect(page.getByText('节奏 Pace')).toBeVisible()
  await expect(page.getByText('叙事风险 Risk')).toBeVisible()
  await expect(page.getByText('角色：许棠')).toBeVisible()

  await page.getByRole('button', { name: /Apply/ }).click()
  await expect(page.getByText('已应用')).toBeVisible()
  await expect(page.getByText('建议已通过规则校验并应用。')).toBeVisible()

  const visibleText = await page.locator('body').innerText()
  expect(visibleText).not.toContain('DirectorContext')
  expect(visibleText).not.toContain('DIRECTOR_CONTEXT_SECRET_SENTINEL')
  expect(visibleText).not.toContain('culprit')
  expect(visibleText).not.toContain('CULPRIT_SECRET_SENTINEL')
  expect(visibleText).not.toContain('private_background')
  expect(visibleText).not.toContain('PRIVATE_BACKGROUND_SECRET_SENTINEL')
})
