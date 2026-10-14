import { useState } from 'react'

const EXAMPLES = [
  'Which station has spent the most minutes empty?',
  'During peak hours, which station spent the most minutes empty?',
  'How many stations are there in each zone?',
  'Compare the average number of available bikes in hours with precipitation versus dry hours.',
]

export default function AskPage() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showSql, setShowSql] = useState(false)

  async function ask(q) {
    const text = (q ?? question).trim()
    if (!text) return
    setQuestion(text)
    setLoading(true)
    setError(null)
    setResult(null)
    setShowSql(false)
    try {
      const res = await fetch('/api/agent/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      })
      const body = await res.json().catch(() => ({}))
      if (res.status === 429) throw new Error('Too many questions — please wait a moment and try again.')
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`)
      setResult(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        <h2 style={s.title}>Ask the data</h2>
        <p style={s.subtitle}>
          Questions in plain English are turned into a read-only SQL query over the station data warehouse.
        </p>

        <form style={s.form} onSubmit={e => { e.preventDefault(); ask() }}>
          <input
            style={s.input}
            value={question}
            maxLength={300}
            placeholder="e.g. Which stations were empty for more than a quarter of the time?"
            onChange={e => setQuestion(e.target.value)}
          />
          <button style={s.askBtn} type="submit" disabled={loading || !question.trim()}>
            {loading ? 'Thinking…' : 'Ask'}
          </button>
        </form>

        <div style={s.examples}>
          {EXAMPLES.map(ex => (
            <button key={ex} style={s.example} onClick={() => ask(ex)} disabled={loading}>{ex}</button>
          ))}
        </div>

        {error && <div style={s.error}>{error}</div>}

        {result && (
          <div style={s.result}>
            <p style={s.answer}>{result.answer}</p>

            {result.sql && (
              <>
                <button style={s.linkBtn} onClick={() => setShowSql(v => !v)}>
                  {showSql ? 'Hide' : 'Show'} SQL · {result.row_count} row{result.row_count === 1 ? '' : 's'} · {result.latency_s}s
                </button>
                {showSql && <pre style={s.sql}>{result.sql}</pre>}
              </>
            )}

            {result.rows?.length > 0 && (
              <div style={s.tableWrap}>
                <table style={s.table}>
                  <thead>
                    <tr>{result.columns.map(c => <th key={c} style={s.th}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, i) => (
                      <tr key={i}>{row.map((v, j) => <td key={j} style={s.td}>{formatCell(v)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
                {result.row_count > result.rows.length && (
                  <p style={s.note}>Showing {result.rows.length} of {result.row_count} rows.</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function formatCell(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(2)
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  return String(v)
}

const s = {
  page: { flex: 1, overflowY: 'auto', background: '#f5f6f8', padding: '32px 16px' },
  card: {
    maxWidth: 860, margin: '0 auto', background: '#fff', borderRadius: 10, padding: 28,
    boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  },
  title: { fontSize: '1.3rem', marginBottom: 6 },
  subtitle: { color: '#666', fontSize: '0.9rem', marginBottom: 20 },
  form: { display: 'flex', gap: 8 },
  input: {
    flex: 1, padding: '10px 12px', fontSize: '0.95rem', border: '1px solid #ccc', borderRadius: 6,
  },
  askBtn: {
    padding: '10px 20px', background: '#1a73e8', color: '#fff', border: 'none', borderRadius: 6,
    cursor: 'pointer', fontWeight: 600,
  },
  examples: { display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  example: {
    background: '#f0f4ff', color: '#1a73e8', border: '1px solid #d6e2ff', borderRadius: 16,
    padding: '4px 12px', fontSize: '0.8rem', cursor: 'pointer',
  },
  error: { marginTop: 20, padding: 12, background: '#fdecea', color: '#a12622', borderRadius: 6 },
  result: { marginTop: 24 },
  answer: { fontSize: '1.05rem', lineHeight: 1.5, marginBottom: 10 },
  linkBtn: {
    background: 'none', border: 'none', color: '#1a73e8', cursor: 'pointer', padding: 0, fontSize: '0.85rem',
  },
  sql: {
    marginTop: 8, padding: 12, background: '#1e1e1e', color: '#d4d4d4', borderRadius: 6,
    fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  },
  tableWrap: { marginTop: 16, overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' },
  th: { textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid #eee', color: '#666', fontWeight: 500 },
  td: { padding: '6px 8px', borderBottom: '1px solid #f0f0f0' },
  note: { marginTop: 8, color: '#888', fontSize: '0.8rem' },
}
