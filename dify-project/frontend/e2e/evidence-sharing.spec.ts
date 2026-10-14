import { expect, test } from '@playwright/test'

test('investigates, privately shares, and publicly discloses a canonical clue', async ({
  page,
  request,
}) => {
  test.setTimeout(90_000)

  const scriptsResponse = await request.get('/api/scripts')
  expect(scriptsResponse.ok()).toBeTruthy()
  const scripts = (await scriptsResponse.json()) as Array<{
    id: number
    title: string
    status: string
  }>
  const readyScript = scripts.find(
    (script) =>
      script.status === 'ready' && script.title === '开发样例：雾港档案',
  )
  expect(
    readyScript,
    '先运行 `PYTHONPATH=backend python -m app.seed`',
  ).toBeDefined()

  const createResponse = await request.post('/api/games', {
    data: { script_id: readyScript?.id },
  })
  expect(createResponse.status()).toBe(201)
  const createdGame = (await createResponse.json()) as {
    id: number
    game_characters: Array<{ id: number }>
  }
  const gameId = createdGame.id
  const humanId = createdGame.game_characters[0].id
  const aiIds = createdGame.game_characters.slice(1).map(({ id }) => id)

  expect(
    (
      await request.post(`/api/games/${gameId}/select-character`, {
        data: { game_character_id: humanId },
      })
    ).ok(),
  ).toBeTruthy()
  expect(
    (await request.post(`/api/games/${gameId}/me/acknowledge-intro`)).ok(),
  ).toBeTruthy()
  expect((await request.post(`/api/games/${gameId}/start`)).ok()).toBeTruthy()

  await page.waitForTimeout(10_200)
  const introAdvance = await request.post(`/api/games/${gameId}/advance-phase`)
  expect(introAdvance.ok()).toBeTruthy()
  expect((await introAdvance.json()).current_phase).toBe('act_1')

  await page.waitForTimeout(10_200)
  const actOneAdvance = await request.post(`/api/games/${gameId}/advance-phase`)
  expect(actOneAdvance.ok()).toBeTruthy()
  expect((await actOneAdvance.json()).current_phase).toBe('investigation_1')

  await page.goto('/')
  await expect(page.getByText('后端连接正常')).toBeVisible()
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await page.locator('#game-session-select').selectOption(String(gameId))
  await expect(
    page.getByRole('region', { name: '搜证与线索分享' }),
  ).toBeVisible()
  await expect(page.getByRole('combobox', { name: '调查地点' })).toBeVisible()

  await page.getByRole('button', { name: '调查地点' }).click()
  await expect(
    page.getByRole('status').filter({ hasText: '发现线索：' }),
  ).toBeVisible()
  const myCluesResponse = await request.get(`/api/games/${gameId}/me/clues`)
  expect(myCluesResponse.ok()).toBeTruthy()
  const myClues = await myCluesResponse.json()
  expect(myClues.acquired_clues).toHaveLength(1)
  const clueId = myClues.acquired_clues[0].clue_id as number
  const clueName = myClues.acquired_clues[0].name as string
  const firstSearchLocation = myClues.acquired_clues[0].location as string

  const repeatedSearch = await request.post(
    `/api/games/${gameId}/investigation/search`,
    { data: { location: firstSearchLocation } },
  )
  expect(repeatedSearch.ok()).toBeTruthy()
  const repeatedResult = await repeatedSearch.json()
  if (repeatedResult.found) {
    expect(repeatedResult.clue.id).not.toBe(clueId)
  }
  const afterRepeat = await (
    await request.get(`/api/games/${gameId}/me/clues`)
  ).json()
  expect(
    afterRepeat.acquired_clues.filter(
      (clue: { clue_id: number }) => clue.clue_id === clueId,
    ),
  ).toHaveLength(1)

  await page
    .getByRole('combobox', { name: '选择要分享的线索' })
    .selectOption(String(clueId))
  await page
    .getByRole('combobox', { name: '分享给角色' })
    .selectOption(String(aiIds[0]))
  await page.getByRole('button', { name: '正式分享线索' }).click()
  await expect(
    page.getByRole('status').filter({ hasText: '已私下分享' }),
  ).toBeVisible()

  const recipientContextResponse = await request.get(
    `/api/games/${gameId}/characters/${aiIds[0]}/context`,
  )
  const otherContextResponse = await request.get(
    `/api/games/${gameId}/characters/${aiIds[1]}/context`,
  )
  expect(recipientContextResponse.ok()).toBeTruthy()
  expect(otherContextResponse.ok()).toBeTruthy()
  const recipientContext = await recipientContextResponse.json()
  const otherContext = await otherContextResponse.json()
  expect(
    recipientContext.known_clues.map(
      (clue: { clue_id: number }) => clue.clue_id,
    ),
  ).toContain(clueId)
  expect(
    otherContext.known_clues.map((clue: { clue_id: number }) => clue.clue_id),
  ).not.toContain(clueId)
  const publicMessagesResponse = await request.get(
    `/api/games/${gameId}/public-messages`,
  )
  expect(await publicMessagesResponse.text()).not.toContain(clueName)

  await page.getByRole('combobox', { name: '分享范围' }).selectOption('public')
  await page.getByRole('button', { name: '正式分享线索' }).click()
  await expect(
    page.getByRole('status').filter({ hasText: '已向所有角色公开' }),
  ).toBeVisible()
  const publicCluesResponse = await request.get(
    `/api/games/${gameId}/clues/public`,
  )
  const publicClues = await publicCluesResponse.json()
  expect(
    publicClues.clues.map((clue: { clue_id: number }) => clue.clue_id),
  ).toContain(clueId)
})
