import { useEffect, useState } from 'react'

export default function WeatherForecast({ onClose }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/weather/forecast')
      .then(r => r.json())
      .then(json => {
        setData(json.data ?? [])
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return (
    <div style={styles.overlay}>
      <div style={styles.modal}>
        <div style={styles.header}>
          <span style={styles.title}>5-Day Weather Forecast — Dublin</span>
          <button onClick={onClose} style={styles.closeBtn}>✕</button>
        </div>

        {loading && <div style={styles.center}>Loading…</div>}
        {error && <div style={styles.center}>Error: {error}</div>}
        {!loading && !error && (
          <div style={styles.grid}>
            {data.map(item => (
              <div key={item.dt} style={styles.card}>
                <div style={styles.time}>{item.time}</div>
                <img
                  src={`https://openweathermap.org/img/wn/${item.icon}.png`}
                  alt={item.description}
                  style={{ width: 40, height: 40 }}
                />
                <div style={styles.temp}>{item.temp}°C</div>
                <div style={styles.desc}>{item.description}</div>
                <div style={styles.meta}>💧 {item.humidity}%</div>
                <div style={styles.meta}>💨 {item.wind_speed} m/s</div>
              </div>
            ))}
          </div>
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
    width: 700,
    maxWidth: '95vw',
    maxHeight: '80vh',
    overflowY: 'auto',
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
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
    gap: 10,
  },
  card: {
    background: '#f0f4ff',
    borderRadius: 8,
    padding: '10px 8px',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 2,
  },
  time: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: '#1a73e8',
  },
  temp: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#222',
  },
  desc: {
    fontSize: '0.7rem',
    color: '#555',
    textTransform: 'capitalize',
  },
  meta: {
    fontSize: '0.7rem',
    color: '#777',
  },
}
