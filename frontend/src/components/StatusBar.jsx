const LEGEND = [
  { color: '#2ecc71', label: 'Many bikes (> 5)' },
  { color: '#f39c12', label: 'Few bikes (1–5)' },
  { color: '#e74c3c', label: 'No bikes' },
  { color: '#95a5a6', label: 'Closed' },
]

export default function StatusBar({ stationCount, onRefresh }) {
  return (
    <div style={styles.bar}>
      <span>
        {stationCount != null ? `${stationCount} stations loaded` : 'Loading stations…'}
      </span>

      <div style={styles.legend}>
        {LEGEND.map(({ color, label }) => (
          <span key={label} style={styles.legendItem}>
            <span style={{ ...styles.dot, background: color }} />
            {label}
          </span>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={onRefresh} style={styles.btn}>↻ Refresh</button>
      </div>
    </div>
  )
}

const styles = {
  bar: {
    height: 36,
    background: '#fff',
    borderTop: '1px solid #ddd',
    display: 'flex',
    alignItems: 'center',
    padding: '0 16px',
    justifyContent: 'space-between',
    fontSize: '0.8rem',
    color: '#555',
    flexShrink: 0,
  },
  legend: {
    display: 'flex',
    gap: 16,
  },
  legendItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 5,
  },
  dot: {
    display: 'inline-block',
    width: 12,
    height: 12,
    borderRadius: '50%',
    flexShrink: 0,
  },
  btn: {
    background: 'none', border: '1px solid #ddd',
    padding: '3px 10px', borderRadius: 4, cursor: 'pointer',
    fontSize: '0.78rem', color: '#555',
  },
}
