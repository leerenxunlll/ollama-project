import { expect, test, type Route } from '@playwright/test'

const gameId = 88
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

const characters = [
  {
    id: 101,
    name: '林澈',
    identity: '港口档案员',
    age: 32,
    public_background: '负责整理港区档案。',
    personality: '谨慎',
    speaking_style: '简短',
  },
  {
    id: 102,
    name: '许棠',
    identity: '记者',
    age: 29,
    public_background: '长期调查港务署。',
    personality: '敏锐',
    speaking_style: '直接',
  },
  {
    id: 103,
    name: '陈默',
    identity: '医生',
    age: 41,
    public_background: '曾为港区居民提供医疗服务。',
    personality: '冷静',
    speaking_style: '克制',
  },
  {
    id: 104,
    name: '周岚',
    identity: '船务经理',
    age: 36,
    public_background: '管理旧港的货运调度。',
    personality: '圆滑',
    speaking_style: '委婉',
  },
]

const chapters = {
  public: [
    {
      chapter_id: 1,
      title: '暴雨夜',
      chapter_order: 1,
      unlock_phase: 'intro',
      content: '暴雨封锁了雾港。\n旧仓库里发生了一起命案。',
    },
    {
      chapter_id: 2,
      title: '档案重启',
      chapter_order: 2,
      unlock_phase: 'act_1',
      content: '清晨，警方公布初步死亡时间。',
    },
    {
      chapter_id: 3,
      title: '第二封信',
      chapter_order: 3,
      unlock_phase: 'act_2',
      content: '一封新的来信打破了沉默。',
    },
  ],
  personal: [
    {
      chapter_id: 11,
      title: '林澈的来港缘由',
      chapter_order: 1,
      unlock_phase: 'intro',
      content: 'PRIVATE_INTRO_SENTINEL\n你收到一封没有署名的旧信。',
    },
    {
      chapter_id: 12,
      title: '没有寄出的副本',
      chapter_order: 2,
      unlock_phase: 'act_1',
      content: 'PRIVATE_ACT_1_SENTINEL',
    },
    {
      chapter_id: 13,
      title: '迟到的回信',
      chapter_order: 3,
      unlock_phase: 'act_2',
      content: 'PRIVATE_ACT_2_SENTINEL',
    },
  ],
}

let gameStatus = 'waiting_for_character_selection'
let currentPhase = 'intro'
let humanCharacterId: number | null = null
let acknowledgedAt: string | null = null

function currentGame() {
  return {
    id: gameId,
    script_id: 12,
    status: gameStatus,
    current_phase: currentPhase,
    human_intro_acknowledged_at: acknowledgedAt,
    created_at: '2026-10-08T00:00:00Z',
    started_at: gameStatus === 'in_progress' ? '2026-10-08T00:01:00Z' : null,
    ended_at: null,
    game_characters: characters.map((character, index) => ({
      id: character.id,
      character_id: character.id,
      controller_type:
        character.id === humanCharacterId
          ? 'human'
          : humanCharacterId === null
            ? null
            : 'ai',
      character: { id: character.id, name: character.name },
    })),
  }
}

function phaseRank(phase: string) {
  return phases.indexOf(phase)
}

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}

