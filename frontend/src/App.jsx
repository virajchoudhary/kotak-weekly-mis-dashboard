import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
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
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL
  || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : window.location.origin)

const EMPTY_DATA = {
  upload: null,
  kpis: {},
  charts: { asset_class: [], top_schemes: [], sip: [], trend: [] },
  tables: { banks_summary: [], fintech_summary: [], sip_pivot: [], brokerwise: [] },
  brokerwise_total: 0,
}

const tabs = [
  ['overview', 'Overview', LayoutDashboard],
  ['banks', 'Banks / ND / RIA', BarChart3],
  ['fintech', 'FINTECH', BarChart3],
  ['sip', 'SIP Pivot', TableProperties],
  ['brokerwise', 'Brokerwise', FileSpreadsheet],
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

function MetricCard({ label, value, detail, loading, tone = '' }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{loading ? '—' : value}</strong>
      {detail && <small>{loading ? 'Loading…' : detail}</small>}
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

function DataTable({ rows, columns, empty = 'No rows available.' }) {
  return (
    <div className="table-scroll">
      <table className="theory-table">
        <thead><tr>{columns.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead>
        <tbody>
          {!rows.length && <tr><td className="empty-cell" colSpan={columns.length}>{empty}</td></tr>}
          {rows.map((row, rowIndex) => (
            <tr key={`${row.asset_class || row.arn_code || rowIndex}-${rowIndex}`}>
              {columns.map(([key, , type]) => (
                <td key={key} className={type === 'text' ? 'text-cell' : ''}>
                  {type === 'percent' ? formatPercent(row[key]) : type === 'text' ? (row[key] || '—') : formatNumber(row[key], 2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SummaryView({ title, subtitle, rows, action }) {
  return <Section title={title} subtitle={subtitle} action={action}><DataTable rows={rows} columns={summaryColumns} /></Section>
}

function SipView({ rows, action }) {
  return (
    <Section title="SIP Pivot" subtitle="Kotak and CAMS SIP counts grouped by ARN and broker." action={action}>
      <DataTable rows={rows} columns={[
        ['arn_code', 'ARN code', 'text'], ['broker_name', 'Broker name', 'text'],
        ['kotak_sip_count', 'Kotak SIP count'], ['cams_sip_count', 'CAMS SIP count'],
      ]} />
    </Section>
  )
}

function BrokerwiseView({ rows, total, action }) {
  const [search, setSearch] = useState('')
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) => [row.arn_code, row.broker_name, row.category, row.asset_class]
      .some((value) => String(value || '').toLowerCase().includes(needle)))
  }, [rows, search])
  return (
    <Section
      title="Brokerwise Data"
      subtitle={`Showing ${filtered.length} of ${total} processed rows.`}
      action={
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <label className="search-box"><Search size={16} /><input aria-label="Search brokerwise rows" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search…" /></label>
          {action}
        </div>
      }
    >
      <DataTable rows={filtered} columns={[
        ['category', 'Category', 'text'], ['sub_category', 'Sub-category', 'text'], ['arn_code', 'ARN code', 'text'],
        ['broker_name', 'Broker', 'text'], ['sch_group', 'Scheme group', 'text'], ['asset_class', 'Asset class', 'text'],
        ['kotak_aum', 'Kotak AUM'], ['cams_aum', 'CAMS AUM'], ['ms_aum', 'MS %', 'percent'],
        ['kotak_gross_sales', 'Kotak GS'], ['cams_gross_sales', 'CAMS GS'], ['ms_gross_sales', 'MS %', 'percent'],
        ['kotak_net_sales', 'Kotak NS'], ['cams_net_sales', 'CAMS NS'], ['ms_net_sales', 'MS %', 'percent'],
      ]} />
    </Section>
  )
}

function Overview({ data, loading, uploading, onUpload, action }) {
  const { kpis, charts } = data
  const metrics = [
    ['Kotak AUM', formatNumber(kpis.kotak_aum, 2), 'Portfolio assets'],
    ['CAMS AUM', formatNumber(kpis.cams_aum, 2), 'Industry assets'],
    ['AUM market share', formatPercent(kpis.ms_aum), 'Kotak ÷ CAMS', 'tone-good'],
    ['Gross sales', formatNumber(kpis.kotak_gross_sales, 2), `MS ${formatPercent(kpis.ms_gross_sales)}`],
    ['Net sales', formatNumber(kpis.kotak_net_sales, 2), `MS ${formatPercent(kpis.ms_net_sales)}`],
    ['SIP count', formatNumber(kpis.kotak_sip_count, 2), `MS ${formatPercent(kpis.ms_sip_count)}`],
    ['SIP book', formatNumber(kpis.kotak_sip_book, 2), `MS ${formatPercent(kpis.ms_sip_book)}`, 'tone-soft'],
  ]
  return (
    <>
      <Section title="Upload weekly MIS" subtitle="Files are validated and the output workbook is generated before any data is committed." action={action}>
        <UploadControl uploading={uploading} onUpload={onUpload} />
      </Section>
      <div className="metric-grid">
        {metrics.map(([label, value, detail, tone]) => <MetricCard key={label} label={label} value={value} detail={detail} tone={tone} loading={loading} />)}
      </div>
      <div className="dashboard-grid">
        <Section title="AUM by scheme group" subtitle="Kotak versus CAMS">
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
        <Section title="Top schemes" subtitle="Ranked by Kotak AUM">
          <div className="chart-wrap">
            {!charts.top_schemes.length ? <EmptyChart loading={loading} /> : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 520, height: 270 }}>
                <AreaChart data={charts.top_schemes} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="name" hide />
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
        <Section title="SIP count by category" subtitle="Grouped category and sub-category totals">
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
        <Section title="Weekly trend" subtitle="Populates as uploads accumulate">
          <div className="chart-wrap">
            {!charts.trend.length ? <EmptyChart loading={loading} /> : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 520, height: 270 }}>
                <LineChart data={charts.trend} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="week_label" stroke="var(--chart-axis)" tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--chart-axis)" tickLine={false} axisLine={false} tickFormatter={formatNumber} width={54} />
                  <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--chart-cursor-line)', strokeWidth: 1 }} />
                  <Line type="monotone" dataKey="kotak_aum" name="Kotak AUM" stroke="var(--chart-primary)" strokeWidth={2} dot={{ r: 3 }} />
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
      setData(await api(`/api/dashboard-data${query}`))
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
      setData(result.dashboard)
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
    if (activeTab === 'banks') return <SummaryView title="Summary - Banks, ND & RIA" subtitle="Template-ordered 45-scheme summary." rows={data.tables.banks_summary} action={uploadSelector} />
    if (activeTab === 'fintech') return <SummaryView title="Summary - FINTECH" subtitle="Template-ordered 42-scheme summary with exclusions applied." rows={data.tables.fintech_summary} action={uploadSelector} />
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
