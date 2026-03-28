import { useState, useEffect } from 'react'

export default function AccountPage({ user, onLogin, onLogout, rentalVersion }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ email: '', password: '', name: '' })
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState([])
  const [active, setActive] = useState(null)

  useEffect(() => {
    if (user) {
      fetch('/api/rental/history', {
        headers: { Authorization: `Bearer ${user.token}` }
      }).then(r => r.json()).then(d => setHistory(d.rentals ?? []))

      fetch('/api/rental/active', {
        headers: { Authorization: `Bearer ${user.token}` }
      }).then(r => r.json()).then(d => setActive(d.active))
    }
  }, [user, rentalVersion])

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    const url = mode === 'login' ? '/api/auth/login' : '/api/auth/register'
    const body = mode === 'login'
      ? { email: form.email, password: form.password }
      : { email: form.email, password: form.password, name: form.name }
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) setError(data.error || 'Something went wrong')
      else onLogin(data.token, data.name)
    } catch { setError('Network error') }
    finally { setLoading(false) }
  }

  const initials = user ? user.name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) : ''

  return (
    <div style={s.page}>
      <div style={s.card}>
        {/* Left: Login Form — only show when not logged in */}
        {!user && <div style={s.left}>
          <h2 style={s.title}>Sign in to your account</h2>
          <p style={s.subtitle}>Access saved stations, reservations, trip history and preferences securely.</p>

          <form onSubmit={handleSubmit} style={s.form}>
            {mode === 'register' && (
              <div style={s.field}>
                <label style={s.label}>Full name</label>
                <input style={s.input} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
              </div>
            )}
            <div style={s.field}>
              <label style={s.label}>Email address</label>
              <input style={s.input} type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required />
            </div>
            <div style={s.field}>
              <label style={s.label}>Password</label>
              <input style={s.input} type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required />
            </div>
            {error && <div style={s.error}>{error}</div>}
            <button type="submit" style={s.submitBtn} disabled={loading}>
              {loading ? 'Loading…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>

          <div style={s.switchRow}>
            {mode === 'login'
              ? <span>Don't have an account? <button style={s.link} onClick={() => { setMode('register'); setError(null) }}>Create account</button></span>
              : <span>Already have an account? <button style={s.link} onClick={() => { setMode('login'); setError(null) }}>Sign in</button></span>
            }
          </div>
        </div>}

        {/* Right: Account info */}
        <div style={{ ...s.right, ...(user ? { flex: 2 } : {}) }}>
          {user ? (
            <>
              {/* User info */}
              <div style={s.userRow}>
                <div style={s.avatar}>{initials}</div>
                <div>
                  <div style={s.userName}>{user.name}</div>
                  <div style={s.userEmail}>{user.email || ''}</div>
                </div>
                <button style={s.signOutBtn} onClick={onLogout}>Sign out</button>
              </div>

              {/* Active rental */}
              {active && (
                <div style={s.section}>
                  <div style={s.sectionTitle}>Active Rental</div>
                  <div style={s.rentalCard}>
                    <div style={s.rentalTitle}>🚲 {active.pickup_station}</div>
                    <div style={s.rentalMeta}>Started: {new Date(active.start_time).toLocaleString()}</div>
                  </div>
                </div>
              )}

              {/* Recent trips */}
              <div style={s.section}>
                <div style={s.sectionTitle}>Recent trips</div>
                {history.length === 0 && <div style={s.empty}>No trips yet.</div>}
                {history.slice(0, 5).map(r => (
                  <div key={r.rental_id} style={s.tripRow}>
                    <div>
                      <div style={s.tripRoute}>{r.pickup_station} → {r.dropoff_station || '—'}</div>
                      <div style={s.tripMeta}>{r.start_time ? new Date(r.start_time).toLocaleString() : ''}</div>
                    </div>
                    <div style={s.tripRight}>
                      {r.duration_minutes != null && <div>{r.duration_minutes} min</div>}
                      {r.cost_eur != null && <div style={s.cost}>€{r.cost_eur.toFixed(2)}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={s.placeholder}>
              <div style={{ fontSize: '2rem' }}>🔒</div>
              <div style={s.placeholderText}>Sign in to view your account, trip history and active rentals.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const s = {
  page: { flex: 1, background: '#f5f5f5', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '40px 20px', overflowY: 'auto' },
  card: { background: '#fff', borderRadius: 12, boxShadow: '0 2px 16px rgba(0,0,0,0.08)', display: 'flex', width: '100%', maxWidth: 900, minHeight: 500 },
  left: { flex: 1, padding: '40px 36px', borderRight: '1px solid #eee' },
  right: { flex: 1, padding: '40px 36px', overflowY: 'auto' },
  title: { fontSize: '1.5rem', fontWeight: 700, color: '#111', marginBottom: 8 },
  subtitle: { fontSize: '0.85rem', color: '#666', marginBottom: 28 },
  form: { display: 'flex', flexDirection: 'column', gap: 16 },
  field: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: { fontSize: '0.85rem', fontWeight: 500, color: '#333' },
  input: { padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: '0.95rem', outline: 'none' },
  error: { color: '#e74c3c', fontSize: '0.85rem' },
  submitBtn: { padding: '12px', background: '#111', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: '0.95rem', fontWeight: 600, marginTop: 4 },
  switchRow: { marginTop: 20, fontSize: '0.85rem', color: '#555', textAlign: 'center' },
  link: { background: 'none', border: 'none', color: '#111', cursor: 'pointer', fontWeight: 600, textDecoration: 'underline' },
  userRow: { display: 'flex', alignItems: 'center', gap: 14, marginBottom: 28 },
  avatar: { width: 44, height: 44, background: '#111', color: '#fff', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '1rem', flexShrink: 0 },
  userName: { fontWeight: 600, fontSize: '1rem', color: '#111' },
  userEmail: { fontSize: '0.8rem', color: '#888' },
  signOutBtn: { marginLeft: 'auto', background: 'none', border: '1px solid #ccc', padding: '6px 14px', borderRadius: 20, cursor: 'pointer', fontSize: '0.85rem' },
  section: { marginBottom: 24 },
  sectionTitle: { fontWeight: 700, fontSize: '0.95rem', color: '#111', marginBottom: 12 },
  rentalCard: { background: '#f5f5f5', borderRadius: 8, padding: '12px 16px' },
  rentalTitle: { fontWeight: 600, fontSize: '0.95rem', color: '#111' },
  rentalMeta: { fontSize: '0.8rem', color: '#666', marginTop: 4 },
  tripRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid #f0f0f0' },
  tripRoute: { fontWeight: 500, fontSize: '0.9rem', color: '#111' },
  tripMeta: { fontSize: '0.78rem', color: '#888', marginTop: 2 },
  tripRight: { textAlign: 'right', fontSize: '0.85rem', color: '#555' },
  cost: { color: '#2d7a3a', fontWeight: 600 },
  empty: { color: '#aaa', fontSize: '0.85rem' },
  placeholder: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 16, color: '#aaa', textAlign: 'center' },
  placeholderText: { fontSize: '0.9rem', maxWidth: 260 },
}
