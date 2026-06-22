import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

test('requires confirmation before replacing an existing week', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
  let uploadAttempts = 0
  global.fetch = vi.fn((url, options = {}) => {
    if (url.includes('/api/uploads/weekly-mis')) {
      uploadAttempts += 1
      if (uploadAttempts === 1) {
        return Promise.resolve({
          ok: false,
          status: 409,
          json: () => Promise.resolve({
            detail: {
              message: 'Week 2026-W40 already exists.',
              code: 'week_exists',
              existing_upload_id: 1,
              can_replace: true,
              can_continue: false,
            },
          }),
        })
      }
      expect(options.body.get('replace_existing')).toBe('true')
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () => Promise.resolve({
          upload_id: 2,
          status: 'replaced',
          week_label: '2026-W40',
          row_count: 1,
          dashboard: emptyDashboard,
        }),
      })
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(url.includes('/api/uploads') ? [] : emptyDashboard),
    })
  })

  const { container } = render(<App />)
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  const file = new File(['a,b\n1,2\n'], 'corrected.csv', { type: 'text/csv' })
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [file] } })
  fireEvent.change(container.querySelector('input[placeholder^="e.g."]'), { target: { value: '2026-W40' } })
  fireEvent.click(container.querySelector('button.btn-primary'))

  await waitFor(() => expect(screen.getByText(/2026-W40 replaced safely/)).toBeInTheDocument())
  expect(confirm).toHaveBeenCalledTimes(1)
  expect(uploadAttempts).toBe(2)
})
