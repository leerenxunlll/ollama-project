import { expect, test, type Page, type Route } from '@playwright/test'

const gameId = 95
const humanId = 501

function createRuntimeMocks(
  page: Page,
  initialPhase: string,
  options: { simulateProactiveSpeech?: boolean } = {},
) {
  let currentPhase = initialPhase
  let runtimeStatus: 'not_started' | 'enabled' | 'paused' = 'not_started'
  let phaseReadAcknowledged = false
  let readyPhase: string | null = null
  let tickCount = 0
  let holdNextTick = false
  let failNextTick = false
  let releaseTick: (() => void) | null = null
  const publicMessages: Array<Record<string, unknown>> = []

  const game = () => ({
    id: gameId,
    script_id: 12,
    status: 'in_progress',
    current_phase: currentPhase,
    human_intro_acknowledged_at: '2026-10-12T10:00:00Z',
    created_at: '2026-10-12T10:00:00Z',
    started_at: '2026-10-12T10:00:00Z',
    ended_at: null,
    game_characters: [
      {
        id: humanId,
        character_id: 201,
        controller_type: 'human',
        character: { id: 201, name: '林澈' },
      },
      ...[202, 203, 204].map((characterId, index) => ({
        id: characterId + 300,
        character_id: characterId,
        controller_type: 'ai',
        character: { id: characterId, name: ['许雁', '周序', '叶青'][index] },
      })),
    ],
  })

  const runtime = () => ({
    game_id: gameId,
    game_status: 'in_progress',
    current_phase: currentPhase,
    runtime_status: runtimeStatus,
    phase_read_acknowledged: phaseReadAcknowledged,
    ready_for_phase: readyPhase,
    action_status: 'idle',
    last_tick_at: null,
    last_director_analysis_at:
      publicMessages.length > 0 ? '2026-10-12T10:04:00Z' : null,
    last_proactive_speech_at:
      publicMessages.length > 0 ? '2026-10-12T10:04:01Z' : null,
    last_action_type: publicMessages.length > 0 ? 'proactive_speech' : null,
    last_error_code: null,
    next_check_after_seconds: 10,
    recent_actions: publicMessages.length
      ? [
          {
            id: 88,
            event_type: 'human_public_message',
            action_type: 'proactive_speech',
            execution_status: 'completed',
            reason_code: 'action_applied',
            started_at: '2026-10-12T10:04:00Z',
            completed_at: '2026-10-12T10:04:01Z',
            related_message_id: 802,
            related_recommendation_id: 33,
          },
        ]
      : [],
  })

  const flow = () => ({
    game_id: gameId,
    status: 'in_progress',
    current_phase: currentPhase,
    phase_started_at: '2026-10-12T10:00:00Z',
    elapsed_seconds: 120,
    minimum_duration_seconds: 10,
    remaining_seconds: 0,
    minimum_time_satisfied: true,
    can_investigate: currentPhase.startsWith('investigation'),
    can_discuss: currentPhase.includes('discussion'),
    can_public_speak: !['vote', 'ending'].includes(currentPhase),
    can_vote: currentPhase === 'vote',
    can_advance: true,
    is_finished: false,
    vote_progress: {
      votes_cast: 0,
      total_voters: 4,
      voting_complete: false,
    },
  })

  async function fulfill(route: Route, payload: unknown, status = 200) {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    })
  }

  void page.route('**/api/**', async (route) => {
    const { pathname } = new URL(route.request().url())
    const method = route.request().method()

    if (pathname === '/api/health') {
      await fulfill(route, { status: 'ok', app: 'AI Murder Mystery' })
    } else if (pathname === '/api/scripts') {
      await fulfill(route, [
        {
          id: 12,
          title: '雾港档案',
          summary: '开发测试剧本',
          theme: '悬疑',
          status: 'ready',
        },
      ])
    } else if (pathname === '/api/games' && method === 'GET') {
      await fulfill(route, [game()])
    } else if (pathname === `/api/games/${gameId}`) {
      await fulfill(route, game())
    } else if (pathname === `/api/games/${gameId}/state`) {
      const phases = [
        'intro',
        'act_1',
        'investigation_1',
        'discussion_1',
        'act_2',
        'investigation_2',
        'discussion_2',
        'final_discussion',
        'vote',
        'ending',
      ]
      await fulfill(route, {
        game_id: gameId,
        status: 'in_progress',
        current_phase: currentPhase,
        started_at: '2026-10-12T10:00:00Z',
        ended_at: null,
        next_phase: phases[phases.indexOf(currentPhase) + 1] ?? null,
        can_investigate: currentPhase.startsWith('investigation'),
      })
    } else if (pathname === `/api/games/${gameId}/flow`) {
      await fulfill(route, flow())
    } else if (pathname === `/api/games/${gameId}/votes/result`) {
      await fulfill(route, {
        game_id: gameId,
        vote_count_by_target: {},
        winner_game_character_id: null,
        is_tie: false,
        votes_cast: 0,
        total_voters: 4,
        voting_complete: false,
        submitted_voter_game_character_ids: [],
      })
    } else if (
      pathname === '/api/ai/status' ||
      pathname === '/api/director/status'
    ) {
      await fulfill(route, { configured: true })
    } else if (pathname.startsWith('/api/writer/')) {
      await fulfill(route, { configured: false })
    } else if (pathname === `/api/games/${gameId}/me/character`) {
      await fulfill(route, {
        game_character_id: humanId,
        character_id: 201,
        name: '林澈',
        age: 32,
        identity: '港口档案员',
        public_background: '负责整理档案。',
        private_background: '个人背景。',
        personality: '谨慎',
        speaking_style: '简短',
        personal_goal: '找回记录。',
        personal_history: null,
        relationship_to_victim: null,
        pre_case_experience: null,
        private_secrets: [],
        initial_knowledge: [],
        current_emotion: null,
        current_goal: null,
      })
    } else if (
      pathname === `/api/games/${gameId}/story/public` ||
      pathname === `/api/games/${gameId}/me/story`
    ) {
      const isPublic = pathname.endsWith('/story/public')
      await fulfill(route, [
        {
          chapter_id: isPublic ? 1 : 2,
          title: isPublic ? '公开章节' : '个人章节',
          chapter_order: 1,
          unlock_phase: currentPhase === 'act_1' ? 'act_1' : 'intro',
          content: isPublic
            ? 'PUBLIC_ACT_1_SENTINEL'
            : 'PERSONAL_ACT_1_SENTINEL',
        },
      ])
    } else if (pathname === `/api/games/${gameId}/public-messages`) {
      await fulfill(route, publicMessages)
    } else if (pathname === `/api/games/${gameId}/runtime`) {
      await fulfill(route, runtime())
    } else if (pathname === `/api/games/${gameId}/runtime/start`) {
      runtimeStatus = 'enabled'
      await fulfill(route, runtime())
    } else if (pathname === `/api/games/${gameId}/runtime/pause`) {
      runtimeStatus = 'paused'
      await fulfill(route, runtime())
    } else if (pathname === `/api/games/${gameId}/runtime/acknowledge-phase`) {
      phaseReadAcknowledged = true
      await fulfill(route, {
        game_id: gameId,
        phase: currentPhase,
        acknowledged: true,
        acknowledged_at: '2026-10-12T10:02:00Z',
      })
    } else if (pathname === `/api/games/${gameId}/runtime/ready`) {
      readyPhase = currentPhase
      await fulfill(route, {
        game_id: gameId,
        phase: currentPhase,
        ready: true,
        ready_at: '2026-10-12T10:03:00Z',
      })
    } else if (pathname === `/api/games/${gameId}/runtime/tick`) {
      tickCount += 1
      if (failNextTick) {
        failNextTick = false
        await fulfill(route, { detail: '模拟 Runtime 服务错误' }, 503)
        return
      }
      if (holdNextTick) {
        holdNextTick = false
        await new Promise<void>((resolve) => {
          releaseTick = resolve
        })
      }
      const phaseBefore = currentPhase
      if (options.simulateProactiveSpeech && tickCount === 1) {
        publicMessages.push({
          id: 802,
          game_session_id: gameId,
          sender_game_character_id: 502,
          channel_type: 'public',
          receiver_game_character_id: null,
          content: '我愿意说说当晚我亲眼看到的情况。',
          created_at: '2026-10-12T10:04:01Z',
        })
        await fulfill(route, {
          game_id: gameId,
          runtime_status: runtimeStatus,
          action_type: 'proactive_speech',
          execution_status: 'completed',
          phase_before: phaseBefore,
          phase_after: phaseBefore,
          public_message_id: 802,
          recommendation_id: 33,
          reason_code: 'action_applied',
          next_check_after_seconds: 10,
        })
        return
      }
      if (currentPhase === 'act_1') currentPhase = 'investigation_1'
      await fulfill(route, {
        game_id: gameId,
        runtime_status: runtimeStatus,
        action_type: phaseBefore === 'act_1' ? 'phase_advance' : 'none',
        execution_status: 'completed',
        phase_before: phaseBefore,
        phase_after: currentPhase,
        public_message_id: null,
        recommendation_id: null,
        reason_code:
          phaseBefore === 'act_1' ? 'phase_advanced' : 'no_new_event',
        next_check_after_seconds: 10,
      })
    } else {
      await fulfill(route, { detail: 'Not found' }, 404)
    }
  })

  return {
    get tickCount() {
      return tickCount
    },
    holdNextTick() {
      holdNextTick = true
    },
    failNextTick() {
      failNextTick = true
    },
    releaseTick() {
      releaseTick?.()
    },
  }
}

