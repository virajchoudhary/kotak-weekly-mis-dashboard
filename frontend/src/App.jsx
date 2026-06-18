import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  Rectangle,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Archive,
  BarChart3,
  Check,
  ChevronDown,
  Download,
  FileSpreadsheet,
  FileUp,
  LayoutDashboard,
  Moon,
  RefreshCw,
  Search,
  Sun,
  TableProperties,
  Trash2,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL
  || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : window.location.origin)

const EMPTY_DATA = {
  upload: null,
  kpis: {},
  totals: {},
  reconciliation: {},
  scope_counts: {},
  reconciled: true,
  charts: { asset_class: [], top_schemes: [], sip: [], trend: [] },
  tables: { banks_summary: [], fintech_summary: [], sip_pivot: [], brokerwise: [] },
  brokerwise_total: 0,
}

const normalizeDashboard = (payload) => ({
  ...EMPTY_DATA,
  ...(payload || {}),
  charts: { ...EMPTY_DATA.charts, ...(payload?.charts || {}) },
  tables: { ...EMPTY_DATA.tables, ...(payload?.tables || {}) },
})

const tabs = [
  ['overview', 'Overview', LayoutDashboard],
  ['banks', 'Banks / ND / RIA', BarChart3],
  ['fintech', 'FINTECH', BarChart3],
  ['sip', 'SIP Pivot', TableProperties],
  ['brokerwise', 'Brokerwise (Overall)', FileSpreadsheet],
  ['archives', 'Archives', Archive],
]

async function api(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail || body
    const error = new Error(detail.message || `Request failed (${response.status})`)
    error.details = detail.errors || []
    throw error
  }
  if (response.status === 204) return null
  return response.json()
}

const formatNumber = (value, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('en-IN', {
    notation: Math.abs(Number(value)) >= 100000 ? 'compact' : 'standard',
    maximumFractionDigits: digits,
  }).format(Number(value))
}

const formatPercent = (value) => (
  value === null || value === undefined ? '—' : `${(Number(value) * 100).toFixed(2)}%`
)

function Section({ title, subtitle, action, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      <div className="card-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function MetricDelta({ pct }) {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return null
  const up = pct >= 0
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className={`metric-delta ${up ? 'up' : 'down'}`}>
      <Icon size={13} />{`${up ? '+' : ''}${(pct * 100).toFixed(1)}% WoW`}
    </span>
  )
}

function MetricCard({ label, value, detail, loading, tone = '', delta }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{loading ? '—' : value}</strong>
      {detail && <small>{loading ? 'Loading…' : detail}</small>}
      {!loading && <MetricDelta pct={delta} />}
    </article>
  )
}

