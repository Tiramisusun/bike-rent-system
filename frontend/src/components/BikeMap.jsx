import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, CircleMarker, Popup, Polyline, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'
import RoutePlanner from './RoutePlanner'
import StationHistoryChart from './StationHistoryChart'
import PredictionWidget from './PredictionWidget'
import WeatherForecastWidget from './WeatherForecastWidget'

function bikeIcon(color) {
  return L.divIcon({
    className: '',
    html: `
      <div style="
        background:${color};
        border:2px solid #fff;
        border-radius:50% 50% 50% 0;
        transform:rotate(-45deg);
        width:32px;height:32px;
        box-shadow:0 2px 6px rgba(0,0,0,0.3);
        display:flex;align-items:center;justify-content:center;
      ">
        <span style="transform:rotate(45deg);font-size:15px;line-height:1;">🚲</span>
      </div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 32],
    popupAnchor: [0, -34],
  })
}

const DUBLIN_CENTER = [53.3498, -6.2603]

/** Renders the three polylines + station halos for one bike segment. */
function BikeSegmentOverlay({ seg }) {
  if (!seg.polylines) return null
  return (
    <>
      <CircleMarker
        center={[seg.pickup_station.position.lat, seg.pickup_station.position.lng]}
        radius={15}
        pathOptions={{ fillColor: '#1a73e8', color: '#1a73e8', weight: 3, fillOpacity: 0.15 }}
      />
      <CircleMarker
        center={[seg.dropoff_station.position.lat, seg.dropoff_station.position.lng]}
        radius={15}
        pathOptions={{ fillColor: '#e74c3c', color: '#e74c3c', weight: 3, fillOpacity: 0.15 }}
      />
      <Polyline positions={seg.polylines.walk_to_pickup}
        pathOptions={{ color: '#1a73e8', weight: 3, dashArray: '6 9', opacity: 0.85 }} />
      <Polyline positions={seg.polylines.bike}
        pathOptions={{ color: '#2ecc71', weight: 4, opacity: 0.9 }} />
      <Polyline positions={seg.polylines.walk_to_destination}
        pathOptions={{ color: '#e74c3c', weight: 3, dashArray: '6 9', opacity: 0.85 }} />
    </>
  )
}

function markerColor(availBikes, status) {
  if (status !== 'OPEN') return '#95a5a6'
  if (availBikes === 0)  return '#e74c3c'
  if (availBikes <= 5)   return '#f39c12'
  return '#2ecc71'
}

function fmtDist(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
}

function fmtTime(ms) {
  if (!ms) return '—'
  return new Date(ms).toLocaleTimeString()
}

/** Flies the map to fit both points when they change. */
function FlyToBounds({ startPoint, endPoint }) {
  const map = useMap()
  useEffect(() => {
    if (startPoint && endPoint) {
      const bounds = L.latLngBounds(
        [startPoint.lat, startPoint.lng],
        [endPoint.lat, endPoint.lng]
      )
      map.flyToBounds(bounds, { padding: [60, 60], maxZoom: 16, duration: 1 })
    } else if (startPoint) {
      map.flyTo([startPoint.lat, startPoint.lng], 15, { duration: 0.8 })
    } else if (endPoint) {
      map.flyTo([endPoint.lat, endPoint.lng], 15, { duration: 0.8 })
    }
  }, [startPoint, endPoint])
  return null
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

export default function BikeMap({ refreshKey, onWeatherLoaded, onStationsLoaded, user, onRentalChange }) {
  const [candidates, setCandidates]         = useState(null)  // { pickup_candidates, dropoff_candidates }
  const [selectedPickup, setSelectedPickup] = useState(null)
  const [selectedDropoff, setSelectedDropoff] = useState(null)
  const [stations, setStations]     = useState([])
  const [error, setError]           = useState(null)
  const [plan, setPlan]             = useState(null)
  const [startPoint, setStartPoint] = useState(null)
  const [endPoint, setEndPoint]     = useState(null)
  const [clickMode, setClickMode]   = useState(null)   // 'start' | 'end' | null
  const [historyStation, setHistoryStation] = useState(null)  // { id, name }
  const [rentalMsg, setRentalMsg] = useState(null)
  const [activeRental, setActiveRental] = useState(null)

  // Load active rental when user logs in
  useEffect(() => {
    if (user) {
      fetch('/api/rental/active', { headers: { Authorization: `Bearer ${user.token}` } })
        .then(r => r.json()).then(d => setActiveRental(d.active))
    } else {
      setActiveRental(null)
    }
  }, [user])

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

  async function handleRent(stationId) {
    if (!user) return setRentalMsg('Please log in to rent a bike.')
    const res = await fetch('/api/rental/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${user.token}` },
      body: JSON.stringify({ station_id: stationId }),
    })
    const data = await res.json()
    if (!res.ok) setRentalMsg(data.error)
    else { setRentalMsg(`✅ Rental started at ${data.pickup_station}`); setActiveRental({ rental_id: data.rental_id, pickup_station: data.pickup_station, start_time: data.start_time }); onRentalChange?.() }
  }

  async function handleReturn(stationId) {
    if (!user || !activeRental) return
    const res = await fetch('/api/rental/end', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${user.token}` },
      body: JSON.stringify({ station_id: stationId }),
    })
    const data = await res.json()
    if (!res.ok) setRentalMsg(data.error)
    else { setRentalMsg(`✅ Returned at ${data.dropoff_station} · ${data.duration_minutes} min · €${data.cost_eur}`); setActiveRental(null); onRentalChange?.() }
  }

  function handleClear() {
    setPlan(null)
    setStartPoint(null)
    setEndPoint(null)
    setClickMode(null)
    setCandidates(null)
    setSelectedPickup(null)
    setSelectedDropoff(null)
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
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/">CARTO</a>'
          maxZoom={19}
        />

        <MapClickHandler clickMode={clickMode} onMapClick={handleMapClick} />
        <FlyToBounds startPoint={startPoint} endPoint={endPoint} />

        {/* ── Station markers ── */}
        {stations.map(station => {
          const avail  = station.available_bikes ?? 0
          const stands = station.available_bike_stands ?? 0
          const total  = avail + stands
          const pct    = total > 0 ? Math.round((avail / total) * 100) : 0
          const color  = markerColor(avail, station.status ?? 'OPEN')

          return (
            <Marker
              key={station.number}
              position={[station.position.lat, station.position.lng]}
              icon={bikeIcon(color)}
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
                <button
                  style={styles.historyBtn}
                  onClick={() => setHistoryStation({ id: station.number, name: station.name })}
                >
                  📈 View History
                </button>
                {user && (
                  activeRental
                    ? <button style={styles.returnBtn} onClick={() => handleReturn(station.number)}>🔄 Return Bike Here</button>
                    : <button style={styles.rentBtn} onClick={() => handleRent(station.number)}>🚲 Rent Bike</button>
                )}
              </Popup>
            </Marker>
          )
        })}

        {/* ── Route visualisation ── */}
        {startPoint && (
          <CircleMarker
            center={[startPoint.lat, startPoint.lng]}
            radius={10}
            pathOptions={{ fillColor: '#1a73e8', color: '#fff', weight: 2.5, fillOpacity: 1 }}
          >
            <Popup><strong>Start:</strong> {startPoint.label}</Popup>
          </CircleMarker>
        )}
        {endPoint && (
          <CircleMarker
            center={[endPoint.lat, endPoint.lng]}
            radius={10}
            pathOptions={{ fillColor: '#e74c3c', color: '#fff', weight: 2.5, fillOpacity: 1 }}
          >
            <Popup><strong>Destination:</strong> {endPoint.label}</Popup>
          </CircleMarker>
        )}

        {plan?.mode === 'bike' && <BikeSegmentOverlay seg={plan} />}

        {/* ── Candidate pickup markers (green shades) ── */}
        {candidates?.pickup_candidates?.map(st => {
          const maxVal = 20
          const alpha  = 0.3 + Math.min(st.predicted_bikes / maxVal, 1) * 0.7
          const color  = `rgba(39,174,96,${alpha})`
          const isSelected = selectedPickup?.station_id === st.station_id
          return (
            <CircleMarker
              key={`pickup-${st.station_id}`}
              center={[st.lat, st.lng]}
              radius={isSelected ? 16 : 12}
              pathOptions={{ fillColor: color, color: isSelected ? '#1a73e8' : '#fff', weight: isSelected ? 3 : 2, fillOpacity: 0.9 }}
              eventHandlers={{ click: () => setSelectedPickup(st) }}
            >
              <Popup>
                <strong>{st.name}</strong><br />
                🚲 {st.predicted_bikes} bikes predicted<br />
                {fmtDist(st.distance_m)} from start
              </Popup>
            </CircleMarker>
          )
        })}

        {/* ── Candidate dropoff markers (red shades) ── */}
        {candidates?.dropoff_candidates?.map(st => {
          const maxVal = 20
          const alpha  = 0.3 + Math.min(st.predicted_docks / maxVal, 1) * 0.7
          const color  = `rgba(231,76,60,${alpha})`
          const isSelected = selectedDropoff?.station_id === st.station_id
          return (
            <CircleMarker
              key={`dropoff-${st.station_id}`}
              center={[st.lat, st.lng]}
              radius={isSelected ? 16 : 12}
              pathOptions={{ fillColor: color, color: isSelected ? '#1a73e8' : '#fff', weight: isSelected ? 3 : 2, fillOpacity: 0.9 }}
              eventHandlers={{ click: () => setSelectedDropoff(st) }}
            >
              <Popup>
                <strong>{st.name}</strong><br />
                🅿️ {st.predicted_docks} docks predicted<br />
                {fmtDist(st.distance_m)} from destination
              </Popup>
            </CircleMarker>
          )
        })}

        {error && (
          <div style={styles.errorBanner}>⚠️ {error}</div>
        )}
      </MapContainer>

      {/* ── Rental message banner ── */}
      {rentalMsg && (
        <div style={styles.rentalBanner}>
          {rentalMsg}
          <button onClick={() => setRentalMsg(null)} style={styles.bannerClose}>✕</button>
        </div>
      )}

      {/* ── Active rental indicator ── */}
      {activeRental && (
        <div style={styles.activeBanner}>
          🚲 Active rental: <strong>{activeRental.pickup_station}</strong> · Click a station to return
        </div>
      )}

      {/* ── Station history chart modal ── */}
      {historyStation && (
        <StationHistoryChart
          stationId={historyStation.id}
          stationName={historyStation.name}
          onClose={() => setHistoryStation(null)}
        />
      )}

      {/* ── Left sidebar: Route Plan / Predict / Forecast ── */}
      <div style={styles.leftSidebar}>
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
          stations={stations}
          candidates={candidates}
          onFetchCandidates={setCandidates}
          selectedPickup={selectedPickup}
          selectedDropoff={selectedDropoff}
          onSelectPickup={setSelectedPickup}
          onSelectDropoff={setSelectedDropoff}
        />
        <PredictionWidget stations={stations} />
        <WeatherForecastWidget />
      </div>
    </div>
  )
}

const styles = {
  leftSidebar: {
    position: 'absolute',
    top: 12,
    left: 12,
    zIndex: 1000,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    maxHeight: 'calc(100% - 24px)',
    overflowY: 'auto',
    pointerEvents: 'none',  // 让地图点击穿透侧边栏空隙
  },
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
  historyBtn: {
    marginTop: 10,
    width: '100%',
    padding: '6px 0',
    background: '#1a73e8',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: '0.82rem',
    fontWeight: 600,
  },
  rentBtn: {
    marginTop: 6,
    width: '100%',
    padding: '6px 0',
    background: '#2d7a3a',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: '0.82rem',
    fontWeight: 600,
  },
  returnBtn: {
    marginTop: 6,
    width: '100%',
    padding: '6px 0',
    background: '#e67e22',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: '0.82rem',
    fontWeight: 600,
  },
  rentalBanner: {
    position: 'absolute',
    top: 12, left: '50%',
    transform: 'translateX(-50%)',
    background: '#111',
    color: '#fff',
    padding: '8px 20px',
    borderRadius: 6,
    zIndex: 9999,
    fontSize: '0.9rem',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },
  bannerClose: {
    background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: '1rem',
  },
  activeBanner: {
    position: 'absolute',
    bottom: 12, left: '50%',
    transform: 'translateX(-50%)',
    background: '#2d7a3a',
    color: '#fff',
    padding: '8px 20px',
    borderRadius: 6,
    zIndex: 9999,
    fontSize: '0.85rem',
    whiteSpace: 'nowrap',
  },
}
