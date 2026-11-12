import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import App from './App'

describe('App', () => {
  it('renders the product name and the licitaciones heading', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText('Radar de Pliegos')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Licitaciones', level: 1 }),
    ).toBeInTheDocument()
  })
})
