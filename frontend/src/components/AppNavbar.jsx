export default function AppNavbar({ currentPage, onNavigate, user, onLogout }) {
  return (
    <header style={s.navbar}>
      <div style={s.left}>
        <span style={s.logo}>🚲 Dublin Bikes Hub</span>
        <nav style={s.nav}>
          {['map', 'account'].map(page => (
            <button
              key={page}
              style={{ ...s.navLink, ...(currentPage === page ? s.navLinkActive : {}) }}
              onClick={() => onNavigate(page)}
            >
              {page === 'map' ? 'Main Map' : 'Login / Account'}
            </button>
          ))}
        </nav>
      </div>
      <div style={s.right}>
        {user ? (
          <>
            <span style={s.userName}>👤 {user.name}</span>
            <button style={s.outlineBtn} onClick={onLogout}>Sign out</button>
          </>
        ) : (
          <button style={s.primaryBtn} onClick={() => onNavigate('account')}>Get a Bike</button>
        )}
      </div>
    </header>
  )
}

const s = {
  navbar: {
    height: 56, background: '#fff', borderBottom: '1px solid #eee',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 24px', flexShrink: 0, zIndex: 1000,
    boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
  },
  left: { display: 'flex', alignItems: 'center', gap: 32 },
  logo: { fontWeight: 700, fontSize: '1.1rem', color: '#111', whiteSpace: 'nowrap' },
  nav: { display: 'flex', gap: 4 },
  navLink: {
    background: 'none', border: 'none', cursor: 'pointer',
    padding: '6px 14px', borderRadius: 6, fontSize: '0.9rem',
    color: '#555', fontWeight: 500,
  },
  navLinkActive: { background: '#f0f0f0', color: '#111', fontWeight: 600 },
  right: { display: 'flex', alignItems: 'center', gap: 12 },
  userName: { fontSize: '0.9rem', color: '#333', fontWeight: 500 },
  primaryBtn: {
    background: '#111', color: '#fff', border: 'none',
    padding: '8px 18px', borderRadius: 20, cursor: 'pointer',
    fontSize: '0.9rem', fontWeight: 600,
  },
  outlineBtn: {
    background: 'none', color: '#111', border: '1px solid #ccc',
    padding: '6px 14px', borderRadius: 20, cursor: 'pointer',
    fontSize: '0.9rem',
  },
}
