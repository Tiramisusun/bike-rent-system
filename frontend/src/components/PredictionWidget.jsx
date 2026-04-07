import { useState, useRef, useEffect } from 'react'

function StationSearch({ stations, selectedStation, onSelect }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  const suggestions = query.trim().length >= 1
    ? stations.filter(s =>
        s.name.toLowerCase().includes(query.toLowerCase()) ||
        String(s.number).includes(query)
      ).slice(0, 6)
    : []

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const displayValue = selectedStation ? selectedStation.name : query

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <input
        style={s.input}
        placeholder="Search station name or number…"
        value={displayValue}
        onChange={e => { setQuery(e.target.value); onSelect(null); setOpen(true) }}
        onFocus={() => setOpen(true)}
        autoComplete="off"
      />
      {open && suggestions.length > 0 && (
        <div style={s.dropdown}>
          {suggestions.map(st => (
            <div
              key={st.number}
              style={s.suggestion}
              onMouseEnter={e => e.currentTarget.style.background = '#f0f4ff'}
              onMouseLeave={e => e.currentTarget.style.background = ''}
              onMouseDown={e => {
                e.preventDefault()
                onSelect(st)
                setQuery('')
                setOpen(false)
              }}
            >
              <span style={s.suggestNum}>#{st.number}</span>
              <span style={s.suggestName}>{st.name}</span>
              <span style={s.suggestBikes}>🚲 {st.available_bikes ?? 0}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function PredictionWidget({ stations = [] }) {
  const now = new Date()
  const [open, setOpen] = useState(false)
  const [station, setStation] = useState(null)
  const [date, setDate] = useState(now.toISOString().slice(0, 10))
  const [time, setTime] = useState(now.toTimeString().slice(0, 5))
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handlePredict() {
    if (!station) { setError('Please select a station'); return }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const dt = `${date}T${time}:00`
      const res = await fetch(`/api/predict?station_id=${station.number}&datetime=${dt}`)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error ?? 'Prediction failed')
      setResult(json)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function bikeColor(n) {
    if (n === 0) return '#e74c3c'
    if (n <= 5)  return '#f39c12'
    return '#2ecc71'
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={s.openBtn}>
        🔮 Predict
      </button>
    )
  }

  return (
    <div style={s.panel}>
      {/* Header */}
      <div style={s.header}>
        <span style={s.title}>🔮 Bike Prediction</span>
        <button onClick={() => { setOpen(false); setResult(null); setError(null) }} style={s.closeBtn}>✕</button>
      </div>

      <div style={s.body}>
        {/* Station selector */}
        <label style={s.label}>Station</label>
        <StationSearch
          stations={stations}
          selectedStation={station}
          onSelect={s => { setStation(s); setResult(null) }}
        />

        {/* Date & Time */}
        <label style={{ ...s.label, marginTop: 10 }}>Date</label>
        <input
          type="date"
          value={date}
          onChange={e => { setDate(e.target.value); setResult(null) }}
          style={s.input}
        />

        <label style={{ ...s.label, marginTop: 8 }}>Time</label>
        <input
          type="time"
          value={time}
          onChange={e => { setTime(e.target.value); setResult(null) }}
          style={s.input}
        />

        {/* Predict button */}
        <button
          onClick={handlePredict}
          disabled={loading}
          style={s.predictBtn}
        >
          {loading ? 'Predicting…' : 'Predict'}
        </button>

        {/* Error */}
        {error && <div style={s.error}>{error}</div>}

        {/* Result */}
        {result && (
          <div style={s.result}>
            <div style={s.resultStation}>{result.station_name}</div>
            <div style={{ ...s.resultNumber, color: bikeColor(result.predicted_bikes) }}>
              {result.predicted_bikes}
            </div>
            <div style={s.resultLabel}>predicted bikes available</div>
            <div style={s.resultMeta}>
              🌡️ {result.weather.temp}°C &nbsp;·&nbsp; 💧 {result.weather.humidity}%
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const s = {
  panel: {
    background: '#fff',
    borderRadius: 8,
    boxShadow: '0 2px 16px rgba(0,0,0,0.22)',
    width: 300,
    fontFamily: "'Segoe UI', Arial, sans-serif",
    pointerEvents: 'auto',
  },
  openBtn: {
    pointerEvents: 'auto',
    background: '#16a085',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '8px 14px',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '0.9rem',
    boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
  },
  header: {
    background: '#16a085',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 14px',
    borderRadius: '8px 8px 0 0',
  },
  title: { fontWeight: 700, fontSize: '0.95rem' },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#fff',
    cursor: 'pointer',
    fontSize: '1rem',
    lineHeight: 1,
    padding: 2,
  },
  body: {
    padding: '12px 14px 16px',
    display: 'flex',
    flexDirection: 'column',
  },
  label: {
    fontSize: '0.78rem',
    color: '#666',
    marginBottom: 4,
  },
  input: {
    width: '100%',
    boxSizing: 'border-box',
    border: '1px solid #ddd',
    borderRadius: 4,
    padding: '7px 10px',
    fontSize: '0.85rem',
    outline: 'none',
  },
  predictBtn: {
    marginTop: 14,
    padding: '9px',
    background: '#16a085',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '0.9rem',
  },
  error: {
    marginTop: 8,
    padding: '6px 10px',
    background: '#fce8e6',
    color: '#c5221f',
    borderRadius: 4,
    fontSize: '0.82rem',
  },
  result: {
    marginTop: 14,
    paddingTop: 14,
    borderTop: '1px solid #eee',
    textAlign: 'center',
  },
  resultStation: {
    fontSize: '0.82rem',
    color: '#666',
    marginBottom: 6,
  },
  resultNumber: {
    fontSize: '3rem',
    fontWeight: 700,
    lineHeight: 1,
  },
  resultLabel: {
    fontSize: '0.8rem',
    color: '#666',
    marginTop: 4,
  },
  resultMeta: {
    fontSize: '0.78rem',
    color: '#999',
    marginTop: 8,
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    background: '#fff',
    border: '1px solid #ddd',
    borderRadius: '0 0 6px 6px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
    zIndex: 2000,
    overflow: 'hidden',
  },
  suggestion: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 12px',
    cursor: 'pointer',
    fontSize: '0.83rem',
    borderBottom: '1px solid #f5f5f5',
  },
  suggestNum: {
    color: '#16a085',
    fontWeight: 700,
    fontSize: '0.78rem',
    minWidth: 34,
    flexShrink: 0,
  },
  suggestName: {
    flex: 1,
    color: '#222',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  suggestBikes: {
    color: '#2ecc71',
    fontSize: '0.78rem',
    flexShrink: 0,
  },
}
