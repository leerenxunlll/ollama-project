import { expect, test, type Page, type Route } from '@playwright/test'
import type { WriterBlueprint, WriterDraft, WriterPhase } from '../src/api'

const draftId = 91
const request = {
  theme: '封闭空间悬疑',
  era: '现代',
  atmosphere: '冷峻',
  difficulty: 'medium',
  custom_requirements: '因果链清楚',
}

const blueprint: WriterBlueprint = {
  script_metadata: {
    title: '雾钟档案',
    summary: '暴风雪夜，旧疗养院发生一起离奇命案。',
    theme: request.theme,
    era: request.era,
    atmosphere: request.atmosphere,
    difficulty: request.difficulty,
  },
  case_truth: {
    culprit_role_key: 'role_2',
    victim: '顾闻舟，疗养院管理人',
    motive: '阻止旧档案公开',
    method: '利用停电掩护投药',
    crime_time: '21:10 至 21:20',
    crime_location: '档案室',
    case_summary: '凶手利用熟悉环境制造不在场假象。',
    key_causal_facts: ['旧档案被调换', '备用电源遭关闭', '凶手熟悉药物流程'],
  },
  canonical_timeline: Array.from({ length: 4 }, (_, index) => ({
    event_key: `event_${index + 1}`,
    time: `21:0${index}`,
    location: '疗养院档案室',
    description: `事件 ${index + 1}。`,
    involved_role_keys: ['role_1'],
    is_public_knowledge: false,
  })),
  characters: ['role_1', 'role_2', 'role_3', 'role_4'].map(
    (role_key, index) => ({
      role_key,
      name: `角色${index + 1}`,
      age: null,
      identity: '旧疗养院相关人员',
      public_background: '公开背景。',
      private_background: '私人背景。',
      personality: '谨慎。',
      speaking_style: '简洁。',
      personal_goal: '查清旧档案。',
      personal_history: '曾亲历一次与案件有关的旧事。',
      relationship_to_victim: '与死者相识。',
      pre_case_experience: '案发前曾回到疗养院。',
      private_secrets: ['知道一处被封存的档案柜。'],
      initial_knowledge: ['知道当晚有短暂停电。'],
    }),
  ),
  clues: [],
}

function makePack(phase: 'intro' | 'act_1' | 'act_2') {
  const chapterOrder = { intro: 1, act_1: 2, act_2: 3 }[phase]
  const chapterLabels = {
    intro: '序章',
    act_1: '第一幕',
    act_2: '第二幕',
  }
  return {
    phase,
    shared_chapter: {
      title: `${chapterLabels[phase]}公共章节`,
      content: '走廊的旧钟停在九点十三分。\n没有人承认听见过钟声。',
      chapter_order: chapterOrder,
      unlock_phase: phase,
    },
    character_chapters: ['role_1', 'role_2', 'role_3', 'role_4'].map(
      (role_key, index) => ({
        role_key,
        title: `角色${index + 1}私人章节`,
        content: `角色${index + 1}回忆起一段具体经历。`,
        chapter_order: chapterOrder,
        unlock_phase: phase,
      }),
    ),
  }
}

function makeDraft(): WriterDraft {
  return {
    id: draftId,
    status: 'created',
    content_revision: 1,
    publication_status: 'unpublished',
    published_script_id: null,
    generation_request: request,
    blueprint: null,
    chapter_packs: {},
    step_durations_seconds: {},
    failed_step: null,
    last_error_type: null,
    completed_steps: [],
  }
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function openDevelopment(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const { pathname } = new URL(route.request().url())
    const method = route.request().method()
    if (pathname === '/api/health') {
      await json(route, { status: 'ok', app: 'AI Murder Mystery' })
    } else if (pathname === '/api/scripts') {
      await json(route, [])
    } else if (pathname === '/api/games') {
      await json(route, [])
    } else if (
      pathname === '/api/ai/status' ||
      pathname === '/api/director/status'
    ) {
      await json(route, { configured: false })
    } else if (pathname === '/api/writer/status') {
      await json(route, { configured: true })
    } else if (pathname === '/api/writer/quality/status') {
      await json(route, { configured: false })
    } else if (pathname === '/api/writer/drafts' && method === 'POST') {
      expect(route.request().postDataJSON()).toEqual(request)
      await json(route, makeDraft(), 201)
    } else if (
      pathname === `/api/writer/drafts/${draftId}/generate-blueprint`
    ) {
      const value = makeDraft()
      value.status = 'blueprint_ready'
      value.blueprint = blueprint
      value.completed_steps = ['blueprint']
      await json(route, value)
    } else if (
      pathname.startsWith(
        `/api/writer/drafts/${draftId}/generate-chapter-pack/`,
      )
    ) {
      const phase = pathname.split('/').at(-1) as WriterPhase
      const order = { intro: 1, act_1: 2, act_2: 3 }[phase]
      const packs = Object.fromEntries(
        (['intro', 'act_1', 'act_2'] as const)
          .filter((name) => ({ intro: 1, act_1: 2, act_2: 3 })[name] <= order)
          .map((name) => [name, makePack(name)]),
      )
      const value = makeDraft()
      value.status = phase === 'act_2' ? 'draft_complete' : `${phase}_ready`
      value.blueprint = blueprint
      value.chapter_packs = packs
      value.completed_steps = ['blueprint', ...Object.keys(packs)]
      await json(route, value)
    } else if (pathname === `/api/writer/drafts/${draftId}`) {
      const value = makeDraft()
      value.blueprint = blueprint
      value.status = 'blueprint_ready'
      value.completed_steps = ['blueprint']
      await json(route, value)
    } else {
      await json(route, { detail: 'Not found' }, 404)
    }
  })

  await page.goto('/')
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await expect(
    page.getByRole('heading', { name: 'AI Writer · Script Draft' }),
  ).toBeVisible()
}

