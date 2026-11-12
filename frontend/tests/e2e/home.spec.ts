import { expect, test } from '@playwright/test'

test('home renders the product name', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /radar de pliegos/i })).toBeVisible()
})
