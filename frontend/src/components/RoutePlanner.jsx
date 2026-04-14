import { useState, useRef, useEffect } from 'react'

const NOMINATIM = 'https://nominatim.openstreetmap.org/search'

function isEircode(q) {
  return /^[A-Za-z0-9]{3}\s?[A-Za-z0-9]{4}$/.test(q.trim())
}
function formatEircode(q) {
  const raw = q.trim().toUpperCase().replace(/\s/g, '')
  return `${raw.slice(0, 3)} ${raw.slice(3)}`
}

async function geocode(address) {
  const headers = { 'Accept-Language': 'en' }
  if (isEircode(address)) {
    try {
      const res = await fetch(`/api/geocode/eircode?q=${encodeURIComponent(formatEircode(address))}`)
      if (res.ok) { const d = await res.json(); if (d.lat) return d }
    } catch { /* fall through */ }
  }
  const dublinParams = new URLSearchParams({
    format: 'json',
    q: isEircode(address) ? `${formatEircode(address)}, Ireland` : address,
    limit: 1, viewbox: '-6.5,53.6,-6.0,53.2', bounded: 1,
  })
  let res = await fetch(`${NOMINATIM}?${dublinParams}`, { headers })
  let data = await res.json()
  if (!data.length) {
    const ieParams = new URLSearchParams({
      format: 'json',
      q: isEircode(address) ? `${formatEircode(address)}, Ireland` : address,
      limit: 1, countrycodes: 'ie',
    })
    res = await fetch(`${NOMINATIM}?${ieParams}`, { headers })
    data = await res.json()
  }
  if (!data.length) throw new Error(`No results found for "${address}"`)
  return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon), label: data[0].display_name }
}

function fmtMin(min) {
  if (min < 1) return '<1 min'
  return `${Math.round(min)} min`
}