function GlassSelect({ value, options, onChange, ariaLabel = 'Select option' }) {
  const [open, setOpen] = useState(false)
  const selectedIndex = Math.max(0, options.findIndex((option) => String(option.value) === String(value)))
  const [highlighted, setHighlighted] = useState(selectedIndex)
  const rootRef = useRef(null)

  useEffect(() => setHighlighted(selectedIndex), [selectedIndex])
  useEffect(() => {
    const close = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])

  const choose = (index) => {
    const option = options[index]
    if (!option) return
    onChange(option.value)
    setOpen(false)
  }

  const onKeyDown = (event) => {
    if (!options.length) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const direction = event.key === 'ArrowDown' ? 1 : -1
      setOpen(true)
      setHighlighted((current) => (current + direction + options.length) % options.length)
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      setOpen(true)
      setHighlighted(event.key === 'Home' ? 0 : options.length - 1)
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      if (open) choose(highlighted)
      else setOpen(true)
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const selected = options[selectedIndex]
  return (
    <div className="glass-select" ref={rootRef}>
      <button
        type="button"
        className={`glass-select-trigger ${open ? 'open' : ''}`}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-activedescendant={open ? `option-${highlighted}` : undefined}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onKeyDown}
      >
        <span>{selected?.label || 'Select'}</span>
        <ChevronDown size={16} className="glass-select-chevron" />
      </button>
      {open && (
        <div className="glass-select-menu" role="listbox" aria-label={ariaLabel}>
          {options.map((option, index) => (
            <button
              id={`option-${index}`}
              type="button"
              role="option"
              aria-selected={String(option.value) === String(value)}
              key={option.value}
              className={`glass-select-option ${index === highlighted ? 'highlighted' : ''} ${String(option.value) === String(value) ? 'active' : ''}`}
              onMouseEnter={() => setHighlighted(index)}
              onClick={() => choose(index)}
            >
              <span>{option.label}</span>
              {String(option.value) === String(value) && <Check size={15} />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((item) => (
        <div className="tooltip-row" key={item.dataKey}>
          <span><i style={{ background: item.color }} />{item.name}</span>
          <b>{formatNumber(item.value, 2)}</b>
        </div>
      ))}
    </div>
  )
}

const renderActiveBar = (props) => (
  <Rectangle {...props} stroke="#fff" strokeWidth={2} strokeOpacity={0.85} />
)

function EmptyChart({ loading }) {
  return <div className="empty-chart">{loading ? 'Loading dashboard…' : 'Upload a weekly MIS file to populate this view.'}</div>
}

const trendMetrics = [
  { value: 'aum', label: 'AUM', kotak: 'kotak_aum', cams: 'cams_aum' },
  { value: 'gross_sales', label: 'Gross sales', kotak: 'kotak_gross_sales', cams: 'cams_gross_sales' },
  { value: 'net_sales', label: 'Net sales', kotak: 'kotak_net_sales', cams: 'cams_net_sales' },
  { value: 'sip_count', label: 'SIP count', kotak: 'kotak_sip_count', cams: 'cams_sip_count' },
  { value: 'sip_book', label: 'SIP book', kotak: 'kotak_sip_book', cams: 'cams_sip_book' },
  { value: 'market_share', label: 'Market share %' },
]

function MarketShareTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((item) => (
        <div className="tooltip-row" key={item.dataKey}>
          <span><i style={{ background: item.color }} />{item.name}</span>
          <b>{formatPercent(item.value)}</b>
        </div>
      ))}
    </div>
  )
}

function ShareDonut({ label, share }) {
  const safe = Math.min(Math.max(Number(share) || 0, 0), 1)
  const pieData = [{ name: 'Kotak', value: safe }, { name: 'Industry', value: 1 - safe }]
  return (
    <div className="share-card">
      <div className="share-donut">
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 150, height: 150 }}>
          <PieChart>
            <Pie data={pieData} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="92%" startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}>
              <Cell fill="var(--chart-primary)" />
              <Cell fill="var(--chart-secondary)" />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <span className="share-value">{formatPercent(share)}</span>
      </div>
      <span className="share-caption">{label}</span>
    </div>
  )
}