test('creates and previews a four-stage Script Draft without publishing it', async ({
  page,
}) => {
  await openDevelopment(page)
  await expect(page.getByText('Writer 已配置')).toBeVisible()

  await page.getByLabel('氛围').fill(request.atmosphere)
  await page.getByLabel('自定义要求').fill(request.custom_requirements)
  await page.getByRole('button', { name: /Create Draft/ }).click()
  await expect(page.getByText(`Draft #${draftId} · created`)).toBeVisible()
  await page.getByRole('button', { name: 'Generate Blueprint' }).click()
  await expect(page.getByText('雾钟档案')).toBeVisible()
  await expect(
    page.getByText('DEVELOPMENT ONLY / SPOILERS · 案件真相'),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Generate 序章' }).click()
  await expect(page.getByText('该阶段章节尚未生成。')).toHaveCount(0)
  await page.getByLabel('阶段').first().selectOption('intro')
  await page.getByLabel('阅读视角').selectOption('public')
  await expect(page.getByText('走廊的旧钟停在九点十三分。')).toBeVisible()
  await page.getByRole('button', { name: 'Generate 第一幕' }).click()
  await page.getByRole('button', { name: 'Generate 第二幕' }).click()
  await expect(
    page.getByText(`Draft #${draftId} · draft_complete`),
  ).toBeVisible()
})

test('keeps generated blueprint visible after chapter-pack failure', async ({
  page,
}) => {
  let chapterAttempt = 0
  await page.route('**/api/**', async (route: Route) => {
    const { pathname } = new URL(route.request().url())
    const method = route.request().method()
    if (pathname === '/api/health') {
      await json(route, { status: 'ok', app: 'AI Murder Mystery' })
    } else if (pathname === '/api/scripts' || pathname === '/api/games') {
      await json(route, [])
    } else if (
      pathname === '/api/ai/status' ||
      pathname === '/api/director/status'
    ) {
      await json(route, { configured: false })
    } else if (pathname === '/api/writer/status') {
      await json(route, { configured: true })
    } else if (pathname === '/api/writer/quality/status') {
      await json(route, { configured: false })
    } else if (pathname === '/api/writer/drafts' && method === 'POST') {
      await json(route, makeDraft(), 201)
    } else if (pathname.endsWith('/generate-blueprint')) {
      const value = makeDraft()
      value.status = 'blueprint_ready'
      value.blueprint = blueprint
      value.completed_steps = ['blueprint']
      await json(route, value)
    } else if (pathname.endsWith('/generate-chapter-pack/intro')) {
      chapterAttempt += 1
      if (chapterAttempt === 1) {
        await json(route, { detail: 'Writer Dify timed out' }, 504)
      } else {
        const value = makeDraft()
        value.status = 'intro_ready'
        value.blueprint = blueprint
        value.chapter_packs = { intro: makePack('intro') }
        value.completed_steps = ['blueprint', 'intro']
        await json(route, value)
      }
    } else if (pathname === `/api/writer/drafts/${draftId}`) {
      const value = makeDraft()
      value.status = 'generation_failed'
      value.blueprint = blueprint
      value.failed_step = 'intro'
      value.last_error_type = 'dify_timeout'
      value.completed_steps = ['blueprint']
      await json(route, value)
    } else {
      await json(route, { detail: 'Not found' }, 404)
    }
  })

  await page.goto('/')
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await page.getByRole('button', { name: /Create Draft/ }).click()
  await page.getByRole('button', { name: 'Generate Blueprint' }).click()
  await page.getByRole('button', { name: 'Generate 序章' }).click()
  await expect(page.getByRole('alert')).toContainText('Writer Dify timed out')
  await expect(page.getByText('雾钟档案')).toBeVisible()
  await expect(page.getByText('失败步骤：intro（dify_timeout）')).toBeVisible()
  await page.getByRole('button', { name: '恢复/重试' }).click()
  await expect(page.getByText('序章公共章节')).toBeVisible()
})
