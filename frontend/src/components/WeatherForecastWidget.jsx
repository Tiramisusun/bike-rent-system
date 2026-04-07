import { useEffect, useState } from 'react'

export default function WeatherForecastWidget() {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(null)
    fetch('/api/weather/forecast')
      .then(r => r.json())
      .then(json => { setData(json.data ?? []); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [open])

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={s.openBtn}>
        🌤️ Forecast
      </button>
    )
  }

  return (
    <div style={s.panel}>
      <div style={s.header}>
        <span style={s.title}>🌤️ 5-Day Forecast</span>
        <button onClick={() => setOpen(false)} style={s.closeBtn}>✕</button>
      </div>

      <div style={s.body}>
        {loading && <div style={s.center}>Loading…</div>}
        {error && <div style={s.center}>Error: {error}</div>}
        {!loading && !error && data.map(item => (
          <div key={item.dt} style={s.row}>
            <div style={s.rowTime}>{item.time}</div>
            <img
              src={`https://openweathermap.org/img/wn/${item.icon}.png`}
              alt={item.description}
              style={{ width: 32, height: 32, flexShrink: 0 }}
            />
            <div style={s.rowTemp}>{item.temp}°C</div>
            <div style={s.rowDesc}>{item.description}</div>
            <div style={s.rowMeta}>💧{item.humidity}% 💨{item.wind_speed}m/s</div>
          </div>
        ))}
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
    maxHeight: 'calc(100vh - 180px)',
    display: 'flex',
    flexDirection: 'column',
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
    textAlign: 'left',
  },
  header: {
    background: '#16a085',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 14px',
    borderRadius: '8px 8px 0 0',
    flexShrink: 0,
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
    overflowY: 'auto',
    padding: '8px 0',
  },
  center: {
    padding: '20px',
    textAlign: 'center',
    color: '#888',
    fontSize: '0.85rem',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '6px 14px',
    borderBottom: '1px solid #f5f5f5',
    fontSize: '0.82rem',
  },
  rowTime: {
    fontWeight: 600,
    color: '#16a085',
    minWidth: 52,
    fontSize: '0.78rem',
  },
  rowTemp: {
    fontWeight: 700,
    color: '#222',
    minWidth: 38,
  },
  rowDesc: {
    flex: 1,
    color: '#555',
    textTransform: 'capitalize',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  rowMeta: {
    color: '#999',
    fontSize: '0.72rem',
    whiteSpace: 'nowrap',
  },
}
