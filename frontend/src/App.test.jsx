import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from './App.jsx'

const emptyDashboard = {
  upload: null,
  kpis: {},
  charts: { asset_class: [], top_schemes: [], sip: [], trend: [] },
  tables: { banks_summary: [], fintech_summary: [], sip_pivot: [], brokerwise: [] },
  brokerwise_total: 0,
}

beforeEach(() => {
  global.fetch = vi.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(url.includes('/api/uploads') ? [] : emptyDashboard),
  }))
})

test('renders the source-of-truth dashboard shell and independent loading state', async () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: 'Weekly MIS Dashboard' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument()
  expect(screen.getByText('Upload weekly MIS')).toBeInTheDocument()
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
})

