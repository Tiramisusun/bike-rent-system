import { useState, useRef, useEffect } from 'react'

const NOMINATIM = 'https://nominatim.openstreetmap.org/search'

/** Returns true if the string looks like an Irish Eircode, e.g. A96R8C4 or D02 XY45 */
function isEircode(q) {
  return /^[A-Za-z0-9]{3}\s?[A-Za-z0-9]{4}$/.test(q.trim())
}

/** Format Eircode to "XXX XXXX" canonical form */
function formatEircode(q) {
  const raw = q.trim().toUpperCase().replace(/\s/g, '')
  return `${raw.slice(0, 3)} ${raw.slice(3)}`
}

async function geocode(address) {
  const headers = { 'Accept-Language': 'en' }

  // If it looks like an Eircode, try the backend proxy first (OpenCage or formatted Nominatim)
  if (isEircode(address)) {
    try {
      const res = await fetch(`/api/geocode/eircode?q=${encodeURIComponent(formatEircode(address))}`)
      if (res.ok) {
        const d = await res.json()
        if (d.lat) return d
      }
    } catch { /* fall through to Nominatim */ }
  }

  // 1st attempt: Dublin bounding box
  const dublinParams = new URLSearchParams({
    format: 'json',
    q: isEircode(address) ? `${formatEircode(address)}, Ireland` : address,
    limit: 1,
    viewbox: '-6.5,53.6,-6.0,53.2',
    bounded: 1,
  })
  let res = await fetch(`${NOMINATIM}?${dublinParams}`, { headers })
  let data = await res.json()

  // 2nd attempt: Ireland-wide (catches Eircodes & county names)
  if (!data.length) {
    const ieParams = new URLSearchParams({
      format: 'json',
      q: isEircode(address) ? `${formatEircode(address)}, Ireland` : address,
      limit: 1,
      countrycodes: 'ie',
    })
    res = await fetch(`${NOMINATIM}?${ieParams}`, { headers })
    data = await res.json()
  }

  if (!data.length) throw new Error(`No results found for "${address}"`)
  return {
    lat: parseFloat(data[0].lat),
    lng: parseFloat(data[0].lon),
    label: data[0].display_name,
  }
}

function fmtDist(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
}

function fmtMin(min) {
  if (min < 1) return '<1 min'
  return `${Math.round(min)} min`
}

function PredictedStandsBadge({ n }) {
  if (n == null) return null
  const color = n === 0 ? '#e74c3c' : n <= 3 ? '#f39c12' : '#27ae60'
  return (
    <span style={{ color, fontWeight: 700, fontSize: '0.85rem' }}>
      {' '}· 🔮 {n} stand{n !== 1 ? 's' : ''} predicted
    </span>
  )
}

function BikeRouteDetail({ pickup, dropoff, times, totalWalkingM, waypoints = [] }) {
  return (
    <>
      <div style={s.step}>
        <span style={s.stepIcon}>🚶</span>
        <div>
          <div style={s.stepLabel}>Walk to pickup · {fmtMin(times.walk_to_pickup)}</div>
          <div style={s.stepStation}>{pickup.name}</div>
          <div style={s.stepDetail}>
            {pickup.available_bikes} bike{pickup.available_bikes !== 1 ? 's' : ''} available
            · {fmtDist(pickup.walking_distance_m)} away
          </div>
        </div>
      </div>
      <div style={s.connector} />
      <div style={s.step}>
        <span style={s.stepIcon}>🚲</span>
        <div>
          <div style={s.stepLabel}>Ride · {fmtMin(times.bike)}</div>
          {waypoints.map((wp, i) => (
            <div key={i} style={{ ...s.stepDetail, color: WAYPOINT_COLORS[i % WAYPOINT_COLORS.length], marginBottom: 2 }}>
              📍 Stop {i + 1}: {wp.label}
            </div>
          ))}
          <div style={s.stepStation}>{dropoff.name}</div>
          <div style={s.stepDetail}>
            {dropoff.available_bike_stands} stand{dropoff.available_bike_stands !== 1 ? 's' : ''} free now
            <PredictedStandsBadge n={dropoff.predicted_stands} />
          </div>
        </div>
      </div>
      <div style={s.connector} />
      <div style={s.step}>
        <span style={s.stepIcon}>🏁</span>
        <div>
          <div style={s.stepLabel}>Walk to destination · {fmtMin(times.walk_to_destination)}</div>
          <div style={s.stepDetail}>{fmtDist(dropoff.walking_distance_m)} away</div>
        </div>
      </div>
      <div style={s.totalRow}>
        Total ~{fmtMin(times.total_travel)}
        <span style={s.totalSub}> · {fmtDist(totalWalkingM)} walking</span>
      </div>
    </>
  )
}


