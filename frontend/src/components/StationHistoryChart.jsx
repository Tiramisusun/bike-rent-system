import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'

export default function StationHistoryChart({ stationId, stationName, onClose }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`/api/db/stations/${stationId}/history`)
      .then(r => r.json())
      .then(json => {
        const formatted = (json.data ?? []).map(d => {
          const dt = new Date(d.update_time)
          const label = `${(dt.getMonth() + 1).toString().padStart(2,'0')}/${dt.getDate().toString().padStart(2,'0')} ` +
            `${dt.getHours().toString().padStart(2,'0')}:${dt.getMinutes().toString().padStart(2,'0')}`
          return {
            time: label,
            'Available Bikes': d.avail_bikes,
            'Free Stands': d.avail_bike_stands,
          }
        })
        setData(formatted)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [stationId])

  return (
    <div style={styles.overlay}>
      <div style={styles.modal}>
        <div style={styles.header}>
          <span style={styles.title}>{stationName} — History</span>
          <button onClick={onClose} style={styles.closeBtn}>✕</button>
        </div>

        {loading && <div style={styles.center}>Loading…</div>}
        {error && <div style={styles.center}>Error: {error}</div>}
        {!loading && !error && data.length === 0 && (
          <div style={styles.center}>No historical data available.</div>
        )}
        {!loading && !error && data.length > 0 && (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} interval={Math.floor(data.length / 8)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="Available Bikes" stroke="#2ecc71" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="Free Stands" stroke="#1a73e8" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.45)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
  modal: {
    background: '#fff',
    borderRadius: 10,
    padding: 24,
    width: 560,
    maxWidth: '95vw',
    boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    fontWeight: 700,
    fontSize: '1rem',
    color: '#1a73e8',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    fontSize: '1.1rem',
    cursor: 'pointer',
    color: '#666',
  },
  center: {
    textAlign: 'center',
    padding: 40,
    color: '#888',
  },
}
