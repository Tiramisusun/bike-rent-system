import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline, useMapEvents } from 'react-leaflet'
import RoutePlanner from './RoutePlanner'

const DUBLIN_CENTER = [53.3498, -6.2603]

function markerColor(availBikes, status) {
  if (status !== 'OPEN') return '#95a5a6'
  if (availBikes === 0)  return '#e74c3c'
  if (availBikes <= 5)   return '#f39c12'
  return '#2ecc71'
}

function fmtTime(ms) {
  if (!ms) return '—'
  return new Date(ms).toLocaleTimeString()
}

/** Intercepts Leaflet map clicks and forwards them when clickMode is active. */
function MapClickHandler({ clickMode, onMapClick }) {
  useMapEvents({
    click(e) {
      if (clickMode) onMapClick(e.latlng, clickMode)
    },
  })
  return null
}

export default function BikeMap({ refreshKey, onWeatherLoaded, onStationsLoaded }) {
  const [stations, setStations]     = useState([])
  const [error, setError]           = useState(null)
  const [plan, setPlan]             = useState(null)
  const [startPoint, setStartPoint] = useState(null)
  const [endPoint, setEndPoint]     = useState(null)
  const [clickMode, setClickMode]   = useState(null)   // 'start' | 'end' | null

  useEffect(() => {
    setError(null)
    Promise.all([
      fetch('/api/weather').then(r => r.json()),
      fetch('/api/bikes').then(r => r.json()),
    ])
      .then(([weatherJson, bikesJson]) => {
        onWeatherLoaded(weatherJson)
        const data = bikesJson.data ?? []
        setStations(data)
        onStationsLoaded(data.length)
      })
      .catch(err => setError(err.message))
  }, [refreshKey])

  function handleMapClick(latlng, mode) {
    const label = `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`
    const point  = { lat: latlng.lat, lng: latlng.lng, label }
    if (mode === 'start') setStartPoint(point)
    else setEndPoint(point)
    setClickMode(null)   // exit click mode after selection
  }

  function handleClear() {
    setPlan(null)
    setStartPoint(null)
    setEndPoint(null)
    setClickMode(null)
  }

  // Cursor style for the map wrapper when click mode is active
  const wrapperStyle = {
    position: 'relative',
    flex: 1,
    cursor: clickMode ? 'crosshair' : 'default',
  }

  return (
    <div style={wrapperStyle}>
      <MapContainer center={DUBLIN_CENTER} zoom={14} style={{ height: '100%' }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
        />

        <MapClickHandler clickMode={clickMode} onMapClick={handleMapClick} />

        {/* ── Station markers ── */}
        {stations.map(station => {
          const avail  = station.available_bikes ?? 0
          const stands = station.available_bike_stands ?? 0
          const total  = avail + stands
          const pct    = total > 0 ? Math.round((avail / total) * 100) : 0
          const color  = markerColor(avail, station.status ?? 'OPEN')

          return (
            <CircleMarker
              key={station.number}
              center={[station.position.lat, station.position.lng]}
              radius={9}
              pathOptions={{ fillColor: color, color: '#fff', weight: 2, fillOpacity: 0.9 }}
            >
              <Popup>
                <div style={styles.popupTitle}>{station.name}</div>
                <table style={styles.table}>
                  <tbody>
                    <tr><td>🚲 Available bikes</td><td style={styles.tdRight}>{avail}</td></tr>
                    <tr><td>🅿️ Free stands</td><td style={styles.tdRight}>{stands}</td></tr>
                    <tr><td>📦 Total capacity</td><td style={styles.tdRight}>{total}</td></tr>
                  </tbody>
                </table>
                <div style={styles.barBg}>
                  <div style={{ ...styles.barFill, width: `${pct}%`, background: color }} />
                </div>
                <div style={styles.popupFooter}>
                  Status: {station.status ?? '—'} · Updated: {fmtTime(station.last_update)}
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        {/* ── Route visualisation ── */}
        {startPoint && (
          <CircleMarker
            center={[startPoint.lat, startPoint.lng]}
            radius={10}
            pathOptions={{ fillColor: '#1a73e8', color: '#fff', weight: 2.5, fillOpacity: 1 }}
          />
        )}
        {endPoint && (
          <CircleMarker
            center={[endPoint.lat, endPoint.lng]}
            radius={10}
            pathOptions={{ fillColor: '#e74c3c', color: '#fff', weight: 2.5, fillOpacity: 1 }}
          />
        )}

        {plan?.mode === 'bike' && (
          <>
            <CircleMarker
              center={[plan.pickup_station.position.lat, plan.pickup_station.position.lng]}
              radius={15}
              pathOptions={{ fillColor: '#1a73e8', color: '#1a73e8', weight: 3, fillOpacity: 0.15 }}
            />
            <CircleMarker
              center={[plan.dropoff_station.position.lat, plan.dropoff_station.position.lng]}
              radius={15}
              pathOptions={{ fillColor: '#e74c3c', color: '#e74c3c', weight: 3, fillOpacity: 0.15 }}
            />
            {/* Walk start → pickup (dashed blue, follows foot route) */}
            <Polyline
              positions={plan.polylines.walk_to_pickup}
              pathOptions={{ color: '#1a73e8', weight: 3, dashArray: '6 9', opacity: 0.85 }}
            />
            {/* Bike pickup → dropoff (solid green, follows cycling route) */}
            <Polyline
              positions={plan.polylines.bike}
              pathOptions={{ color: '#2ecc71', weight: 4, opacity: 0.9 }}
            />
            {/* Walk dropoff → destination (dashed red, follows foot route) */}
            <Polyline
              positions={plan.polylines.walk_to_destination}
              pathOptions={{ color: '#e74c3c', weight: 3, dashArray: '6 9', opacity: 0.85 }}
            />
          </>
        )}

        {error && (
          <div style={styles.errorBanner}>⚠️ {error}</div>
        )}
      </MapContainer>

      {/* ── Directions panel (floating over map) ── */}
      <RoutePlanner
        startPoint={startPoint}
        endPoint={endPoint}
        setStartPoint={setStartPoint}
        setEndPoint={setEndPoint}
        clickMode={clickMode}
        setClickMode={setClickMode}
        plan={plan}
        onPlanComputed={setPlan}
        onClear={handleClear}
      />
    </div>
  )
}

const styles = {
  errorBanner: {
    position: 'absolute',
    top: 8, left: '50%',
    transform: 'translateX(-50%)',
    background: '#e74c3c',
    color: '#fff',
    padding: '6px 16px',
    borderRadius: 4,
    zIndex: 9999,
    fontSize: '0.85rem',
  },
  popupTitle: {
    fontWeight: 700,
    fontSize: '0.95rem',
    color: '#1a73e8',
    marginBottom: 8,
  },
  table: {
    fontSize: '0.85rem',
    borderCollapse: 'collapse',
    width: '100%',
  },
  tdRight: {
    textAlign: 'right',
    paddingLeft: 16,
    fontWeight: 600,
  },
  barBg: {
    marginTop: 8,
    height: 8,
    background: '#ecf0f1',
    borderRadius: 4,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 4,
    transition: 'width 0.3s',
  },
  popupFooter: {
    marginTop: 6,
    fontSize: '0.75rem',
    color: '#888',
  },
}
