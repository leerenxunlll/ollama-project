import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  reporter: 'list',
  workers: 1, // E2E scenarios write to the local SQLite database.
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173',
    headless: true,
  },
})
