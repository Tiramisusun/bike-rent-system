const FEATURES = [
  {
    icon: '🗺️',
    title: 'Route Planning',
    steps: [
      'Enter your start location, destination, and departure time.',
      'The system finds nearby stations with more than 2 available bikes for pickup.',
      'Based on estimated travel time, it recommends drop-off stations near your destination with more than 2 free stands.',
    ],
  },
  {
    icon: '📊',
    title: 'Availability Prediction',
    steps: [
      'Select a station and a future time to check predicted availability.',
      'The model uses historical data combined with current weather conditions.',
      'See the forecasted number of available bikes and stands before you travel.',
    ],
  },
  {
    icon: '💳',
    title: 'Bike Rental & Billing',
    steps: [
      'Log in to your account and choose a pickup station on the map.',
      'Return the bike at any station when you\'re done.',
      'The first 30 minutes are free. Each additional 30 minutes costs €0.50. Your full trip summary is shown on return.',
    ],
  },
]

export default function HowToPage() {
  return (
    <div style={s.page}>
      <h1 style={s.heading}>How It Works</h1>
      <p style={s.sub}>Everything you need to know to get started with Dublin Bikes Hub.</p>
      <div style={s.grid}>
        {FEATURES.map(({ icon, title, steps }) => (
          <div key={title} style={s.card}>
            <div style={s.icon}>{icon}</div>
            <h2 style={s.cardTitle}>{title}</h2>
            <ol style={s.list}>
              {steps.map((step, i) => (
                <li key={i} style={s.item}>{step}</li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  )
}

const s = {
  page: {
    flex: 1,
    background: '#f5f5f5',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '48px 24px',
    overflowY: 'auto',
  },
  heading: {
    fontSize: '2rem',
    fontWeight: 700,
    color: '#111',
    margin: 0,
  },
  sub: {
    fontSize: '1rem',
    color: '#666',
    marginTop: 10,
    marginBottom: 40,
  },
  grid: {
    display: 'flex',
    gap: 24,
    width: '100%',
    maxWidth: 1000,
  },
  card: {
    flex: 1,
    background: '#fff',
    borderRadius: 12,
    boxShadow: '0 2px 12px rgba(0,0,0,0.07)',
    padding: '32px 28px',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  icon: {
    fontSize: '2.4rem',
  },
  cardTitle: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#111',
    margin: 0,
  },
  list: {
    margin: 0,
    paddingLeft: 18,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  item: {
    fontSize: '0.88rem',
    color: '#444',
    lineHeight: 1.6,
  },
}