function UploadControl({ uploading, onUpload }) {
  const [file, setFile] = useState(null)
  const [weekLabel, setWeekLabel] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const submit = (event) => {
    event.preventDefault()
    if (file) onUpload(file, weekLabel)
  }

  const accept = (files) => {
    const selected = files?.[0]
    if (selected) setFile(selected)
  }

  return (
    <form className="upload-form" onSubmit={submit}>
      <div
        className={`drop-zone ${dragging ? 'dragging' : ''}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); accept(event.dataTransfer.files) }}
      >
        <FileUp size={22} />
        <div>
          <strong>{file?.name || 'Drop the Weekly MIS file here'}</strong>
          <span>.xlsx, .xls, or .csv · up to 25 MB</span>
        </div>
        <button type="button" className="btn-secondary" onClick={() => inputRef.current?.click()}>Browse</button>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          onChange={(event) => accept(event.target.files)}
          hidden
        />
      </div>
      <label className="field-label">
        <span>Week label</span>
        <input value={weekLabel} onChange={(event) => setWeekLabel(event.target.value)} placeholder="e.g. 2026-W24 (optional)" />
      </label>
      <button className="btn-primary" disabled={!file || uploading} type="submit">
        {uploading ? <><RefreshCw size={17} className="spinner" /> Processing…</> : <><FileUp size={17} /> Validate & process</>}
      </button>
    </form>
  )
}

const summaryColumns = [
  ['asset_class', 'Asset class', 'text'], ['sch_group', 'Scheme group', 'text'],
  ['kotak_aum', 'Kotak AUM'], ['cams_aum', 'CAMS AUM'], ['ms_aum', 'MS %', 'percent'],
  ['kotak_gross_sales', 'Kotak GS'], ['cams_gross_sales', 'CAMS GS'], ['ms_gross_sales', 'MS %', 'percent'],
  ['kotak_net_sales', 'Kotak NS'], ['cams_net_sales', 'CAMS NS'], ['ms_net_sales', 'MS %', 'percent'],
  ['kotak_sip_count', 'Kotak SIP'], ['cams_sip_count', 'CAMS SIP'], ['ms_sip_count', 'MS %', 'percent'],
  ['kotak_sip_book', 'Kotak Book'], ['cams_sip_book', 'CAMS Book'], ['ms_sip_book', 'MS %', 'percent'],
]

function DataTable({ rows, columns, empty = 'No rows available.', showTotals = false, searchable = false, searchKeys }) {
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState({ key: null, dir: 'asc' })

  const keys = searchKeys || columns.filter(([, , type]) => type === 'text').map(([key]) => key)

  const searched = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!searchable || !needle) return rows
    return rows.filter((row) => keys.some((key) => String(row[key] ?? '').toLowerCase().includes(needle)))
  }, [rows, search, searchable, keys])

  const sorted = useMemo(() => {
    if (!sort.key) return searched
    const column = columns.find(([key]) => key === sort.key)
    const type = column?.[2]
    const factor = sort.dir === 'asc' ? 1 : -1
    return [...searched].sort((a, b) => {
      if (type === 'text') {
        return String(a[sort.key] ?? '').localeCompare(String(b[sort.key] ?? '')) * factor
      }
      const av = Number(a[sort.key])
      const bv = Number(b[sort.key])
      const aNan = Number.isNaN(av)
      const bNan = Number.isNaN(bv)
      if (aNan && bNan) return 0
      if (aNan) return 1
      if (bNan) return -1
      return (av - bv) * factor
    })
  }, [searched, sort, columns])

  const toggleSort = (key) => {
    setSort((current) => (
      current.key === key
        ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' }
    ))
  }

  const totals = useMemo(() => {
    if (!showTotals) return null
    const sums = {}
    columns.forEach(([key, , type]) => {
      if (type === 'text' || type === 'percent') return
      sums[key] = sorted.reduce((acc, row) => {
        const value = Number(row[key])
        return acc + (Number.isFinite(value) ? value : 0)
      }, 0)
    })
    let seenText = false
    return columns.map(([key, , type], index) => {
      if (type === 'text') {
        if (!seenText) { seenText = true; return 'Grand Total' }
        return ''
      }
      if (type === 'percent') {
        const kotakKey = columns[index - 2]?.[0]
        const camsKey = columns[index - 1]?.[0]
        if (!kotakKey || !camsKey) return '—'
        const kotakSum = sums[kotakKey]
        const camsSum = sums[camsKey]
        return camsSum ? formatPercent(kotakSum / camsSum) : '—'
      }
      return formatNumber(sums[key], 2)
    })
  }, [showTotals, sorted, columns])

  const table = (
    <div className="table-scroll">
      <table className="theory-table">
        <thead><tr>{columns.map(([key, label, type]) => {
          const active = sort.key === key
          return (
            <th key={key} className="sortable" onClick={() => toggleSort(key)} title="Click to sort">
              <span className={type === 'text' ? 'th-inner left' : 'th-inner'}>
                {label}
                <i className={`sort-caret ${active ? sort.dir : ''}`}>{active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}</i>
              </span>
            </th>
          )
        })}</tr></thead>
        <tbody>
          {!sorted.length && <tr><td className="empty-cell" colSpan={columns.length}>{empty}</td></tr>}
          {sorted.map((row, rowIndex) => (
            <tr key={`${row.asset_class || row.arn_code || rowIndex}-${rowIndex}`}>
              {columns.map(([key, , type]) => {
                const numeric = type !== 'text' && type !== 'percent'
                const value = Number(row[key])
                const neg = numeric && Number.isFinite(value) && value < 0
                return (
                  <td key={key} className={`${type === 'text' ? 'text-cell' : ''}${neg ? ' neg' : ''}`}>
                    {type === 'percent' ? formatPercent(row[key]) : type === 'text' ? (row[key] || '—') : formatNumber(row[key], 2)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
        {showTotals && sorted.length > 0 && (
          <tfoot><tr className="totals-row">
            {totals.map((value, index) => (
              <td key={columns[index][0]} className={columns[index][2] === 'text' ? 'text-cell' : ''}>{value}</td>
            ))}
          </tr></tfoot>
        )}
      </table>
    </div>
  )

  if (!searchable) return table
  return (
    <>
      <div className="table-toolbar">
        <label className="search-box"><Search size={16} /><input aria-label="Search rows" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search…" /></label>
      </div>
      {table}
    </>
  )
}

function SummaryView({ title, subtitle, rows, action }) {
  return <Section title={title} subtitle={subtitle} action={action}><DataTable rows={rows} columns={summaryColumns} showTotals searchable /></Section>
}

function SipView({ rows, action }) {
  return (
    <Section title="SIP Pivot" subtitle="Kotak and CAMS SIP counts grouped by ARN and broker." action={action}>
      <DataTable rows={rows} showTotals searchable columns={[
        ['arn_code', 'ARN code', 'text'], ['broker_name', 'Broker name', 'text'],
        ['kotak_sip_count', 'Kotak SIP count'], ['cams_sip_count', 'CAMS SIP count'],
      ]} />
    </Section>
  )
}

function BrokerwiseView({ rows, total, action }) {
  return (
    <Section title="Overall Brokerwise Total" subtitle={`Every uploaded row across all scopes (Overall) · ${total} processed rows.`} action={action}>
      <DataTable rows={rows} showTotals searchable columns={[
        ['category', 'Category', 'text'], ['sub_category', 'Sub-category', 'text'], ['arn_code', 'ARN code', 'text'],
        ['broker_name', 'Broker', 'text'], ['sch_group', 'Scheme group', 'text'], ['asset_class', 'Asset class', 'text'],
        ['kotak_aum', 'Kotak AUM'], ['cams_aum', 'CAMS AUM'], ['ms_aum', 'MS %', 'percent'],
        ['kotak_gross_sales', 'Kotak GS'], ['cams_gross_sales', 'CAMS GS'], ['ms_gross_sales', 'MS %', 'percent'],
        ['kotak_net_sales', 'Kotak NS'], ['cams_net_sales', 'CAMS NS'], ['ms_net_sales', 'MS %', 'percent'],
      ]} />
    </Section>
  )
}

const wowPct = (current, prior) => {
  const cur = Number(current)
  const pri = Number(prior)
  if (!Number.isFinite(cur) || !Number.isFinite(pri) || pri === 0) return null
  return (cur - pri) / Math.abs(pri)
}

const scopeOptions = [
  ['overall', 'Overall'],
  ['banks_nd_ria', 'Banks/ND/RIA'],
  ['fintech', 'FINTECH'],
]

const scopeLabels = {
  overall: 'Overall (all scopes)',
  banks_nd_ria: 'Banks/ND/RIA',
  fintech: 'FINTECH',
  unmapped_or_excluded: 'Unmapped/Excluded',
}

function ScopeTabs({ value, onChange, counts }) {
  return (
    <div className="scope-tabs" role="tablist" aria-label="Reporting scope">
      {scopeOptions.map(([key, label]) => (
        <button
          key={key}
          type="button"
          role="tab"
          aria-selected={value === key}
          className={`scope-tab ${value === key ? 'active' : ''}`}
          onClick={() => onChange(key)}
        >
          {label}
          {counts && Number.isFinite(Number(counts[key])) && <span className="scope-count">{counts[key]}</span>}
        </button>
      ))}
    </div>
  )
}

const reconMetrics = [
  ['kotak_aum', 'Kotak AUM'],
  ['cams_aum', 'CAMS AUM'],
  ['kotak_gross_sales', 'Kotak Gross Sales'],
  ['cams_gross_sales', 'CAMS Gross Sales'],
  ['kotak_net_sales', 'Kotak Net Sales'],
  ['cams_net_sales', 'CAMS Net Sales'],
  ['kotak_sip_count', 'Kotak SIP Count'],
  ['cams_sip_count', 'CAMS SIP Count'],
  ['kotak_sip_book', 'Kotak SIP Book'],
  ['cams_sip_book', 'CAMS SIP Book'],
]

function ReconciliationCard({ reconciliation, reconciled, loading }) {
  const entries = reconciliation || {}
  const hasData = Object.keys(entries).length > 0
  return (
    <Section
      title="Reconciliation"
      subtitle="Brokerwise = Banks/ND/RIA + FINTECH + Unmapped/Excluded. A metric is reconciled when the difference is 0."
      action={hasData ? (
        <span className={`recon-status ${reconciled ? 'ok' : 'bad'}`}>
          {reconciled ? 'All metrics reconciled' : 'Mismatch detected'}
        </span>
      ) : null}
    >
      {!hasData ? (
        <div className="empty-chart">{loading ? 'Loading…' : 'Upload a weekly MIS file to see reconciliation.'}</div>
      ) : (
        <div className="table-scroll">
          <table className="theory-table recon-table">
            <thead><tr>
              <th className="text-cell">Metric</th>
              <th>Brokerwise total</th>
              <th>Banks/ND/RIA</th>
              <th>FINTECH</th>
              <th>Unmapped/Excluded</th>
              <th>Difference</th>
              <th>Status</th>
            </tr></thead>
            <tbody>
              {reconMetrics.map(([key, label]) => {
                const entry = entries[key]
                if (!entry) return null
                const ok = entry.status === 'reconciled'
                return (
                  <tr key={key}>
                    <td className="text-cell">{label}</td>
                    <td>{formatNumber(entry.brokerwise_total, 2)}</td>
                    <td>{formatNumber(entry.banks_nd_ria_total, 2)}</td>
                    <td>{formatNumber(entry.fintech_total, 2)}</td>
                    <td>{formatNumber(entry.unmapped_or_excluded_total, 2)}</td>
                    <td className={ok ? '' : 'neg'}>{formatNumber(entry.difference, 2)}</td>
                    <td><span className={`recon-badge ${ok ? 'ok' : 'bad'}`}>{ok ? 'Reconciled' : 'Mismatch'}</span></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}

function Overview({ data, loading, uploading, onUpload, action }) {
  const { kpis, charts } = data
  const [trendMetric, setTrendMetric] = useState('aum')
  const [scope, setScope] = useState('overall')

  const prior = useMemo(() => {
    const trend = charts.trend || []
    const idx = trend.findIndex((row) => row.id === data.upload?.id)
    return idx > 0 ? trend[idx - 1] : undefined
  }, [charts.trend, data.upload])

  const priorShare = prior && Number(prior.cams_aum) ? Number(prior.kotak_aum) / Number(prior.cams_aum) : undefined

  const trendData = useMemo(() => (charts.trend || []).map((row) => {
    const kotak = Number(row.kotak_aum)
    const cams = Number(row.cams_aum)
    const ms = Number.isFinite(kotak) && Number.isFinite(cams) && cams !== 0 ? kotak / cams : null
    return { ...row, ms }
  }), [charts.trend])

  const activeMetric = trendMetrics.find((metric) => metric.value === trendMetric) || trendMetrics[0]
  const isShare = activeMetric.value === 'market_share'

  const scopeTotals = (data.totals && data.totals[scope]) || kpis
  const isOverall = scope === 'overall'
  const d = (current, priorValue) => (isOverall ? wowPct(current, priorValue) : null)
  const metrics = [
    ['Total Kotak AUM', formatNumber(scopeTotals.kotak_aum, 2), 'Portfolio assets', '', d(scopeTotals.kotak_aum, prior?.kotak_aum)],
    ['Total CAMS AUM', formatNumber(scopeTotals.cams_aum, 2), 'Industry assets', '', d(scopeTotals.cams_aum, prior?.cams_aum)],
    ['AUM market share', formatPercent(scopeTotals.ms_aum), 'Kotak ÷ CAMS', 'tone-good', d(scopeTotals.ms_aum, priorShare)],
    ['Total Gross Sales', formatNumber(scopeTotals.kotak_gross_sales, 2), `MS ${formatPercent(scopeTotals.ms_gross_sales)}`, '', d(scopeTotals.kotak_gross_sales, prior?.kotak_gross_sales)],
    ['Total Net Sales', formatNumber(scopeTotals.kotak_net_sales, 2), `MS ${formatPercent(scopeTotals.ms_net_sales)}`, '', d(scopeTotals.kotak_net_sales, prior?.kotak_net_sales)],
    ['Total SIP Count', formatNumber(scopeTotals.kotak_sip_count, 2), `MS ${formatPercent(scopeTotals.ms_sip_count)}`, '', d(scopeTotals.kotak_sip_count, prior?.kotak_sip_count)],
    ['Total SIP Book', formatNumber(scopeTotals.kotak_sip_book, 2), `MS ${formatPercent(scopeTotals.ms_sip_book)}`, 'tone-soft', d(scopeTotals.kotak_sip_book, prior?.kotak_sip_book)],
  ]
  const hasKpis = Object.keys(kpis).length > 0
  return (
    <>
      <Section title="Upload weekly MIS" subtitle="Files are validated and the output workbook is generated before any data is committed." action={action}>
        <UploadControl uploading={uploading} onUpload={onUpload} />
      </Section>
      <div className="scope-bar">
        <div className="scope-bar-label">
          <span className="eyebrow">Totals scope</span>
          <strong>{scopeLabels[scope]}</strong>
        </div>
        <ScopeTabs value={scope} onChange={setScope} counts={data.scope_counts} />
      </div>
      <div className="metric-grid">
        {metrics.map(([label, value, detail, tone, delta]) => <MetricCard key={label} label={label} value={value} detail={detail} tone={tone} delta={delta} loading={loading} />)}
      </div>
      {!isOverall && (
        <div className="scope-note">
          Showing <strong>{scopeLabels[scope]}</strong> totals — a subset of the overall brokerwise total. Week-over-week deltas are shown for the Overall scope only. See Reconciliation below.
        </div>
      )}
      <ReconciliationCard reconciliation={data.reconciliation} reconciled={data.reconciled} loading={loading} />
      <Section title="Market share — Kotak vs industry" subtitle={`Kotak share of each industry metric · ${scopeLabels[scope]}`}>
        {!hasKpis ? <div className="chart-wrap"><EmptyChart loading={loading} /></div> : (
          <div className="share-grid">
            <ShareDonut label="AUM" share={scopeTotals.ms_aum} />
            <ShareDonut label="Gross sales" share={scopeTotals.ms_gross_sales} />
            <ShareDonut label="Net sales" share={scopeTotals.ms_net_sales} />
            <ShareDonut label="SIP count" share={scopeTotals.ms_sip_count} />
          </div>
        )}
      </Section>
      <div className="dashboard-grid">
        <Section title="AUM by scheme group" subtitle="Kotak versus CAMS · Overall (all scopes)">
          <div className="chart-wrap">
            {!charts.asset_class.length ? <EmptyChart loading={loading} /> : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 520, height: 270 }}>
                <BarChart data={charts.asset_class} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="name" stroke="var(--chart-axis)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--chart-axis)" tickLine={false} axisLine={false} tickFormatter={formatNumber} width={54} />
                  <Tooltip content={<ChartTooltip />} cursor={false} />
                  <Bar dataKey="kotak_aum" name="Kotak AUM" fill="var(--chart-primary)" radius={[5, 5, 0, 0]} activeBar={renderActiveBar} />
                  <Bar dataKey="cams_aum" name="CAMS AUM" fill="var(--chart-secondary)" radius={[5, 5, 0, 0]} activeBar={renderActiveBar} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>
        <Section title="Top schemes" subtitle="Ranked by Kotak AUM · Overall (all scopes)">
          <div className="chart-wrap">
            {!charts.top_schemes.length ? <EmptyChart loading={loading} /> : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 520, height: 270 }}>
                <AreaChart data={charts.top_schemes} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="name" stroke="var(--chart-axis)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--chart-axis)" tickLine={false} axisLine={false} tickFormatter={formatNumber} width={54} />
                  <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--chart-cursor-line)', strokeWidth: 1 }} />
                  <Area type="monotone" dataKey="kotak_aum" name="Kotak AUM" stroke="var(--chart-primary)" fill="var(--chart-fill)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>
      </div>
      <div className="dashboard-grid">
        <Section title="SIP count by category" subtitle="Grouped category and sub-category totals · Overall (all scopes)">
          <div className="chart-wrap">
            {!charts.sip.length ? <EmptyChart loading={loading} /> : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 520, height: 270 }}>
                <BarChart data={charts.sip} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="name" stroke="var(--chart-axis)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--chart-axis)" tickLine={false} axisLine={false} tickFormatter={formatNumber} width={54} />
                  <Tooltip content={<ChartTooltip />} cursor={false} />
                  <Bar dataKey="kotak_sip_count" name="Kotak SIP" fill="var(--chart-primary)" activeBar={renderActiveBar} />
                  <Bar dataKey="cams_sip_count" name="CAMS SIP" fill="var(--chart-secondary)" activeBar={renderActiveBar} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>
        <Section
          title="Weekly trend"
          subtitle="Populates as uploads accumulate · Overall (all scopes)"
          action={
            <div className="trend-select">
              <GlassSelect ariaLabel="Select trend metric" value={trendMetric} options={trendMetrics.map(({ value, label }) => ({ value, label }))} onChange={setTrendMetric} />
            </div>
          }
        >
          <div className="chart-wrap">
            {!trendData.length ? <EmptyChart loading={loading} /> : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 520, height: 270 }}>
                <LineChart data={trendData} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="week_label" stroke="var(--chart-axis)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--chart-axis)" tickLine={false} axisLine={false} tickFormatter={isShare ? formatPercent : formatNumber} width={isShare ? 64 : 54} />
                  <Tooltip content={isShare ? <MarketShareTooltip /> : <ChartTooltip />} cursor={{ stroke: 'var(--chart-cursor-line)', strokeWidth: 1 }} />
                  {isShare ? (
                    <Line type="monotone" dataKey="ms" name="Market share" stroke="var(--chart-primary)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                  ) : (
                    <>
                      <Line type="monotone" dataKey={activeMetric.kotak} name={`Kotak ${activeMetric.label}`} stroke="var(--chart-primary)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                      <Line type="monotone" dataKey={activeMetric.cams} name={`CAMS ${activeMetric.label}`} stroke="var(--chart-secondary)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                    </>
                  )}
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>
      </div>
    </>
  )
}

function ArchivesView({ uploads, onSelect, onDelete }) {
  return (
    <Section title="Upload archives" subtitle="Browse, restore, download, or remove a finalized weekly upload.">
      <div className="archive-list">
        {!uploads.length && <div className="empty-chart">No uploads have been finalized yet.</div>}
        {uploads.map((upload) => (
          <article className="archive-row" key={upload.id}>
            <div className="archive-icon"><FileSpreadsheet size={19} /></div>
            <div className="archive-main">
              <strong>{upload.week_label}</strong>
              <span>{upload.original_filename} · {upload.row_count} rows</span>
            </div>
            <span className={`status-badge ${upload.status === 'finalized' ? 'finalized' : 'in-progress'}`}>{upload.status}</span>
            <button className="btn-icon" title="Open upload" onClick={() => onSelect(upload.id)}><LayoutDashboard size={17} /></button>
            <a className="btn-icon" title="Download Excel" href={`${API_BASE}/api/download/${upload.id}`}><Download size={17} /></a>
            <button className="btn-icon danger" title="Delete upload" onClick={() => onDelete(upload.id)}><Trash2 size={17} /></button>
          </article>
        ))}
      </div>
    </Section>
  )
}

export default function App() {
  const [isDarkMode, setIsDarkMode] = useState(true)
  const [activeTab, setActiveTab] = useState('overview')
  const [data, setData] = useState(EMPTY_DATA)
  const [uploads, setUploads] = useState([])
  const [selectedUpload, setSelectedUpload] = useState('latest')
  const [loading, setLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadDashboard = async (uploadId = selectedUpload) => {
    setLoading(true)
    setError('')
    try {
      const query = uploadId && uploadId !== 'latest' ? `?upload_id=${uploadId}` : ''
      setData(normalizeDashboard(await api(`/api/dashboard-data${query}`)))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  const loadUploads = async () => {
    try { setUploads(await api('/api/uploads')) } catch (requestError) { setError(requestError.message) }
  }

  useEffect(() => {
    Promise.all([loadDashboard('latest'), loadUploads()]).catch(() => {})
  }, [])

  const selectUpload = async (value) => {
    setSelectedUpload(value)
    await loadDashboard(value)
    if (activeTab === 'archives') setActiveTab('overview')
  }

  const uploadFile = async (file, weekLabel) => {
    setIsUploading(true)
    setError('')
    setNotice('')
    const body = new FormData()
    body.append('file', file)
    if (weekLabel.trim()) body.append('week_label', weekLabel.trim())
    try {
      const result = await api('/api/uploads/weekly-mis', { method: 'POST', body })
      setData(normalizeDashboard(result.dashboard))
      setSelectedUpload(result.upload_id)
      setNotice(`${result.week_label} finalized: ${result.row_count} rows validated and stored.`)
      await loadUploads()
    } catch (requestError) {
      const firstDetail = requestError.details?.[0]
      setError(firstDetail ? `${requestError.message} ${firstDetail.field || ''} ${firstDetail.message || ''}`.trim() : requestError.message)
    } finally {
      setIsUploading(false)
    }
  }

  const deleteUpload = async (uploadId) => {
    if (!window.confirm('Delete this upload and its generated files?')) return
    try {
      await api(`/api/uploads/${uploadId}`, { method: 'DELETE' })
      await loadUploads()
      if (String(selectedUpload) === String(uploadId)) {
        setSelectedUpload('latest')
        await loadDashboard('latest')
      }
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const uploadOptions = [
    { value: 'latest', label: 'Latest finalized week' },
    ...uploads.map((upload) => ({ value: upload.id, label: `${upload.week_label} · ${upload.row_count} rows` })),
  ]

  const uploadSelector = (
    <div className="header-select">
      <GlassSelect ariaLabel="Select upload week" value={selectedUpload} options={uploadOptions} onChange={selectUpload} />
    </div>
  )

  const content = useMemo(() => {
    if (activeTab === 'banks') return <SummaryView title="Banks/ND/RIA Summary" subtitle="Banks/ND/RIA scope only — FINTECH is reported separately, so these totals exclude FINTECH. Full breakdown under Reconciliation on the Overview tab." rows={data.tables.banks_summary} action={uploadSelector} />
    if (activeTab === 'fintech') return <SummaryView title="FINTECH Summary" subtitle="FINTECH scope only — 42-scheme summary with 3 excluded scheme types. Banks/ND/RIA + FINTECH + Unmapped/Excluded = Overall Brokerwise total." rows={data.tables.fintech_summary} action={uploadSelector} />
    if (activeTab === 'sip') return <SipView rows={data.tables.sip_pivot} action={uploadSelector} />
    if (activeTab === 'brokerwise') return <BrokerwiseView rows={data.tables.brokerwise} total={data.brokerwise_total} action={uploadSelector} />
    if (activeTab === 'archives') return <ArchivesView uploads={uploads} onSelect={selectUpload} onDelete={deleteUpload} />
    return <Overview data={data} loading={loading && !data.upload} uploading={isUploading} onUpload={uploadFile} action={uploadSelector} />
  }, [activeTab, data, loading, isUploading, uploads, selectedUpload, uploadOptions])

  return (
    <div className={`app-layout ${isDarkMode ? 'dark-theme' : 'light-theme'}`}>
      <button
        className="theme-toggle"
        onClick={() => setIsDarkMode((value) => !value)}
        title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        aria-label={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {isDarkMode ? <Sun size={18} /> : <Moon size={18} />}
      </button>
      <aside className="sidebar" aria-label="Dashboard sections">
        {tabs.map(([key, label, Icon]) => (
          <button key={key} className={activeTab === key ? 'active' : ''} onClick={() => setActiveTab(key)}>
            <Icon size={17} /><span>{label}</span>
          </button>
        ))}
      </aside>
      <main className="main-content">
        <header className="app-header">
          <div>
            <span className="eyebrow">Kotak Mutual Fund · Internal MIS</span>
            <h1>Weekly MIS Dashboard</h1>
            <p>Validated brokerwise reporting, history, and template-matched Excel exports.</p>
          </div>
        </header>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {notice && <div className="success-banner" role="status">{notice}</div>}
        <div className="page-content">{content}</div>
      </main>
      {data.upload && (
        <a className="download-fab" href={`${API_BASE}/api/download/${data.upload.id}`} title="Download generated weekly summary" aria-label="Download generated weekly summary">
          <Download size={21} />
        </a>
      )}
    </div>
  )
}
