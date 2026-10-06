import { expect, test } from '@playwright/test'

test('shows public turns, partial failures, and one proactive AI step', async ({
  page,
  request,
}) => {
  const scriptsResponse = await request.get('/api/scripts')
  const scripts = (await scriptsResponse.json()) as Array<{
    id: number
    status: string
  }>
  const readyScript = scripts.find((script) => script.status === 'ready')
  expect(readyScript).toBeDefined()

  const createGameResponse = await request.post('/api/games', {
    data: { script_id: readyScript?.id },
  })
  const created = (await createGameResponse.json()) as {
    id: number
    game_characters: Array<{ id: number }>
  }
  expect(createGameResponse.status()).toBe(201)

  await request.post(`/api/games/${created.id}/select-character`, {
    data: { game_character_id: created.game_characters[0].id },
  })
  await request.post(`/api/games/${created.id}/start`)

  const gameResponse = await request.get(`/api/games/${created.id}`)
  const game = (await gameResponse.json()) as {
    id: number
    game_characters: Array<{
      id: number
      controller_type: 'human' | 'ai'
      character: { name: string }
    }>
  }
  const human = game.game_characters.find(
    (character) => character.controller_type === 'human',
  )
  const aiCharacters = game.game_characters.filter(
    (character) => character.controller_type === 'ai',
  )
  expect(human).toBeDefined()
  expect(aiCharacters.length).toBe(3)

  await page.route(`**/api/games/${game.id}/public-turn`, async (route) => {
    const body = route.request().postDataJSON() as { content: string }
    const timestamp = new Date().toISOString()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        human_message: {
          id: 9001,
          game_session_id: game.id,
          sender_game_character_id: human?.id,
          channel_type: 'public',
          receiver_game_character_id: null,
          content: body.content,
          created_at: timestamp,
        },
        ai_responses: [
          {
            id: 9002,
            game_session_id: game.id,
            sender_game_character_id: aiCharacters[0].id,
            channel_type: 'public',
            receiver_game_character_id: null,
            content: '我可以说明昨晚的行踪。',
            created_at: timestamp,
          },
        ],
        status: 'partial',
        failures: [
          {
            game_character_id: aiCharacters[1].id,
            error_type: 'DifyRequestError',
          },
        ],
      }),
    })
  })

  await page.route(`**/api/games/${game.id}/ai-step`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ai_message: {
          id: 9003,
          game_session_id: game.id,
          sender_game_character_id: aiCharacters[1].id,
          channel_type: 'public',
          receiver_game_character_id: null,
          content: '我也想补充一件事。',
          created_at: new Date().toISOString(),
        },
      }),
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: /载入剧本/ }).click()
  await page.locator('#public-room-game-select').selectOption(String(game.id))
  await page.locator('#public-room-message').fill('你们怎么看？')
  await page.getByRole('button', { name: /发送 Public Turn/ }).click()

  await expect(page.getByText('HUMAN · 林澈 · PUBLIC')).toBeVisible()
  await expect(page.getByText('我可以说明昨晚的行踪。')).toBeVisible()
  await expect(page.getByText('本次公共回合部分失败')).toBeVisible()

  await page.getByRole('button', { name: /AI Proactive Step/ }).click()
  await expect(page.getByText('我也想补充一件事。')).toBeVisible()
  await expect(page.getByText(/AI · .* · PUBLIC/).last()).toBeVisible()
})
