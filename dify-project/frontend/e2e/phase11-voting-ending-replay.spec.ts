import { expect, test, type Route } from '@playwright/test'

const gameId = 811
const humanId = 4101
const aiIds = [4102, 4103, 4104]
const characters = [
  {
    id: humanId,
    character_id: 101,
    controller_type: 'human',
    character: { id: 101, name: '林澈' },
  },
  {
    id: aiIds[0],
    character_id: 102,
    controller_type: 'ai',
    character: { id: 102, name: '许棠' },
  },
  {
    id: aiIds[1],
    character_id: 103,
    controller_type: 'ai',
    character: { id: 103, name: '陈默' },
  },
  {
    id: aiIds[2],
    character_id: 104,
    controller_type: 'ai',
    character: { id: 104, name: '周岚' },
  },
]

test('human and AI votes remain private until ending, then expose filtered replay', async ({
  page,
}) => {
  let humanHasVoted = false
  let aiVotesCast = 0
  let finished = false
  let runtimeEnabled = false
  const submittedVotes: Array<{
    voter_game_character_id: number
    target_game_character_id: number
  }> = []

  const game = () => ({
    id: gameId,
    script_id: 12,
    status: finished ? 'finished' : 'in_progress',
    current_phase: finished ? 'ending' : 'vote',
    created_at: '2026-10-15T08:00:00Z',
    started_at: '2026-10-15T08:00:00Z',
    ended_at: finished ? '2026-10-15T08:15:00Z' : null,
    game_characters: characters,
  })

  const voteStatus = () => ({
    game_id: gameId,
    current_phase: finished ? 'ending' : 'vote',
    votes_cast: (humanHasVoted ? 1 : 0) + aiVotesCast,
    total_voters: 4,
    human_has_voted: humanHasVoted,
    ai_characters: characters.slice(1).map((character, index) => ({
      game_character_id: character.id,
      character_name: character.character.name,
      has_voted: aiVotesCast > index,
    })),
    voting_complete: humanHasVoted && aiVotesCast === 3,
  })

  const flowState = () => ({
    game_id: gameId,
    status: finished ? 'finished' : 'in_progress',
    current_phase: finished ? 'ending' : 'vote',
    phase_started_at: '2026-10-15T08:00:00Z',
    elapsed_seconds: 900,
    minimum_duration_seconds: 0,
    remaining_seconds: 0,
    minimum_time_satisfied: true,
    can_investigate: false,
    can_discuss: false,
    can_public_speak: false,
    can_vote: !finished,
    can_advance: false,
    is_finished: finished,
    vote_progress: {
      votes_cast: voteStatus().votes_cast,
      total_voters: 4,
      voting_complete: voteStatus().voting_complete,
    },
  })

  const runtimeState = () => ({
    game_id: gameId,
    game_status: finished ? 'finished' : 'in_progress',
    current_phase: finished ? 'ending' : 'vote',
    runtime_status: runtimeEnabled ? 'enabled' : 'not_started',
    phase_read_acknowledged: false,
    ready_for_phase: null,
    action_status: 'idle',
    last_tick_at: null,
    last_director_analysis_at: null,
    last_proactive_speech_at: null,
    last_action_type: null,
    last_error_code: null,
    next_check_after_seconds: 0,
    recent_actions: [],
  })

  await page.on('dialog', (dialog) => dialog.accept())
  await page.route('**/api/**', async (route: Route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    const method = request.method()
    const fulfill = async (payload: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      })

    if (pathname === '/api/health') {
      await fulfill({ status: 'ok', app: 'AI Murder Mystery' })
    } else if (pathname === '/api/ai/status') {
      await fulfill({ configured: true })
    } else if (pathname === '/api/scripts') {
      await fulfill([
        {
          id: 12,
          title: '雾港来信',
          summary: '测试剧本',
          theme: '悬疑',
          status: 'ready',
        },
      ])
    } else if (pathname === '/api/games' && method === 'GET') {
      await fulfill([game()])
    } else if (pathname === `/api/games/${gameId}` && method === 'GET') {
      await fulfill(game())
    } else if (pathname === `/api/games/${gameId}/state`) {
      await fulfill({
        game_id: gameId,
        status: finished ? 'finished' : 'in_progress',
        current_phase: finished ? 'ending' : 'vote',
        started_at: '2026-10-15T08:00:00Z',
        ended_at: finished ? '2026-10-15T08:15:00Z' : null,
        next_phase: finished ? null : 'ending',
        can_investigate: false,
      })
    } else if (pathname === `/api/games/${gameId}/flow`) {
      await fulfill(flowState())
    } else if (
      pathname === `/api/games/${gameId}/runtime` &&
      method === 'GET'
    ) {
      await fulfill(runtimeState())
    } else if (pathname === `/api/games/${gameId}/runtime/start`) {
      runtimeEnabled = true
      await fulfill(runtimeState())
    } else if (pathname === `/api/games/${gameId}/runtime/tick`) {
      const voterId = aiIds[aiVotesCast]
      aiVotesCast += 1
      submittedVotes.push({
        voter_game_character_id: voterId,
        target_game_character_id: humanId,
      })
      if (aiVotesCast === 3 && humanHasVoted) finished = true
      await fulfill({
        game_id: gameId,
        runtime_status: 'enabled',
        action_type: 'ai_vote',
        execution_status: 'completed',
        phase_before: finished ? 'vote' : 'vote',
        phase_after: finished ? 'ending' : 'vote',
        public_message_id: null,
        vote_id: 5000 + aiVotesCast,
        recommendation_id: null,
        reason_code: finished ? 'all_votes_cast' : 'ai_vote_cast',
        next_check_after_seconds: 0,
      })
    } else if (pathname === `/api/games/${gameId}/vote/status`) {
      await fulfill(voteStatus())
    } else if (pathname === '/api/ai/vote/status') {
      await fulfill({ configured: true })
    } else if (pathname === `/api/games/${gameId}/votes` && method === 'POST') {
      const payload = request.postDataJSON() as {
        voter_game_character_id: number
        target_game_character_id: number
      }
      humanHasVoted = true
      submittedVotes.push(payload)
      await fulfill({
        id: 5001,
        game_session_id: gameId,
        ...payload,
        created_at: '2026-10-15T08:01:00Z',
      })
    } else if (pathname === `/api/games/${gameId}/me/character`) {
      await fulfill({ detail: 'No player card in this mock' }, 404)
    } else if (pathname === `/api/games/${gameId}/public-messages`) {
      await fulfill([])
    } else if (pathname === '/api/director/status') {
      await fulfill({ configured: false })
    } else if (
      pathname === '/api/writer/status' ||
      pathname === '/api/writer/quality/status'
    ) {
      await fulfill({ configured: false })
    } else if (pathname === `/api/games/${gameId}/ending`) {
      await fulfill({
        game_id: gameId,
        script_id: 12,
        culprit_game_character_id: aiIds[0],
        culprit_name: '许棠',
        vote_result: 'culprit_identified',
        accused_game_character_id: aiIds[0],
        is_tie: false,
        human_vote_target_id: aiIds[0],
        human_identified_culprit: true,
        case_outcome: 'culprit_identified',
        ending_narrative: '真相终于揭晓。',
        resolved_at: '2026-10-15T08:15:00Z',
        truth: {
          culprit_role_key: 'role_2',
          victim: '钟表匠',
          motive: '守住秘密',
          method: '投毒',
          crime_time: '午夜',
          crime_location: '钟楼',
          case_summary: '案件真相摘要。',
          key_causal_facts: ['钥匙留下了痕迹。'],
        },
        canonical_timeline: [],
        key_clues: [],
        votes: submittedVotes.map((vote, index) => ({
          vote_id: 5001 + index,
          voter_game_character_id: vote.voter_game_character_id,
          voter_name:
            characters.find(
              (character) => character.id === vote.voter_game_character_id,
            )?.character.name ?? '',
          target_game_character_id: vote.target_game_character_id,
          target_name:
            characters.find(
              (character) => character.id === vote.target_game_character_id,
            )?.character.name ?? '',
          reason: null,
          created_at: '2026-10-15T08:01:00Z',
        })),
      })
    } else if (pathname === `/api/games/${gameId}/replay`) {
      await fulfill({
        game_id: gameId,
        started_at: '2026-10-15T08:00:00Z',
        ended_at: '2026-10-15T08:15:00Z',
        events: [
          {
            event_id: 'message:1',
            event_type: 'message',
            timestamp: '2026-10-15T08:10:00Z',
            phase: 'final_discussion',
            actor_game_character_id: humanId,
            actor_name: '林澈',
            target_game_character_id: null,
            target_name: null,
            visibility: 'public',
            content: '请解释你昨晚的行踪。',
            inner_os: null,
            emotion: null,
            intent: null,
            memory_importance: null,
            subjective: false,
            related_message_id: 1,
            related_clue_id: null,
            related_vote_id: null,
          },
          {
            event_id: 'thought:1',
            event_type: 'character_thought',
            timestamp: '2026-10-15T08:10:01Z',
            phase: 'final_discussion',
            actor_game_character_id: aiIds[0],
            actor_name: '许棠',
            target_game_character_id: null,
            target_name: null,
            visibility: 'god',
            content: null,
            inner_os: '她注意到我的迟疑。',
            emotion: 'nervous',
            intent: 'deflect',
            memory_importance: null,
            subjective: false,
            related_message_id: 2,
            related_clue_id: null,
            related_vote_id: null,
          },
          {
            event_id: 'vote:1',
            event_type: 'vote',
            timestamp: '2026-10-15T08:14:00Z',
            phase: 'vote',
            actor_game_character_id: humanId,
            actor_name: '林澈',
            target_game_character_id: aiIds[0],
            target_name: '许棠',
            visibility: 'god',
            content: '林澈 → 许棠',
            inner_os: null,
            emotion: null,
            intent: null,
            memory_importance: null,
            subjective: false,
            related_message_id: null,
            related_clue_id: null,
            related_vote_id: 5001,
          },
        ],
      })
    } else {
      await fulfill({ detail: `Unmocked ${method} ${pathname}` }, 404)
    }
  })

  await page.goto('/')
  await expect(page.getByText('后端连接正常')).toBeVisible()
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await page.locator('#game-session-select').selectOption(String(gameId))

  await expect(page.getByRole('heading', { name: '最终投票' })).toBeVisible()
  await expect(page.getByText('已完成 0 / 4 票')).toBeVisible()
  await expect(page.locator('#human-vote-target')).toBeEnabled()
  await page.locator('#human-vote-target').selectOption(String(aiIds[0]))
  await page.getByRole('button', { name: '确认投票' }).click()
  await expect(page.getByText('此票不可撤销。')).toBeVisible()
  expect(submittedVotes).toEqual([
    { voter_game_character_id: humanId, target_game_character_id: aiIds[0] },
  ])
  await expect(page.getByText('已完成 1 / 4 票')).toBeVisible()

  const pageBeforeResolution = await page.locator('body').innerText()
  expect(pageBeforeResolution).not.toContain('AI → 许棠')
  expect(pageBeforeResolution).not.toContain('领先嫌疑人')

  await page.getByRole('button', { name: 'Start Runtime' }).click()
  for (let index = 0; index < 3; index += 1) {
    await page.getByRole('button', { name: 'Manual Tick' }).click()
    await expect(page.getByTestId('runtime-result')).toContainText('AI 投票')
    expect(
      submittedVotes.filter((vote) => vote.voter_game_character_id !== humanId),
    ).toHaveLength(index + 1)
  }
  expect(submittedVotes.map((vote) => vote.voter_game_character_id)).toEqual([
    humanId,
    ...aiIds,
  ])
  await expect(page.locator('.session-meta')).toContainText('状态 已结束')

  await page.getByRole('button', { name: '揭晓结局' }).click()
  await expect(page.getByText('真相终于揭晓。')).toBeVisible()
  await expect(
    page.locator('.ending-content').getByText('凶手：许棠'),
  ).toBeVisible()
  await page.getByRole('button', { name: '查看完整回放' }).click()
  await expect(page.getByText('内心 OS：她注意到我的迟疑。')).toBeVisible()
  await expect(page.getByText('请解释你昨晚的行踪。')).toBeVisible()

  const replay = page.locator('.replay-content')
  await replay.getByLabel('阶段').selectOption('vote')
  await expect(replay.getByText('林澈 → 许棠')).toBeVisible()
  await expect(replay.getByText('内心 OS：她注意到我的迟疑。')).toHaveCount(0)
  await replay.getByLabel('阶段').selectOption('all')
  await replay
    .locator('.replay-filters label')
    .nth(1)
    .locator('select')
    .selectOption(String(aiIds[0]))
  await expect(replay.getByText('内心 OS：她注意到我的迟疑。')).toBeVisible()
  await replay.getByLabel('事件').selectOption('character_thought')
  await expect(replay.getByText('请解释你昨晚的行踪。')).toHaveCount(0)
})