async function openDevelopmentGame(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await page.locator('#game-session-select').selectOption(String(gameId))
  await expect(
    page.getByRole('region', { name: 'Runtime 控制面板' }),
  ).toBeVisible()
}

test('confirms reading, runs one bounded tick and exposes investigation readiness', async ({
  page,
}) => {
  createRuntimeMocks(page, 'act_1')
  await openDevelopmentGame(page)

  const runtimePanel = page.getByRole('region', {
    name: 'Runtime 控制面板',
  })
  await expect(runtimePanel.getByText('PUBLIC_ACT_1_SENTINEL')).toBeVisible()
  await expect(runtimePanel.getByText('PERSONAL_ACT_1_SENTINEL')).toBeVisible()
  await page.getByRole('button', { name: '确认已阅读' }).click()
  await expect(
    page.getByRole('button', { name: '本阶段已确认阅读' }),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Start Runtime' }).click()
  await expect(
    page.getByRole('status').filter({ hasText: '运行中' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Manual Tick' }).click()

  await expect(
    page.getByRole('button', { name: '结束搜证并继续' }),
  ).toBeVisible()
  await expect(page.getByTestId('runtime-result')).toContainText('阶段已推进')
})

test('auto tick does not overlap and pause stops later ticks', async ({
  page,
}) => {
  await page.clock.install()
  const mocks = createRuntimeMocks(page, 'discussion_1')
  mocks.holdNextTick()
  await openDevelopmentGame(page)
  await page.getByRole('button', { name: 'Start Runtime' }).click()
  await page.getByLabel('Auto Tick（每 10 秒）').check()

  await page.clock.fastForward(10_000)
  await expect.poll(() => mocks.tickCount).toBe(1)
  await page.clock.fastForward(30_000)
  expect(mocks.tickCount).toBe(1)

  mocks.releaseTick()
  await expect(page.getByTestId('runtime-result')).toBeVisible()
  await page.getByRole('button', { name: 'Pause Runtime' }).click()
  await expect(
    page.getByRole('status').filter({ hasText: '已暂停' }),
  ).toBeVisible()
  await page.clock.fastForward(20_000)
  expect(mocks.tickCount).toBe(1)
})

test('a bounded tick displays one simulated AI speech and pause stops ticks', async ({
  page,
}) => {
  await page.clock.install()
  const mocks = createRuntimeMocks(page, 'discussion_1', {
    simulateProactiveSpeech: true,
  })
  await openDevelopmentGame(page)

  const runtimePanel = page.getByRole('region', {
    name: 'Runtime 控制面板',
  })
  await runtimePanel.getByRole('button', { name: 'Start Runtime' }).click()
  await runtimePanel.getByLabel('Auto Tick（每 10 秒）').check()
  await page.clock.fastForward(10_000)

  await expect.poll(() => mocks.tickCount).toBe(1)
  await expect(page.getByTestId('runtime-result')).toContainText('AI 主动发言')

  await page.locator('#public-room-game-select').selectOption(String(gameId))
  await expect(page.getByText('我愿意说说当晚我亲眼看到的情况。')).toBeVisible()
  await runtimePanel.getByRole('button', { name: 'Pause Runtime' }).click()
  await expect(runtimePanel.getByRole('status').first()).toHaveText('已暂停')

  await page.clock.fastForward(20_000)
  expect(mocks.tickCount).toBe(1)
})

test('runtime errors are shown safely in the development panel', async ({
  page,
}) => {
  const mocks = createRuntimeMocks(page, 'discussion_1')
  mocks.failNextTick()
  await openDevelopmentGame(page)
  const runtimePanel = page.getByRole('region', {
    name: 'Runtime 控制面板',
  })
  await runtimePanel.getByRole('button', { name: 'Start Runtime' }).click()
  await runtimePanel.getByRole('button', { name: 'Manual Tick' }).click()

  await expect(runtimePanel.getByRole('alert')).toContainText(
    '模拟 Runtime 服务错误',
  )
})
