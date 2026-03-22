export default function Navbar({ weather, onRefresh }) {
  const w = weather?.data

  return (
    <header style={styles.navbar}>
      <span style={styles.brand}>🚲 Dublin Bikes</span>

      <div style={styles.weatherPanel}>
        {w ? (
          <>
            {w.weather?.[0]?.icon && (
              <img
                src={`https://openweathermap.org/img/wn/${w.weather[0].icon}.png`}
                alt={w.weather[0].description ?? 'weather icon'}
                style={{ width: 32, height: 32 }}
              />
            )}
            <span title="Temperature">🌡️ {Math.round(w.main?.temp)}°C</span>
            <span title="Feels like">Feels {Math.round(w.main?.feels_like)}°C</span>
            <span title="Humidity">💧 {w.main?.humidity}%</span>
            <span title="Wind speed">💨 {w.wind?.speed} m/s</span>
            {w.weather?.[0]?.description && (
              <span style={{ opacity: 0.85, textTransform: 'capitalize' }}>
                {w.weather[0].description}
              </span>
            )}
          </>
        ) : (
          <span>Loading weather…</span>
        )}
      </div>

      <button onClick={onRefresh} style={styles.btn} title="Refresh all data">
        ↻ Refresh
      </button>
    </header>
  )
}

const styles = {
  navbar: {
    height: 56,
    background: '#1a73e8',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    padding: '0 16px',
    gap: 16,
    flexShrink: 0,
    boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
    zIndex: 1000,
  },
  brand: {
    fontSize: '1.2rem',
    fontWeight: 700,
    whiteSpace: 'nowrap',
  },
  weatherPanel: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    fontSize: '0.9rem',
    flexWrap: 'wrap',
    overflow: 'hidden',
  },
  btn: {
    background: 'rgba(255,255,255,0.2)',
    border: '1px solid rgba(255,255,255,0.5)',
    color: '#fff',
    padding: '6px 14px',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: '0.9rem',
    whiteSpace: 'nowrap',
    transition: 'background 0.2s',
  },
}
