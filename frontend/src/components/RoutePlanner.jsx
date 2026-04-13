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
function fmtDist(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
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
          {fmtDist(station.distance_m)} away · {label}
        </div>
      </div>
      {selected && <span style={s.checkmark}>✓</span>}
    </div>
  )
}

// ── Multi-segment route result ────────────────────────────────────────────────
function RouteResult({ plans }) {
  const prefLabel = { recommended: 'Bike paths', fastest: 'Fastest', shortest: 'Shortest' }
  const totalTime = plans.reduce((sum, p) => sum + (p.times_minutes?.total_travel ?? 0), 0)
  const isMulti = plans.length > 1

  return (
    <div style={s.result}>
      {plans.map((plan, i) => {
        const { pickup_station: pickup, dropoff_station: dropoff,
                times_minutes: times, cycling_preference } = plan
        const isLast = i === plans.length - 1
        return (
          <div key={i}>
            {isMulti && <div style={s.legHeader}>Leg {i + 1}</div>}
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
              <span style={s.stepIcon}>{isLast ? '🏁' : '📍'}</span>
              <div>
                <div style={s.stepLabel}>
                  {isLast ? 'Walk to destination' : `Walk to stop ${i + 1}`} · {fmtMin(times.walk_to_destination)}
                </div>
              </div>
            </div>
            {!isLast && <div style={s.legDivider} />}
          </div>
        )
      })}
      <div style={s.totalRow}>Total ~{fmtMin(totalTime)}</div>
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

  // Multi-stop state
  const [waypointTexts, setWaypointTexts]     = useState([])   // raw text inputs
  const [waypointPoints, setWaypointPoints]   = useState([])   // geocoded {lat,lng,label}
  const [allCandidates, setAllCandidates]     = useState([])   // candidates per segment
  const [segmentSelections, setSegSels]       = useState([])   // [{pickup,dropoff}] per segment
  const [activeSegIdx, setActiveSegIdx]       = useState(0)
  const [segmentPlans, setSegmentPlans]       = useState([])   // final route per segment

  const currentCandidates = allCandidates[activeSegIdx]
  const currentSel = segmentSelections[activeSegIdx] ?? { pickup: null, dropoff: null }

  // ── Waypoint helpers ──────────────────────────────────────────────────────
  function addWaypoint() {
    setWaypointTexts(t => [...t, ''])
    setWaypointPoints(p => [...p, null])
  }
  function removeWaypoint(i) {
    setWaypointTexts(t => t.filter((_, j) => j !== i))
    setWaypointPoints(p => p.filter((_, j) => j !== i))
  }
  function updateWaypointText(i, v) {
    setWaypointTexts(t => t.map((x, j) => j === i ? v : x))
    setWaypointPoints(p => p.map((x, j) => j === i ? null : x))
  }
  function setWaypointPoint(i, pt) {
    setWaypointPoints(p => p.map((x, j) => j === i ? pt : x))
    setWaypointTexts(t => t.map((x, j) => j === i ? '' : x))
  }

  // ── Segment navigation ────────────────────────────────────────────────────
  function switchToSegment(idx) {
    // When jumping forward via dots, ensure all prior legs are complete
    if (idx > activeSegIdx) {
      const firstIncomplete = segmentSelections.findIndex(
        (sel, i) => i < idx && (!sel.pickup || !sel.dropoff)
      )
      if (firstIncomplete !== -1) {
        setError(`Complete Leg ${firstIncomplete + 1} first (select both pickup and dropoff)`)
        return
      }
    }
    setError(null)
    setActiveSegIdx(idx)
    onFetchCandidates(allCandidates[idx])
    const sel = segmentSelections[idx] ?? { pickup: null, dropoff: null }
    onSelectPickup(sel.pickup)
    onSelectDropoff(sel.dropoff)
  }

  function handlePickupSelect(st) {
    const idx = activeSegIdx   // capture before async batching
    setSegSels(prev => prev.map((sel, i) => i === idx ? { ...sel, pickup: st } : sel))
    onSelectPickup(st)
  }

  function handleDropoffSelect(st) {
    const idx = activeSegIdx
    setSegSels(prev => prev.map((sel, i) => i === idx ? { ...sel, dropoff: st } : sel))
    onSelectDropoff(st)
  }

  // ── Close / clear ─────────────────────────────────────────────────────────
  function handleClose() {
    setOpen(false)
    setPhase('input')
    setStartText(''); setEndText('')
    setWaypointTexts([]); setWaypointPoints([])
    setAllCandidates([]); setSegSels([])
    setActiveSegIdx(0); setSegmentPlans([])
    setError(null)
    onClear()
    onFetchCandidates(null)
    onSelectPickup(null)
    onSelectDropoff(null)
  }

  // ── Phase 1 → 2: geocode all points, fetch candidates per segment ─────────
  async function handleFindStations() {
    setError(null)
    setLoading(true)
    try {
      const start = startPoint ?? await geocode(startText)
      setStartPoint(start)

      // Geocode waypoints sequentially (preserve order)
      const resolvedWps = []
      for (let i = 0; i < waypointTexts.length; i++) {
        const pt = waypointPoints[i] ?? await geocode(waypointTexts[i])
        resolvedWps.push(pt)
      }
      setWaypointPoints(resolvedWps)

      const end = endPoint ?? await geocode(endText)
      setEndPoint(end)

      const allPoints = [start, ...resolvedWps, end]
      const departureDt = new Date(departureTime).toISOString()

      // Fetch candidates for all segments in parallel
      const fetches = allPoints.slice(0, -1).map((from, i) => {
        const to = allPoints[i + 1]
        const params = new URLSearchParams({
          start_lat: from.lat, start_lng: from.lng,
          end_lat:   to.lat,   end_lng:   to.lng,
          departure_time: departureDt,
        })
        return fetch(`/api/plan/candidates?${params}`)
          .then(r => r.json().then(j => ({ ok: r.ok, data: j })))
      })
      const results = await Promise.all(fetches)

      const failed = results.find(r => !r.ok)
      if (failed) throw new Error(failed.data.error ?? 'Failed to fetch candidates')

      const newAllCandidates = results.map(r => r.data)
      setAllCandidates(newAllCandidates)
      setSegSels(newAllCandidates.map(() => ({ pickup: null, dropoff: null })))
      setActiveSegIdx(0)
      onFetchCandidates(newAllCandidates[0])
      onSelectPickup(null); onSelectDropoff(null)
      setPhase('select')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Phase 3 → 4: compute route for each segment ───────────────────────────
  async function handleGetDirections() {
    setError(null)
    setLoading(true)
    try {
      const allPoints = [startPoint, ...waypointPoints, endPoint]
      const fetches = segmentSelections.map((sel, i) => {
        const from = allPoints[i]
        const to   = allPoints[i + 1]
        const params = new URLSearchParams({
          pickup_id:  sel.pickup.station_id,
          dropoff_id: sel.dropoff.station_id,
          start_lat: from.lat, start_lng: from.lng,
          end_lat:   to.lat,   end_lng:   to.lng,
          preference,
        })
        return fetch(`/api/plan/route?${params}`)
          .then(r => r.json().then(j => ({ ok: r.ok, data: j })))
      })
      const results = await Promise.all(fetches)

      const failed = results.find(r => !r.ok)
      if (failed) throw new Error(failed.data.error ?? 'Failed to compute route')

      const plans = results.map(r => r.data)
      setSegmentPlans(plans)
      onPlanComputed(plans[0])   // send first leg to map for polyline
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

  // ── Computed helpers for render ───────────────────────────────────────────
  const allPoints = [startPoint, ...waypointPoints, endPoint]
  const numSegs   = allCandidates.length
  const allSegsSelected = segmentSelections.length > 0 &&
    segmentSelections.every(sel => sel.pickup && sel.dropoff)

  // Label letters: A, B, C, D...
  const endLabel = String.fromCharCode(66 + waypointTexts.length)

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

          {/* Waypoints */}
          {waypointTexts.map((text, i) => (
            <div key={i} style={{ marginTop: 8, display: 'flex', alignItems: 'flex-start', gap: 4 }}>
              <div style={{ flex: 1 }}>
                <AddressInput
                  label={String.fromCharCode(66 + i)}
                  dotColor="#f39c12"
                  placeholder={`Stop ${i + 1} — address`}
                  value={waypointPoints[i] ? waypointPoints[i].label : text}
                  onChange={v => updateWaypointText(i, v)}
                  onSelectStation={pt => setWaypointPoint(i, pt)}
                  stations={stations}
                />
              </div>
              <button onClick={() => removeWaypoint(i)} style={s.removeWpBtn} title="Remove stop">×</button>
            </div>
          ))}

          <div style={{ marginTop: 8 }}>
            <AddressInput
              label={endLabel} dotColor="#e74c3c"
              placeholder="Destination — station name or address"
              value={endPoint ? endPoint.label : endText}
              onChange={v => { setEndText(v); setEndPoint(null) }}
              onSelectStation={pt => { setEndPoint(pt); setEndText('') }}
              onFocus={() => setClickMode('end')}
              stations={stations}
            />
          </div>

          <button onClick={addWaypoint} style={s.addWpBtn}>+ Add stop</button>

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

      {/* ── Phase 2: Select stations (segment by segment) ── */}
      {phase === 'select' && currentCandidates && (
        <div style={s.body}>
          {/* Segment indicator dots (only if multi-stop) */}
          {numSegs > 1 && (
            <div style={s.segIndicator}>
              {allCandidates.map((_, i) => {
                const sel = segmentSelections[i]
                const done = sel?.pickup && sel?.dropoff
                return (
                  <button
                    key={i}
                    onClick={() => switchToSegment(i)}
                    style={{
                      ...s.segDot,
                      background: done ? '#16a085' : '#ddd',
                      border: i === activeSegIdx ? '2px solid #1a73e8' : '2px solid transparent',
                      color: done ? '#fff' : '#555',
                    }}
                  >
                    {i + 1}
                  </button>
                )
              })}
            </div>
          )}

          {/* Current segment label */}
          <div style={s.segLabel}>
            {numSegs > 1 ? `Leg ${activeSegIdx + 1} of ${numSegs}` : 'Select stations'}
            {allPoints[activeSegIdx] && allPoints[activeSegIdx + 1] && (
              <span style={s.segRoute}>
                {' '}{shortLabel(allPoints[activeSegIdx])} → {shortLabel(allPoints[activeSegIdx + 1])}
              </span>
            )}
          </div>

          {/* Pickup candidates */}
          <div style={s.sectionTitle}>
            Pickup station <span style={s.sectionSub}>(ML predicted · departure time)</span>
          </div>
          {currentCandidates.pickup_candidates.length === 0
            ? <div style={s.emptyMsg}>No stations with enough bikes nearby.</div>
            : currentCandidates.pickup_candidates.map(st => (
                <CandidateCard
                  key={st.station_id}
                  station={st} type="pickup"
                  selected={currentSel.pickup?.station_id === st.station_id}
                  onClick={() => handlePickupSelect(st)}
                />
              ))
          }

          <div style={{ height: 10 }} />

          {/* Dropoff candidates */}
          <div style={s.sectionTitle}>
            Dropoff station <span style={s.sectionSub}>(ML predicted · arrival time)</span>
          </div>
          {currentCandidates.dropoff_candidates.length === 0
            ? <div style={s.emptyMsg}>No stations nearby.</div>
            : currentCandidates.dropoff_candidates.map(st => (
                <CandidateCard
                  key={st.station_id}
                  station={st} type="dropoff"
                  selected={currentSel.dropoff?.station_id === st.station_id}
                  onClick={() => handleDropoffSelect(st)}
                />
              ))
          }

          {error && <div style={s.error}>{error}</div>}

          {/* Navigation */}
          <div style={s.btnRow}>
            <button
              onClick={() => {
                if (activeSegIdx === 0) { setPhase('input'); onFetchCandidates(null) }
                else switchToSegment(activeSegIdx - 1)
              }}
              style={s.secondaryBtn}
            >
              ← {activeSegIdx === 0 ? 'Back' : 'Prev leg'}
            </button>

            {activeSegIdx < numSegs - 1 ? (
              <button
                onClick={() => {
                  if (!currentSel.pickup || !currentSel.dropoff) {
                    setError('Select both stations for this leg.'); return
                  }
                  setError(null)
                  switchToSegment(activeSegIdx + 1)
                }}
                style={s.primaryBtn}
              >
                Next leg →
              </button>
            ) : (
              <button
                onClick={() => {
                  if (!allSegsSelected) {
                    const missing = segmentSelections
                      .map((sel, i) => {
                        if (!sel.pickup && !sel.dropoff) return `Leg ${i + 1}: pickup & dropoff`
                        if (!sel.pickup)  return `Leg ${i + 1}: pickup`
                        if (!sel.dropoff) return `Leg ${i + 1}: dropoff`
                        return null
                      })
                      .filter(Boolean)
                    setError(`Still missing: ${missing.join(' · ')}`)
                    return
                  }
                  setError(null)
                  setPhase('preference')
                }}
                style={s.primaryBtn}
              >
                Next →
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Phase 3: Preference ── */}
      {phase === 'preference' && (
        <div style={s.body}>
          <div style={s.summaryBox}>
            {segmentSelections.map((sel, i) => (
              <div key={i}>
                {segmentSelections.length > 1 && (
                  <div style={s.summaryLegHeader}>Leg {i + 1}</div>
                )}
                <div style={s.summaryRow}>
                  <span style={s.summaryLabel}>Pickup</span>
                  <span>{sel.pickup?.name}</span>
                </div>
                <div style={s.summaryRow}>
                  <span style={s.summaryLabel}>Dropoff</span>
                  <span>{sel.dropoff?.name}</span>
                </div>
              </div>
            ))}
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
            <button onClick={() => { setPhase('select'); switchToSegment(numSegs - 1) }} style={s.secondaryBtn}>← Back</button>
            <button onClick={handleGetDirections} disabled={loading} style={s.primaryBtn}>
              {loading ? 'Calculating…' : 'Get Directions'}
            </button>
          </div>
        </div>
      )}

      {/* ── Phase 4: Result ── */}
      {phase === 'result' && segmentPlans.length > 0 && (
        <div>
          <RouteResult plans={segmentPlans} />
          <div style={{ padding: '0 12px 12px' }}>
            <button onClick={() => setPhase('preference')} style={s.secondaryBtn}>← Change preference</button>
          </div>
        </div>
      )}
    </div>
  )
}

// Shorten a geocoded label to just the first part
function shortLabel(pt) {
  if (!pt) return ''
  return (pt.label ?? '').split(',')[0] || pt.label
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
  addWpBtn: {
    marginTop: 8, background: 'none', border: 'none',
    color: '#16a085', cursor: 'pointer',
    fontSize: '0.82rem', fontWeight: 600, padding: '2px 0',
    textDecoration: 'underline',
  },
  removeWpBtn: {
    background: 'none', border: 'none',
    color: '#aaa', cursor: 'pointer',
    fontSize: '1.1rem', lineHeight: 1,
    padding: '6px 4px', marginTop: 2,
    flexShrink: 0,
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
  segIndicator: {
    display: 'flex', gap: 6, marginBottom: 10, alignItems: 'center',
  },
  segDot: {
    width: 26, height: 26, borderRadius: 13,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: '0.78rem', fontWeight: 700, cursor: 'pointer',
    border: '2px solid transparent', transition: 'all 0.15s',
    padding: 0,
  },
  segLabel: { fontSize: '0.82rem', fontWeight: 700, color: '#333', marginBottom: 8 },
  segRoute: { fontWeight: 400, color: '#888', fontSize: '0.75rem' },
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
  summaryLegHeader: {
    fontSize: '0.75rem', fontWeight: 700, color: '#16a085',
    textTransform: 'uppercase', letterSpacing: '0.03em',
    marginTop: 8, marginBottom: 4,
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
  legHeader: {
    fontSize: '0.75rem', fontWeight: 700, color: '#16a085',
    textTransform: 'uppercase', letterSpacing: '0.03em',
    marginBottom: 8, marginTop: 4,
  },
  legDivider: {
    borderTop: '2px dashed #e0e0e0', margin: '12px 0',
  },
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