function PlanResult({ plan, onSelectAlt }) {
  const [showAlts, setShowAlts] = useState(false)

  if (plan.mode === 'walk_only') {
    return (
      <div style={s.result}>
        <div style={s.walkOnlyBadge}>Walk only</div>
        <div style={s.step}>
          <span style={s.stepIcon}>🚶</span>
          <div>
            <div style={s.stepLabel}>Walk directly to destination</div>
            <div style={s.stepDetail}>{fmtMin(plan.walk_minutes)}</div>
          </div>
        </div>
        <div style={s.totalRow}>{plan.reason}</div>
      </div>
    )
  }

  const { pickup_station: pickup, dropoff_station: dropoff, times_minutes: times, alternatives = [] } = plan
  return (
    <div style={s.result}>
      <BikeRouteDetail
        pickup={pickup}
        dropoff={dropoff}
        times={times}
        totalWalkingM={plan.total_walking_m}
        waypoints={plan._waypoints ?? []}
      />

      {alternatives.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button
            style={s.altToggleBtn}
            onClick={() => setShowAlts(v => !v)}
          >
            {showAlts ? '▲ Hide' : `▼ ${alternatives.length} alternative route${alternatives.length > 1 ? 's' : ''}`}
          </button>

          {showAlts && alternatives.map((alt, i) => (
            <div key={i} style={s.altCard}>
              <div style={s.altHeader}>
                <span style={s.altNum}>Option {i + 2}</span>
                <span style={s.altTime}>~{fmtMin(alt.times_minutes.total_travel)}</span>
                <button
                  style={s.altSelectBtn}
                  onClick={() => onSelectAlt(alt)}
                >
                  Use this
                </button>
              </div>
              <div style={s.altBody}>
                <span>🚶 {fmtMin(alt.times_minutes.walk_to_pickup)}</span>
                <span style={{ color: '#aaa' }}>→</span>
                <span style={s.altStation}>{alt.pickup.name}</span>
                <span style={{ color: '#aaa' }}>→</span>
                <span>🚲 {fmtMin(alt.times_minutes.bike)}</span>
                <span style={{ color: '#aaa' }}>→</span>
                <span style={s.altStation}>{alt.dropoff.name}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StationInput({ label, dotColor, value, onChange, onSelectStation, onFocus, stations, placeholder }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  const query = value.trim().toLowerCase()
  const suggestions = query.length >= 1
    ? stations.filter(st =>
        st.name.toLowerCase().includes(query) ||
        String(st.number).includes(query)
      ).slice(0, 6)
    : []

  // Close dropdown on outside click
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
          onFocus={() => { onFocus(); setOpen(true) }}
          autoComplete="off"
        />
      </div>
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

const WAYPOINT_COLORS = ['#9b59b6', '#e67e22', '#16a085', '#c0392b', '#2980b9']

export default function RoutePlanner({
  startPoint, endPoint,
  setStartPoint, setEndPoint,
  clickMode, setClickMode,
  plan, onPlanComputed, onClear,
  stations = [],
}) {
  const [startText, setStartText] = useState('')
  const [endText, setEndText] = useState('')
  // waypoints: array of { point: {lat,lng,label} | null, text: string }
  const [waypoints, setWaypoints] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(false)

  function handleClose() {
    setOpen(false)
    setStartText('')
    setEndText('')
    setWaypoints([])
    onClear()
  }

  function handleSwap() {
    setStartText(endText); setStartPoint(endPoint)
    setEndText(startText); setEndPoint(startPoint)
  }

  function addWaypoint() {
    setWaypoints(wps => [...wps, { point: null, text: '' }])
  }

  function removeWaypoint(i) {
    setWaypoints(wps => wps.filter((_, idx) => idx !== i))
  }

  function updateWaypointText(i, text) {
    setWaypoints(wps => wps.map((wp, idx) => idx === i ? { ...wp, text, point: null } : wp))
  }

  function updateWaypointPoint(i, point) {
    setWaypoints(wps => wps.map((wp, idx) => idx === i ? { ...wp, point, text: '' } : wp))
  }

  async function resolvePoint(point, text, label) {
    if (point) return point
    if (!text.trim()) throw new Error(`Please enter ${label}`)
    return geocode(text)
  }

  async function handlePlan() {
    setError(null)
    setLoading(true)
    try {
      const start = await resolvePoint(startPoint, startText, 'a start location')
      setStartPoint(start)

      const resolvedWaypoints = []
      for (let i = 0; i < waypoints.length; i++) {
        const wp = waypoints[i]
        const resolved = await resolvePoint(wp.point, wp.text, `waypoint ${i + 1}`)
        resolvedWaypoints.push(resolved)
        updateWaypointPoint(i, resolved)
      }

      const end = await resolvePoint(endPoint, endText, 'a destination')
      setEndPoint(end)

      const params = new URLSearchParams({
        start_lat: start.lat, start_lng: start.lng,
        end_lat: end.lat, end_lng: end.lng,
      })
      if (resolvedWaypoints.length > 0) {
        params.set('waypoints', resolvedWaypoints.map(p => `${p.lat},${p.lng}`).join(';'))
      }

      const res = await fetch(`/api/plan?${params}`)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error ?? json.details ?? 'Failed to plan route')
      // Attach resolved waypoints so map can show them
      json._waypoints = resolvedWaypoints
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
        <StationInput
          label="A"
          dotColor="#16a085"
          placeholder="Start — station name, number or address"
          value={startPoint ? startPoint.label : startText}
          onChange={v => { setStartText(v); setStartPoint(null) }}
          onSelectStation={pt => { setStartPoint(pt); setStartText('') }}
          onFocus={() => setClickMode('start')}
          stations={stations}
        />

        {/* Waypoints */}
        {waypoints.map((wp, i) => (
          <div key={i}>
            <div style={s.waypointConnector}>
              <div style={s.vertLine} />
              <button
                style={s.removeWpBtn}
                onClick={() => removeWaypoint(i)}
                title="Remove stop"
              >✕</button>
            </div>
            <StationInput
              label={String(i + 1)}
              dotColor={WAYPOINT_COLORS[i % WAYPOINT_COLORS.length]}
              placeholder={`Stop ${i + 1} — station or address`}
              value={wp.point ? wp.point.label : wp.text}
              onChange={v => updateWaypointText(i, v)}
              onSelectStation={pt => updateWaypointPoint(i, pt)}
              onFocus={() => {}}
              stations={stations}
            />
          </div>
        ))}

        <div style={s.swapRow}>
          <div style={s.vertLine} />
          <button onClick={handleSwap} style={s.swapBtn} title="Swap start and destination">⇅</button>
          <button onClick={addWaypoint} style={s.addWpBtn} title="Add a stop">+ Stop</button>
        </div>

        <StationInput
          label="B"
          dotColor="#e74c3c"
          placeholder="Destination — station name, number or address"
          value={endPoint ? endPoint.label : endText}
          onChange={v => { setEndText(v); setEndPoint(null) }}
          onSelectStation={pt => { setEndPoint(pt); setEndText('') }}
          onFocus={() => setClickMode('end')}
          stations={stations}
        />
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

      {plan && (
        <PlanResult
          plan={plan}
          onSelectAlt={alt => {
            onPlanComputed({
              ...plan,
              pickup_station: {
                station_id: alt.pickup.station_id,
                name: alt.pickup.name,
                position: { lat: alt.pickup.lat, lng: alt.pickup.lng },
                available_bikes: alt.pickup.avail_bikes,
                walking_distance_m: alt.pickup.distance_m,
                status: alt.pickup.status,
              },
              dropoff_station: {
                station_id: alt.dropoff.station_id,
                name: alt.dropoff.name,
                position: { lat: alt.dropoff.lat, lng: alt.dropoff.lng },
                available_bike_stands: alt.dropoff.avail_docks,
                walking_distance_m: alt.dropoff.distance_m,
                status: alt.dropoff.status,
              },
              times_minutes: alt.times_minutes,
              total_walking_m: Math.round(alt.pickup.distance_m + alt.dropoff.distance_m),
              polylines: plan.polylines,
              alternatives: [],
            })
          }}
        />
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
    color: '#16a085',
    borderRadius: 4,
    fontSize: '0.78rem',
  },
  planBtn: {
    display: 'block',
    width: 'calc(100% - 24px)',
    margin: '12px',
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
  stepDetail: { fontSize: '0.78rem', color: '#16a085', marginTop: 2 },
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
    color: '#333',
    fontWeight: 600,
  },
  totalSub: {
    fontWeight: 400,
    color: '#777',
  },
  waypointConnector: {
    display: 'flex',
    alignItems: 'center',
    height: 28,
    paddingLeft: 3,
    gap: 6,
  },
  removeWpBtn: {
    background: 'none',
    border: '1px solid #ddd',
    borderRadius: '50%',
    width: 20,
    height: 20,
    fontSize: '0.7rem',
    cursor: 'pointer',
    color: '#999',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 0,
    marginLeft: 'auto',
  },
  addWpBtn: {
    background: 'none',
    border: '1px dashed #16a085',
    borderRadius: 4,
    color: '#16a085',
    fontSize: '0.75rem',
    fontWeight: 600,
    padding: '2px 8px',
    cursor: 'pointer',
    marginLeft: 8,
  },
  segCard: {
    border: '1px solid #eee',
    borderRadius: 6,
    overflow: 'hidden',
    marginBottom: 8,
  },
  segHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '5px 10px',
    color: '#fff',
    fontSize: '0.8rem',
    fontWeight: 700,
  },
  segTime: { fontWeight: 400, fontSize: '0.78rem' },
  segBody: { padding: '8px 10px' },
  segRow: { fontSize: '0.8rem', color: '#333', marginBottom: 3 },
  altToggleBtn: {
    width: '100%',
    background: 'none',
    border: '1px solid #e0e0e0',
    borderRadius: 4,
    padding: '5px 8px',
    cursor: 'pointer',
    fontSize: '0.78rem',
    color: '#555',
    textAlign: 'left',
  },
  altCard: {
    marginTop: 6,
    border: '1px solid #eee',
    borderRadius: 6,
    overflow: 'hidden',
  },
  altHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '6px 10px',
    background: '#f8f9fa',
    borderBottom: '1px solid #eee',
  },
  altNum: { fontWeight: 700, fontSize: '0.78rem', color: '#555', flex: 1 },
  altTime: { fontSize: '0.82rem', fontWeight: 600, color: '#16a085' },
  altSelectBtn: {
    background: '#16a085',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    padding: '3px 8px',
    cursor: 'pointer',
    fontSize: '0.75rem',
    fontWeight: 600,
  },
  altBody: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 4,
    padding: '6px 10px',
    fontSize: '0.78rem',
    color: '#333',
  },
  altStation: {
    fontWeight: 600,
    color: '#111',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth: 80,
  },
  walkOnlyBadge: {
    display: 'inline-block',
    marginBottom: 10,
    padding: '2px 8px',
    background: '#f1f3f4',
    color: '#555',
    borderRadius: 12,
    fontSize: '0.75rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
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
    transition: 'background 0.1s',
    ':hover': { background: '#f0f4ff' },
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
}
