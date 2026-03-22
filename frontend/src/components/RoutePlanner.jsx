import { useState } from 'react'

const NOMINATIM = 'https://nominatim.openstreetmap.org/search'

async function geocode(address) {
  const params = new URLSearchParams({
    format: 'json',
    q: address,
    limit: 1,
    viewbox: '-6.5,53.6,-6.0,53.2',
    bounded: 1,
  })
  const res = await fetch(`${NOMINATIM}?${params}`, {
    headers: { 'Accept-Language': 'en' },
  })
  const data = await res.json()
  if (!data.length) throw new Error(`No results for "${address}" in Dublin`)
  return {
    lat: parseFloat(data[0].lat),
    lng: parseFloat(data[0].lon),
    label: data[0].display_name,
  }
}

function fmtDist(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
}

function PlanResult({ plan }) {
  const { pickup_station: pickup, dropoff_station: dropoff } = plan
  return (
    <div style={s.result}>
      <div style={s.step}>
        <span style={s.stepIcon}>🚶</span>
        <div>
          <div style={s.stepLabel}>Walk {fmtDist(pickup.walking_distance_m)} to pick up</div>
          <div style={s.stepStation}>{pickup.name}</div>
          <div style={s.stepDetail}>
            {pickup.available_bikes} bike{pickup.available_bikes !== 1 ? 's' : ''} available
          </div>
        </div>
      </div>

      <div style={s.connector} />

      <div style={s.step}>
        <span style={s.stepIcon}>🚲</span>
        <div>
          <div style={s.stepLabel}>Ride to drop off</div>
          <div style={s.stepStation}>{dropoff.name}</div>
          <div style={s.stepDetail}>
            {dropoff.available_bike_stands} stand{dropoff.available_bike_stands !== 1 ? 's' : ''} available
          </div>
        </div>
      </div>

      <div style={s.connector} />

      <div style={s.step}>
        <span style={s.stepIcon}>🏁</span>
        <div>
          <div style={s.stepLabel}>Walk {fmtDist(dropoff.walking_distance_m)} to destination</div>
        </div>
      </div>

      <div style={s.totalRow}>Total walking: {fmtDist(plan.total_walking_m)}</div>
    </div>
  )
}

export default function RoutePlanner({
  startPoint, endPoint,
  setStartPoint, setEndPoint,
  clickMode, setClickMode,
  plan, onPlanComputed, onClear,
}) {
  const [startText, setStartText] = useState('')
  const [endText, setEndText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(true)

  function handleClose() {
    setOpen(false)
    setStartText('')
    setEndText('')
    onClear()
  }

  function handleSwap() {
    const tmpText = startText
    const tmpPoint = startPoint
    setStartText(endText)
    setStartPoint(endPoint)
    setEndText(tmpText)
    setEndPoint(tmpPoint)
  }

  async function handlePlan() {
    setError(null)
    setLoading(true)
    try {
      let start = startPoint
      let end = endPoint

      if (!start) {
        if (!startText.trim()) throw new Error('Please enter or select a start location')
        start = await geocode(startText)
        setStartPoint(start)
      }
      if (!end) {
        if (!endText.trim()) throw new Error('Please enter or select a destination')
        end = await geocode(endText)
        setEndPoint(end)
      }

      const params = new URLSearchParams({
        start_lat: start.lat,
        start_lng: start.lng,
        end_lat: end.lat,
        end_lng: end.lng,
      })
      const res = await fetch(`/api/plan?${params}`)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error ?? json.details ?? 'Failed to plan route')
      onPlanComputed(json)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={s.openBtn}>
        ↗ Directions
      </button>
    )
  }

  return (
    <div style={s.panel}>
      {/* Header */}
      <div style={s.header}>
        <span style={s.title}>Route Plan</span>
        <button onClick={handleClose} style={s.closeBtn} title="Close">✕</button>
      </div>

      {/* Inputs */}
      <div style={s.inputs}>
        <div style={s.inputRow}>
          <span style={{ ...s.dot, background: '#1a73e8' }}>A</span>
          <input
            style={s.input}
            placeholder="Start — type or click map"
            value={startPoint ? startPoint.label : startText}
            onChange={e => { setStartText(e.target.value); setStartPoint(null) }}
            onFocus={() => setClickMode('start')}
          />
        </div>

        <div style={s.swapRow}>
          <div style={s.vertLine} />
          <button onClick={handleSwap} style={s.swapBtn} title="Swap start and destination">⇅</button>
        </div>

        <div style={s.inputRow}>
          <span style={{ ...s.dot, background: '#e74c3c' }}>B</span>
          <input
            style={s.input}
            placeholder="Destination — type or click map"
            value={endPoint ? endPoint.label : endText}
            onChange={e => { setEndText(e.target.value); setEndPoint(null) }}
            onFocus={() => setClickMode('end')}
          />
        </div>
      </div>

      {/* Click-mode hint */}
      {clickMode && (
        <div style={s.clickHint}>
          Click on the map to set {clickMode === 'start' ? 'start point' : 'destination'}
        </div>
      )}

      {/* Action button */}
      <button onClick={handlePlan} disabled={loading} style={s.planBtn}>
        {loading ? 'Planning…' : 'Get Directions'}
      </button>

      {error && <div style={s.error}>{error}</div>}

      {plan && <PlanResult plan={plan} />}
    </div>
  )
}

