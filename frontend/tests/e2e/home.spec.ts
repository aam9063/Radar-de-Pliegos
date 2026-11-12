import { expect, test } from '@playwright/test'

test('home renders the product name and the licitaciones heading', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Radar de Pliegos')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Licitaciones', level: 1 })).toBeVisible()
})
