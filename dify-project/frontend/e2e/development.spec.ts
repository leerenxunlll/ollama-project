import { expect, test } from '@playwright/test'

test('opens Development and reads an AI character debug state', async ({
  page,
  request,
}) => {
  const scriptsResponse = await request.get('/api/scripts')
  expect(scriptsResponse.ok()).toBeTruthy()
  const scripts = (await scriptsResponse.json()) as Array<{
    id: number
    status: string
  }>
  const readyScript = scripts.find((script) => script.status === 'ready')
  expect(readyScript).toBeDefined()

  const createGameResponse = await request.post('/api/games', {
    data: { script_id: readyScript?.id },
  })
  expect(createGameResponse.status()).toBe(201)
  const game = (await createGameResponse.json()) as {
    id: number
    game_characters: Array<{ id: number }>
  }

  const selectCharacterResponse = await request.post(
    `/api/games/${game.id}/select-character`,
    { data: { game_character_id: game.game_characters[0].id } },
  )
  expect(selectCharacterResponse.ok()).toBeTruthy()
  const startGameResponse = await request.post(`/api/games/${game.id}/start`)
  expect(startGameResponse.ok()).toBeTruthy()

  await page.goto('/')
  await expect(page.getByText('后端连接正常')).toBeVisible()
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await expect(
    page.getByRole('heading', { name: '游戏规则与 AI 对话验证' }),
  ).toBeVisible()
  await page.locator('#public-room-game-select').selectOption(String(game.id))
  await page.getByRole('button', { name: '读取角色状态' }).click()
  await expect(page.getByText('尚无角色内心记录。')).toBeVisible()
  await expect(page.getByText('尚无已保存记忆。')).toBeVisible()
})