test('reads only unlocked public and personal script chapters', async ({
  page,
}) => {
  gameStatus = 'waiting_for_character_selection'
  currentPhase = 'intro'
  humanCharacterId = null
  acknowledgedAt = null

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
          title: '雾港档案',
          summary: '一段被暴雨封存的旧案。',
          theme: '悬疑',
          status: 'ready',
        },
      ])
      return
    }
    if (pathname === '/api/games' && method === 'GET') {
      await fulfillJson(
        route,
        gameStatus === 'waiting_for_character_selection' ? [] : [currentGame()],
      )
      return
    }
    if (pathname === '/api/games' && method === 'POST') {
      gameStatus = 'waiting_for_character_selection'
      await fulfillJson(route, currentGame(), 201)
      return
    }
    if (pathname === '/api/ai/status' && method === 'GET') {
      await fulfillJson(route, { configured: false })
      return
    }
    if (pathname === '/api/director/status' && method === 'GET') {
      await fulfillJson(route, { configured: false })
      return
    }
    if (pathname === '/api/writer/status' && method === 'GET') {
      await fulfillJson(route, { configured: false })
      return
    }
    if (pathname === `/api/games/${gameId}` && method === 'GET') {
      await fulfillJson(route, currentGame())
      return
    }
    if (pathname === `/api/games/${gameId}/state` && method === 'GET') {
      const phaseIndex = phaseRank(currentPhase)
      await fulfillJson(route, {
        game_id: gameId,
        status: gameStatus,
        current_phase: currentPhase,
        started_at: currentGame().started_at,
        ended_at: null,
        next_phase: phases[phaseIndex + 1] ?? null,
        can_investigate: false,
      })
      return
    }
    if (pathname === `/api/games/${gameId}/flow` && method === 'GET') {
      await fulfillJson(route, {
        game_id: gameId,
        status: gameStatus,
        current_phase: currentPhase,
        phase_started_at: currentGame().started_at,
        elapsed_seconds: 120,
        minimum_duration_seconds: 10,
        remaining_seconds: 0,
        minimum_time_satisfied: true,
        can_investigate: false,
        can_discuss: false,
        can_public_speak: true,
        can_vote: false,
        can_advance: true,
        is_finished: false,
        vote_progress: {
          votes_cast: 0,
          total_voters: 4,
          voting_complete: false,
        },
      })
      return
    }
    if (pathname === `/api/games/${gameId}/votes/result` && method === 'GET') {
      await fulfillJson(route, {
        game_id: gameId,
        vote_count_by_target: {},
        winner_game_character_id: null,
        is_tie: false,
        votes_cast: 0,
        total_voters: 4,
        voting_complete: false,
        submitted_voter_game_character_ids: [],
      })
      return
    }
    if (
      pathname === `/api/games/${gameId}/characters/selectable` &&
      method === 'GET'
    ) {
      await fulfillJson(
        route,
        characters.map((character) => ({
          game_character_id: character.id,
          character_id: character.id,
          name: character.name,
          age: character.age,
          identity: character.identity,
          public_background: character.public_background,
          personality: character.personality,
          speaking_style: character.speaking_style,
        })),
      )
      return
    }
    if (
      pathname === `/api/games/${gameId}/select-character` &&
      method === 'POST'
    ) {
      humanCharacterId = request.postDataJSON().game_character_id
      gameStatus = 'ready'
      await fulfillJson(route, currentGame())
      return
    }
    if (pathname === `/api/games/${gameId}/me/character` && method === 'GET') {
      const character = characters.find((item) => item.id === humanCharacterId)
      await fulfillJson(route, {
        game_character_id: humanCharacterId,
        character_id: humanCharacterId,
        name: character?.name,
        age: character?.age,
        identity: character?.identity,
        public_background: character?.public_background,
        personality: character?.personality,
        speaking_style: character?.speaking_style,
        private_background: '角色私有背景。',
        personal_goal: '找出旧案中的矛盾。',
        current_emotion: null,
        current_goal: null,
      })
      return
    }
    if (pathname === `/api/games/${gameId}/story/public` && method === 'GET') {
      const unlocked = chapters.public.filter(
        (chapter) => phaseRank(chapter.unlock_phase) <= phaseRank(currentPhase),
      )
      await fulfillJson(
        route,
        gameStatus === 'waiting_for_character_selection' ? [] : unlocked,
      )
      return
    }
    if (pathname === `/api/games/${gameId}/me/story` && method === 'GET') {
      const unlocked = chapters.personal.filter(
        (chapter) => phaseRank(chapter.unlock_phase) <= phaseRank(currentPhase),
      )
      await fulfillJson(
        route,
        gameStatus === 'waiting_for_character_selection' ? [] : unlocked,
      )
      return
    }
    if (
      pathname === `/api/games/${gameId}/me/acknowledge-intro` &&
      method === 'POST'
    ) {
      acknowledgedAt ??= '2026-10-08T00:02:00Z'
      await fulfillJson(route, {
        game_id: gameId,
        acknowledged: true,
        acknowledged_at: acknowledgedAt,
      })
      return
    }
    if (pathname === `/api/games/${gameId}/start` && method === 'POST') {
      gameStatus = 'in_progress'
      currentPhase = 'intro'
      await fulfillJson(route, {
        game_id: gameId,
        status: gameStatus,
        current_phase: currentPhase,
        started_at: currentGame().started_at,
        ended_at: null,
        next_phase: 'act_1',
        can_investigate: false,
      })
      return
    }
    if (
      pathname === `/api/games/${gameId}/advance-phase` &&
      method === 'POST'
    ) {
      currentPhase = phases[phaseRank(currentPhase) + 1] ?? currentPhase
      await fulfillJson(route, {
        game_id: gameId,
        status: gameStatus,
        current_phase: currentPhase,
        started_at: currentGame().started_at,
        ended_at: null,
        next_phase: phases[phaseRank(currentPhase) + 1] ?? null,
        can_investigate: false,
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
  await page.getByRole('button', { name: '创建游戏' }).click()
  await expect(page.getByRole('heading', { name: '林澈' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '许棠' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '陈默' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '周岚' })).toBeVisible()
  await expect(page.getByText('PRIVATE_INTRO_SENTINEL')).not.toBeVisible()
  await page.getByRole('button', { name: '选择此角色' }).first().click()

  const storyReader = page.getByRole('region', { name: '已解锁剧本阅读' })
  await expect(storyReader.getByRole('tab', { name: '公共剧情' })).toBeVisible()
  await expect(
    storyReader.getByRole('heading', { name: '暴雨夜' }),
  ).toBeVisible()
  await expect(storyReader.getByText('暴雨封锁了雾港。')).toBeVisible()
  await expect(
    storyReader.getByText('PRIVATE_INTRO_SENTINEL'),
  ).not.toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Start Game · 开始游戏' }),
  ).toBeDisabled()

  await storyReader.getByRole('tab', { name: '个人剧情' }).click()
  await expect(
    storyReader.getByRole('heading', { name: '林澈的来港缘由' }),
  ).toBeVisible()
  await expect(storyReader.getByText('PRIVATE_INTRO_SENTINEL')).toBeVisible()
  await expect(
    storyReader.getByText('PRIVATE_ACT_1_SENTINEL'),
  ).not.toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Start Game · 开始游戏' }),
  ).toBeDisabled()

  await page
    .getByRole('region', { name: '开发数据验证' })
    .getByRole('button', { name: '确认已阅读' })
    .click()
  await expect(page.getByText('序章已确认阅读')).toBeVisible()
  await page.getByRole('button', { name: 'Start Game · 开始游戏' }).click()
  await expect(page.getByText(/当前阶段：序章/)).toBeVisible()

  await page.getByRole('button', { name: /Advance Phase/ }).click()
  await storyReader.getByRole('tab', { name: '公共剧情' }).click()
  await expect(
    storyReader.getByRole('heading', { name: '档案重启' }),
  ).toBeVisible()
  await storyReader.getByLabel('选择章节').selectOption('1')
  await expect(
    storyReader.getByRole('heading', { name: '暴雨夜' }),
  ).toBeVisible()
  await storyReader.getByLabel('选择章节').selectOption('2')
  await expect(
    storyReader.getByRole('heading', { name: '档案重启' }),
  ).toBeVisible()
  await storyReader.getByRole('tab', { name: '个人剧情' }).click()
  await expect(
    storyReader.getByRole('heading', { name: '没有寄出的副本' }),
  ).toBeVisible()
  await storyReader.getByLabel('选择章节').selectOption('11')
  await expect(
    storyReader.getByRole('heading', { name: '林澈的来港缘由' }),
  ).toBeVisible()
  await storyReader.getByLabel('选择章节').selectOption('12')
  await expect(
    storyReader.getByRole('heading', { name: '没有寄出的副本' }),
  ).toBeVisible()
  await expect(storyReader.getByText('PRIVATE_ACT_1_SENTINEL')).toBeVisible()
  await expect(
    storyReader.getByText('PRIVATE_ACT_2_SENTINEL'),
  ).not.toBeVisible()

  await storyReader.getByRole('tab', { name: '公共剧情' }).click()
  await page.getByRole('button', { name: /Advance Phase/ }).click()
  await page.getByRole('button', { name: /Advance Phase/ }).click()
  await page.getByRole('button', { name: /Advance Phase/ }).click()
  await expect(
    storyReader.getByRole('heading', { name: '第二封信' }),
  ).toBeVisible()
  await storyReader.getByRole('tab', { name: '个人剧情' }).click()
  await expect(
    storyReader.getByRole('heading', { name: '迟到的回信' }),
  ).toBeVisible()
  await expect(storyReader.getByText('PRIVATE_ACT_2_SENTINEL')).toBeVisible()
})
