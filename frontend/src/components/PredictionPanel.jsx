import { useState, useRef, useEffect } from 'react'

export default function PredictionPanel({ stationId, stationName, onClose }) {
  const now = new Date()
  const localDate = now.toISOString().slice(0, 10)
  const localTime = now.toTimeString().slice(0, 5)

  const [date, setDate] = useState(localDate)
  const [time, setTime] = useState(localTime)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Drag state
  const panelRef = useRef(null)
  const dragOffset = useRef(null)
  const [pos, setPos] = useState({ x: window.innerWidth / 2 - 160, y: 80 })

  function onMouseDown(e) {
    dragOffset.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  function onMouseMove(e) {
    if (!dragOffset.current) return
    setPos({ x: e.clientX - dragOffset.current.x, y: e.clientY - dragOffset.current.y })
  }

  function onMouseUp() {
    dragOffset.current = null
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  useEffect(() => () => {
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }, [])

  async function handlePredict() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const dt = `${date}T${time}:00`
      const res = await fetch(`/api/predict?station_id=${stationId}&datetime=${dt}`)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error ?? 'Prediction failed')
      setResult(json)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      ref={panelRef}
      style={{ ...styles.panel, left: pos.x, top: pos.y }}
    >
      {/* Title bar — drag handle */}
      <div style={styles.titleBar} onMouseDown={onMouseDown}>
        <span style={styles.title}>🔮 Predict — {stationName}</span>
        <button onClick={onClose} style={styles.closeBtn}>✕</button>
      </div>

      {/* Inputs */}
      <div style={styles.body}>
        <label style={styles.label}>Date</label>
        <input
          type="date"
          value={date}
          onChange={e => setDate(e.target.value)}
          style={styles.input}
        />

        <label style={styles.label}>Time</label>
        <input
          type="time"
          value={time}
          onChange={e => setTime(e.target.value)}
          style={styles.input}
        />

        <button
          onClick={handlePredict}
          disabled={loading}
          style={styles.predictBtn}
        >
          {loading ? 'Predicting…' : 'Predict'}
        </button>

        {/* Result */}
        {error && <div style={styles.error}>{error}</div>}
        {result && (
          <div style={styles.result}>
            <div style={styles.resultNumber}>{result.predicted_bikes}</div>
            <div style={styles.resultLabel}>predicted bikes available</div>
            <div style={styles.resultMeta}>
              🌡️ {result.weather.temp}°C · 💧 {result.weather.humidity}%
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const styles = {
  panel: {
    position: 'fixed',
    width: 300,
    background: '#fff',
    borderRadius: 10,
    boxShadow: '0 8px 32px rgba(0,0,0,0.22)',
    zIndex: 9999,
    userSelect: 'none',
  },
  titleBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: '#1a73e8',
    color: '#fff',
    padding: '10px 14px',
    borderRadius: '10px 10px 0 0',
    cursor: 'grab',
  },
  title: {
    fontWeight: 700,
    fontSize: '0.88rem',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: 220,
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#fff',
    fontSize: '1rem',
    cursor: 'pointer',
    lineHeight: 1,
  },
  body: {
    padding: '14px 16px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  label: {
    fontSize: '0.78rem',
    color: '#555',
    marginBottom: -4,
  },
  input: {
    padding: '6px 8px',
    fontSize: '0.88rem',
    border: '1px solid #ddd',
    borderRadius: 5,
    outline: 'none',
  },
  predictBtn: {
    marginTop: 4,
    padding: '8px 0',
    background: '#1a73e8',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    fontSize: '0.9rem',
    fontWeight: 600,
    cursor: 'pointer',
  },
  error: {
    color: '#e74c3c',
    fontSize: '0.82rem',
    marginTop: 4,
  },
  result: {
    marginTop: 6,
    textAlign: 'center',
    padding: '12px 0 4px',
    borderTop: '1px solid #eee',
  },
  resultNumber: {
    fontSize: '2.4rem',
    fontWeight: 700,
    color: '#1a73e8',
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
    marginTop: 6,
  },
}