const s = {
  panel: {
    position: 'absolute',
    top: 12,
    left: 12,
    zIndex: 1000,
    background: '#fff',
    borderRadius: 8,
    boxShadow: '0 2px 16px rgba(0,0,0,0.22)',
    width: 300,
    maxHeight: 'calc(100% - 24px)',
    overflowY: 'auto',
    fontFamily: "'Segoe UI', Arial, sans-serif",
  },
  header: {
    background: '#1a73e8',
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
  inputs: { padding: '12px 12px 0' },
  inputRow: { display: 'flex', alignItems: 'center', gap: 8 },
  dot: {
    width: 22,
    height: 22,
    borderRadius: 11,
    color: '#fff',
    fontSize: '0.72rem',
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  input: {
    flex: 1,
    border: '1px solid #ddd',
    borderRadius: 4,
    padding: '7px 10px',
    fontSize: '0.85rem',
    outline: 'none',
    minWidth: 0,
  },
  swapRow: {
    display: 'flex',
    alignItems: 'center',
    height: 28,
    paddingLeft: 3,
  },
  vertLine: {
    width: 2,
    height: 28,
    background: '#e0e0e0',
    marginLeft: 9,
  },
  swapBtn: {
    background: '#fff',
    border: '1px solid #ddd',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: '1rem',
    width: 28,
    height: 28,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 'auto',
    color: '#555',
  },
  clickHint: {
    margin: '8px 12px 0',
    padding: '5px 10px',
    background: '#e8f0fe',
    color: '#1a73e8',
    borderRadius: 4,
    fontSize: '0.78rem',
  },
  planBtn: {
    display: 'block',
    width: 'calc(100% - 24px)',
    margin: '12px',
    padding: '9px',
    background: '#1a73e8',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '0.9rem',
  },
  error: {
    margin: '-4px 12px 10px',
    padding: '6px 10px',
    background: '#fce8e6',
    color: '#c5221f',
    borderRadius: 4,
    fontSize: '0.82rem',
  },
  result: {
    borderTop: '1px solid #eee',
    padding: '14px 12px',
  },
  step: { display: 'flex', gap: 10, alignItems: 'flex-start' },
  stepIcon: { fontSize: '1.2rem', flexShrink: 0, marginTop: 1 },
  stepLabel: { fontSize: '0.8rem', color: '#666' },
  stepStation: { fontSize: '0.9rem', fontWeight: 600, color: '#1a1a1a', marginTop: 2 },
  stepDetail: { fontSize: '0.78rem', color: '#1a73e8', marginTop: 2 },
  connector: {
    borderLeft: '2px dashed #ddd',
    height: 18,
    margin: '4px 0 4px 11px',
  },
  totalRow: {
    marginTop: 12,
    paddingTop: 10,
    borderTop: '1px solid #f0f0f0',
    fontSize: '0.82rem',
    color: '#555',
  },
  openBtn: {
    position: 'absolute',
    top: 12,
    left: 12,
    zIndex: 1000,
    background: '#1a73e8',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '8px 14px',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '0.9rem',
    boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
  },
}
