import { expect, test } from '@playwright/test'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const FIXTURE_PDF = join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'pliego.pdf')

test('create a licitación, upload a PDF and reach the detail view (AC-09 smoke)', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.getByText('Radar de Pliegos')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Licitaciones', level: 1 })).toBeVisible()

  await page.getByRole('link', { name: 'Nueva licitación' }).click()
  await expect(page.getByRole('heading', { name: 'Nueva licitación', level: 1 })).toBeVisible()

  await page.getByLabel('Nombre interno').fill(`E2E licitación ${Date.now()}`)
  await page.setInputFiles('#ficheros-pdf', FIXTURE_PDF)
  await expect(page.getByText('Documentos (1)')).toBeVisible()

  await page.getByRole('button', { name: 'Extraer datos' }).click()

  await expect(page).toHaveURL(/\/licitaciones\/\d+$/)
  await expect(page.getByRole('heading', { level: 1, name: /E2E licitación/ })).toBeVisible()

  // The uploaded PDF is served and shown in the viewer (iframe, page 1).
  const visor = page.getByTitle('Visor del documento')
  await expect(visor).toBeVisible()
  await expect(visor).toHaveAttribute('src', /\/documentos\/\d+\/pdf#page=1$/)
  await expect(page.getByTestId('pagina-indicador')).toHaveText('Página 1 de 2')

  // Without a seeded extraction there is no ficha yet: the empty state shows.
  await expect(page.getByText(/Aún no se ha extraído la ficha/)).toBeVisible()
})

test('the list shows the created licitación', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Licitaciones', level: 1 })).toBeVisible()
  await expect(page.getByRole('link', { name: /E2E licitación/ }).first()).toBeVisible()
})