// ── Shared address input with station autocomplete ────────────────────────────
function AddressInput({ label, dotColor, value, onChange, onSelectStation, onFocus, stations, placeholder }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const query = value.trim().toLowerCase()
  const suggestions = query.length >= 1
    ? stations.filter(st =>
        st.name.toLowerCase().includes(query) || String(st.number).includes(query)
      ).slice(0, 6)
    : []

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <div style={s.inputRow}>
        <span style={{ ...s.dot, background: dotColor }}>{label}</span>
        <input
          style={s.input}
          placeholder={placeholder}
          value={value}
          onChange={e => { onChange(e.target.value); setOpen(true) }}
          onFocus={() => { onFocus?.(); setOpen(true) }}
          autoComplete="off"
        />
      </div>
      {open && suggestions.length > 0 && (
        <div style={s.dropdown}>
          {suggestions.map(st => (
            <div key={st.number} style={s.suggestion}
              onMouseEnter={e => e.currentTarget.style.background = '#f0f4ff'}
              onMouseLeave={e => e.currentTarget.style.background = ''}
              onMouseDown={e => {
                e.preventDefault()
                onSelectStation({ lat: st.position.lat, lng: st.position.lng, label: st.name })
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

// ── Candidate station card ────────────────────────────────────────────────────
function CandidateCard({ station, type, selected, onClick }) {
  const value   = type === 'pickup' ? station.predicted_bikes : station.predicted_docks
  const maxVal  = 20
  const alpha   = 0.25 + Math.min(value / maxVal, 1) * 0.75
  const bgColor = type === 'pickup'
    ? `rgba(39,174,96,${alpha})`
    : `rgba(231,76,60,${alpha})`
  const label   = type === 'pickup' ? `🚲 ${value} bikes predicted` : `🅿️ ${value} docks predicted`

  return (
    <div
      onClick={onClick}
      style={{
        ...s.candidateCard,
        border: selected ? '2px solid #1a73e8' : '2px solid transparent',
        background: selected ? '#e8f0fe' : '#fff',
      }}
    >
      <div style={{ ...s.candidateBar, background: bgColor }} />
      <div style={s.candidateBody}>
        <div style={s.candidateName}>{station.name}</div>
        <div style={s.candidateMeta}>
          {label} · {Math.round(station.distance_m ?? 0)} m away
        </div>
      </div>
      {selected && <span style={s.checkmark}>✓</span>}
    </div>
  )
}

// ── Route result ──────────────────────────────────────────────────────────────
function RouteResult({ plan }) {
  const prefLabel = { recommended: 'Bike paths', fastest: 'Fastest', shortest: 'Shortest' }
  const { pickup_station: pickup, dropoff_station: dropoff,
          times_minutes: times, cycling_preference } = plan

  return (
    <div style={s.result}>
      <div style={s.step}>
        <span style={s.stepIcon}>🚶</span>
        <div>
          <div style={s.stepLabel}>Walk to pickup · {fmtMin(times.walk_to_pickup)}</div>
          <div style={s.stepStation}>{pickup.name}</div>
          <div style={s.stepDetail}>{pickup.available_bikes} bikes available</div>
        </div>
      </div>
      <div style={s.connector} />
      <div style={s.step}>
        <span style={s.stepIcon}>🚲</span>
        <div>
          <div style={s.stepLabel}>Ride · {fmtMin(times.bike)} · {prefLabel[cycling_preference]}</div>
          <div style={s.stepStation}>{dropoff.name}</div>
          <div style={s.stepDetail}>{dropoff.available_bike_stands} stands free</div>
        </div>
      </div>
      <div style={s.connector} />
      <div style={s.step}>
        <span style={s.stepIcon}>🏁</span>
        <div>
          <div style={s.stepLabel}>Walk to destination · {fmtMin(times.walk_to_destination)}</div>
        </div>
      </div>
      <div style={s.totalRow}>Total ~{fmtMin(times.total_travel)}</div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function RoutePlanner({
  startPoint, endPoint,
  setStartPoint, setEndPoint,
  clickMode, setClickMode,
  onPlanComputed, onClear,
  stations,
  onFetchCandidates,
  onSelectPickup, onSelectDropoff,
}) {
  const [open, setOpen]               = useState(false)
  const [phase, setPhase]             = useState('input')
  const [startText, setStartText]     = useState('')
  const [endText, setEndText]         = useState('')
  const [departureTime, setDeparture] = useState(() => new Date().toISOString().slice(0, 16))
  const [preference, setPreference]   = useState('recommended')
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState(null)

  const [candidates, setCandidates]   = useState(null)
  const [pickup, setPickup]           = useState(null)
  const [dropoff, setDropoff]         = useState(null)
  const [plan, setPlan]               = useState(null)

  // ── Close / clear ─────────────────────────────────────────────────────────
  function handleClose() {
    setOpen(false)
    setPhase('input')
    setStartText(''); setEndText('')
    setCandidates(null)
    setPickup(null); setDropoff(null)
    setPlan(null)
    setError(null)
    onClear()
    onFetchCandidates(null)
    onSelectPickup(null)
    onSelectDropoff(null)
  }

  // ── Phase 1 → 2: geocode points, fetch candidates ─────────────────────────
  async function handleFindStations() {
    setError(null)
    setLoading(true)
    try {
      const start = startPoint ?? await geocode(startText)
      setStartPoint(start)
      const end = endPoint ?? await geocode(endText)
      setEndPoint(end)

      const params = new URLSearchParams({
        start_lat: start.lat, start_lng: start.lng,
        end_lat:   end.lat,   end_lng:   end.lng,
        departure_time: new Date(departureTime).toISOString(),
      })
      const res = await fetch(`/api/plan/candidates?${params}`)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error ?? 'Failed to fetch candidates')

      setCandidates(json)
      setPickup(null); setDropoff(null)
      onFetchCandidates(json)
      onSelectPickup(null); onSelectDropoff(null)
      setPhase('select')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function handlePickupSelect(st) {
    setPickup(st)
    onSelectPickup(st)
  }

  function handleDropoffSelect(st) {
    setDropoff(st)
    onSelectDropoff(st)
  }

  // ── Phase 3 → 4: compute route ────────────────────────────────────────────
  async function handleGetDirections() {
    setError(null)
    setLoading(true)
    try {
      const start = startPoint
      const end   = endPoint
      const params = new URLSearchParams({
        pickup_id:  pickup.station_id,
        dropoff_id: dropoff.station_id,
        start_lat: start.lat, start_lng: start.lng,
        end_lat:   end.lat,   end_lng:   end.lng,
        preference,
      })
      const res = await fetch(`/api/plan/route?${params}`)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error ?? 'Failed to compute route')

      setPlan(json)
      onPlanComputed(json)
      setPhase('result')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Closed state ──────────────────────────────────────────────────────────
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
        <button onClick={handleClose} style={s.closeBtn}>✕</button>
      </div>

      {/* ── Phase 1: Input ── */}
      {phase === 'input' && (
        <div style={s.body}>
          <AddressInput
            label="A" dotColor="#16a085"
            placeholder="Start — station name or address"
            value={startPoint ? startPoint.label : startText}
            onChange={v => { setStartText(v); setStartPoint(null) }}
            onSelectStation={pt => { setStartPoint(pt); setStartText('') }}
            onFocus={() => setClickMode('start')}
            stations={stations}
          />
          <div style={{ marginTop: 8 }}>
            <AddressInput
              label="B" dotColor="#e74c3c"
              placeholder="Destination — station name or address"
              value={endPoint ? endPoint.label : endText}
              onChange={v => { setEndText(v); setEndPoint(null) }}
              onSelectStation={pt => { setEndPoint(pt); setEndText('') }}
              onFocus={() => setClickMode('end')}
              stations={stations}
            />
          </div>

          <div style={s.fieldRow}>
            <label style={s.fieldLabel}>Departure time</label>
            <input
              type="datetime-local"
              value={departureTime}
              onChange={e => setDeparture(e.target.value)}
              style={s.datetimeInput}
            />
          </div>
          {clickMode && (
            <div style={s.clickHint}>
              Click on the map to set {clickMode === 'start' ? 'start point' : 'destination'}
            </div>
          )}
          <button onClick={handleFindStations} disabled={loading} style={s.primaryBtn}>
            {loading ? 'Finding stations…' : 'Find Stations'}
          </button>
          {error && <div style={s.error}>{error}</div>}
        </div>
      )}

      {/* ── Phase 2: Select stations ── */}
      {phase === 'select' && candidates && (
        <div style={s.body}>
          <div style={s.sectionTitle}>
            Pickup station <span style={s.sectionSub}>(ML predicted · departure time)</span>
          </div>
          {candidates.pickup_candidates.length === 0
            ? <div style={s.emptyMsg}>No stations with enough bikes nearby.</div>
            : candidates.pickup_candidates.map(st => (
                <CandidateCard
                  key={st.station_id}
                  station={st} type="pickup"
                  selected={pickup?.station_id === st.station_id}
                  onClick={() => handlePickupSelect(st)}
                />
              ))
          }

          <div style={{ height: 10 }} />

          <div style={s.sectionTitle}>
            Dropoff station <span style={s.sectionSub}>(ML predicted · arrival time)</span>
          </div>
          {candidates.dropoff_candidates.length === 0
            ? <div style={s.emptyMsg}>No stations nearby.</div>
            : candidates.dropoff_candidates.map(st => (
                <CandidateCard
                  key={st.station_id}
                  station={st} type="dropoff"
                  selected={dropoff?.station_id === st.station_id}
                  onClick={() => handleDropoffSelect(st)}
                />
              ))
          }

          {error && <div style={s.error}>{error}</div>}

          <div style={s.btnRow}>
            <button onClick={() => { setPhase('input'); onFetchCandidates(null) }} style={s.secondaryBtn}>
              ← Back
            </button>
            <button
              onClick={() => {
                if (!pickup || !dropoff) { setError('Select both a pickup and dropoff station.'); return }
                setError(null)
                setPhase('preference')
              }}
              style={s.primaryBtn}
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {/* ── Phase 3: Preference ── */}
      {phase === 'preference' && (
        <div style={s.body}>
          <div style={s.summaryBox}>
            <div style={s.summaryRow}>
              <span style={s.summaryLabel}>Pickup</span>
              <span>{pickup?.name}</span>
            </div>
            <div style={s.summaryRow}>
              <span style={s.summaryLabel}>Dropoff</span>
              <span>{dropoff?.name}</span>
            </div>
          </div>
          <div style={s.sectionTitle}>Cycling preference</div>
          {[
            { value: 'recommended', label: '🛤️ Bike paths preferred', desc: 'Safer, slightly longer' },
            { value: 'fastest',     label: '⚡ Fastest',              desc: 'Shortest time' },
            { value: 'shortest',    label: '📏 Shortest distance',    desc: 'Fewest kilometres' },
          ].map(opt => (
            <div
              key={opt.value}
              onClick={() => setPreference(opt.value)}
              style={{
                ...s.prefCard,
                border: preference === opt.value ? '2px solid #1a73e8' : '2px solid #eee',
                background: preference === opt.value ? '#e8f0fe' : '#fff',
              }}
            >
              <div style={s.prefLabel}>{opt.label}</div>
              <div style={s.prefDesc}>{opt.desc}</div>
            </div>
          ))}
          {error && <div style={s.error}>{error}</div>}
          <div style={s.btnRow}>
            <button onClick={() => setPhase('select')} style={s.secondaryBtn}>← Back</button>
            <button onClick={handleGetDirections} disabled={loading} style={s.primaryBtn}>
              {loading ? 'Calculating…' : 'Get Directions'}
            </button>
          </div>
        </div>
      )}

      {/* ── Phase 4: Result ── */}
      {phase === 'result' && plan && (
        <div>
          <RouteResult plan={plan} />
          <div style={{ padding: '0 12px 12px' }}>
            <button onClick={() => setPhase('preference')} style={s.secondaryBtn}>← Change preference</button>
          </div>
        </div>
      )}
    </div>
  )
}

const s = {
  panel: {
    background: '#fff',
    borderRadius: 8,
    boxShadow: '0 2px 16px rgba(0,0,0,0.22)',
    width: 300,
    maxHeight: 'calc(100vh - 120px)',
    overflowY: 'auto',
    fontFamily: "'Segoe UI', Arial, sans-serif",
    pointerEvents: 'auto',
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
  closeBtn: { background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: '1rem' },
  body: { padding: '12px' },
  inputRow: { display: 'flex', alignItems: 'center', gap: 8 },
  dot: {
    width: 22, height: 22, borderRadius: 11,
    color: '#fff', fontSize: '0.72rem', fontWeight: 700,
    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  input: {
    flex: 1, border: '1px solid #ddd', borderRadius: 4,
    padding: '7px 10px', fontSize: '0.85rem', outline: 'none', minWidth: 0,
  },
  fieldRow: { marginTop: 10 },
  fieldLabel: { display: 'block', fontSize: '0.78rem', color: '#666', marginBottom: 4 },
  datetimeInput: {
    width: '100%', border: '1px solid #ddd', borderRadius: 4,
    padding: '7px 10px', fontSize: '0.83rem', boxSizing: 'border-box',
  },
  clickHint: {
    margin: '8px 0', padding: '5px 10px',
    background: '#e8f0fe', color: '#16a085',
    borderRadius: 4, fontSize: '0.78rem',
  },
  primaryBtn: {
    display: 'block', width: '100%', marginTop: 12,
    padding: '9px', background: '#16a085', color: '#fff',
    border: 'none', borderRadius: 4, cursor: 'pointer',
    fontWeight: 600, fontSize: '0.9rem',
  },
  secondaryBtn: {
    padding: '7px 14px', background: '#f1f3f4', color: '#333',
    border: 'none', borderRadius: 4, cursor: 'pointer',
    fontSize: '0.85rem', fontWeight: 600,
  },
  btnRow: { display: 'flex', gap: 8, marginTop: 12, justifyContent: 'space-between' },
  error: {
    marginTop: 8, padding: '6px 10px',
    background: '#fce8e6', color: '#c5221f',
    borderRadius: 4, fontSize: '0.82rem',
  },
  sectionTitle: {
    fontSize: '0.8rem', fontWeight: 700, color: '#333',
    marginBottom: 6, marginTop: 4,
  },
  sectionSub: { fontWeight: 400, color: '#888', fontSize: '0.75rem' },
  emptyMsg: { fontSize: '0.82rem', color: '#999', padding: '6px 0' },
  candidateCard: {
    display: 'flex', alignItems: 'center',
    borderRadius: 6, overflow: 'hidden',
    marginBottom: 6, cursor: 'pointer',
    transition: 'border-color 0.15s',
    position: 'relative',
  },
  candidateBar: { width: 8, alignSelf: 'stretch', flexShrink: 0 },
  candidateBody: { padding: '7px 10px', flex: 1, minWidth: 0 },
  candidateName: { fontSize: '0.85rem', fontWeight: 600, color: '#1a1a1a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  candidateMeta: { fontSize: '0.75rem', color: '#555', marginTop: 2 },
  checkmark: { color: '#1a73e8', fontWeight: 700, padding: '0 10px', fontSize: '1rem' },
  summaryBox: {
    background: '#f8f9fa', borderRadius: 6,
    padding: '10px 12px', marginBottom: 12,
  },
  summaryRow: {
    display: 'flex', justifyContent: 'space-between',
    fontSize: '0.83rem', color: '#333', marginBottom: 4,
  },
  summaryLabel: { color: '#888', marginRight: 8, fontWeight: 600 },
  prefCard: {
    borderRadius: 6, padding: '9px 12px',
    marginBottom: 8, cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  prefLabel: { fontSize: '0.88rem', fontWeight: 600, color: '#1a1a1a' },
  prefDesc: { fontSize: '0.75rem', color: '#666', marginTop: 2 },
  result: { borderTop: '1px solid #eee', padding: '14px 12px' },
  step: { display: 'flex', gap: 10, alignItems: 'flex-start' },
  stepIcon: { fontSize: '1.2rem', flexShrink: 0, marginTop: 1 },
  stepLabel: { fontSize: '0.8rem', color: '#666' },
  stepStation: { fontSize: '0.9rem', fontWeight: 600, color: '#1a1a1a', marginTop: 2 },
  stepDetail: { fontSize: '0.78rem', color: '#16a085', marginTop: 2 },
  connector: { borderLeft: '2px dashed #ddd', height: 18, margin: '4px 0 4px 11px' },
  totalRow: {
    marginTop: 12, paddingTop: 10,
    borderTop: '1px solid #f0f0f0',
    fontSize: '0.82rem', color: '#333', fontWeight: 600,
  },
  openBtn: {
    pointerEvents: 'auto',
    background: '#16a085', color: '#fff',
    border: 'none', borderRadius: 6,
    padding: '8px 14px', cursor: 'pointer',
    fontWeight: 600, fontSize: '0.9rem',
    boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
  },
  dropdown: {
    position: 'absolute', top: '100%', left: 0, right: 0,
    background: '#fff', border: '1px solid #ddd',
    borderRadius: '0 0 6px 6px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
    zIndex: 2000, overflow: 'hidden',
  },
  suggestion: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '8px 12px', cursor: 'pointer',
    fontSize: '0.83rem', borderBottom: '1px solid #f5f5f5',
  },
  suggestNum: { color: '#16a085', fontWeight: 700, fontSize: '0.78rem', minWidth: 34, flexShrink: 0 },
  suggestName: { flex: 1, color: '#222', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  suggestBikes: { color: '#2ecc71', fontSize: '0.78rem', flexShrink: 0 },
}
