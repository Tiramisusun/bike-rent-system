import { useEffect, useRef, useState } from 'react'

const EXAMPLES = [
  'Which station has spent the most minutes empty?',
  'How many stations are there in each zone?',
  'Compare the average number of available bikes in hours with precipitation versus dry hours.',
]

// The server keeps no conversation state: every question carries the recent turns.
// Must match MAX_HISTORY_TURNS / HISTORY_ROWS in src/agent/agent.py.
const HISTORY_TURNS = 6
const HISTORY_ROWS = 5

export default function AskPage() {
  const [turns, setTurns] = useState([])          // [{ question, answer, sql, columns, rows, ... }]
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, loading])

  async function ask(q) {
    const text = (q ?? question).trim()
    if (!text || loading) return
    setQuestion('')
    setLoading(true)
    setError(null)
    const history = turns.slice(-HISTORY_TURNS).map(t => ({
      question: t.question,
      answer: t.answer,
      sql: t.sql,
      columns: t.columns,
      rows: (t.rows ?? []).slice(0, HISTORY_ROWS),
    }))
    try {
      const res = await fetch('/api/agent/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, history }),
      })
      const body = await res.json().catch(() => ({}))
      if (res.status === 429) throw new Error('Too many questions — please wait a moment and try again.')
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`)
      setTurns(prev => [...prev, body])
    } catch (err) {
      setError(err.message)
      setQuestion(text)                            // let the user retry without retyping
    } finally {
      setLoading(false)
    }
  }

  function newConversation() {
    setTurns([])
    setError(null)
    setQuestion('')
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={s.header}>
          <div>
            <h2 style={s.title}>Ask the data</h2>
            <p style={s.subtitle}>
              Ask in plain English, then follow up — "and at peak hours?" refers to the previous answer.
            </p>
          </div>
          {turns.length > 0 && (
            <button style={s.newBtn} onClick={newConversation} disabled={loading}>New conversation</button>
          )}
        </div>

        <div style={s.thread}>
          {turns.length === 0 && !loading && (
            <div style={s.examples}>
              {EXAMPLES.map(ex => (
                <button key={ex} style={s.example} onClick={() => ask(ex)}>{ex}</button>
              ))}
            </div>
          )}

          {turns.map((t, i) => (
            <div key={i}>
              <div style={s.userRow}><div style={s.userBubble}>{t.question}</div></div>
              <AssistantMessage turn={t} />
            </div>
          ))}

          {loading && <div style={s.thinking}>Thinking…</div>}
          {error && <div style={s.error}>{error}</div>}
          <div ref={bottomRef} />
        </div>

        <form style={s.form} onSubmit={e => { e.preventDefault(); ask() }}>
          <input
            style={s.input}
            value={question}
            maxLength={300}
            placeholder={turns.length ? 'Ask a follow-up…' : 'e.g. Which stations were empty for more than a quarter of the time?'}
            onChange={e => setQuestion(e.target.value)}
            disabled={loading}
          />
          <button style={s.askBtn} type="submit" disabled={loading || !question.trim()}>Ask</button>
        </form>
      </div>
    </div>
  )
}

function AssistantMessage({ turn }) {
  const [showSql, setShowSql] = useState(false)
  return (
    <div style={s.assistantBubble}>
      <p style={s.answer}>{turn.answer}</p>
      {turn.grounded === false && /\d/.test(turn.answer ?? '') && (
        <p style={s.warning}>⚠ Not based on a query in this turn — please verify.</p>
      )}
      {turn.sql && (
        <>
          <button style={s.linkBtn} onClick={() => setShowSql(v => !v)}>
            {showSql ? 'Hide' : 'Show'} SQL · {turn.row_count} row{turn.row_count === 1 ? '' : 's'} · {turn.latency_s}s
          </button>
          {showSql && <pre style={s.sql}>{turn.sql}</pre>}
        </>
      )}
      {turn.rows?.length > 0 && (
        <div style={s.tableWrap}>
          <table style={s.table}>
            <thead>
              <tr>{turn.columns.map(c => <th key={c} style={s.th}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {turn.rows.map((row, i) => (
                <tr key={i}>{row.map((v, j) => <td key={j} style={s.td}>{formatCell(v)}</td>)}</tr>
              ))}
            </tbody>
          </table>
          {turn.row_count > turn.rows.length && (
            <p style={s.note}>Showing {turn.rows.length} of {turn.row_count} rows.</p>
          )}
        </div>
      )}
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
    maxWidth: 860, margin: '0 auto', background: '#fff', borderRadius: 10, padding: 24,
    boxShadow: '0 1px 3px rgba(0,0,0,0.08)', display: 'flex', flexDirection: 'column', gap: 16,
  },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  title: { fontSize: '1.3rem', marginBottom: 6 },
  subtitle: { color: '#666', fontSize: '0.9rem' },
  newBtn: {
    background: 'none', border: '1px solid #ddd', borderRadius: 6, padding: '6px 12px',
    cursor: 'pointer', color: '#555', whiteSpace: 'nowrap',
  },
  thread: { display: 'flex', flexDirection: 'column', gap: 14, minHeight: 120 },
  examples: { display: 'flex', flexWrap: 'wrap', gap: 8 },
  example: {
    background: '#f0f4ff', color: '#1a73e8', border: '1px solid #d6e2ff', borderRadius: 16,
    padding: '4px 12px', fontSize: '0.8rem', cursor: 'pointer',
  },
  userRow: { display: 'flex', justifyContent: 'flex-end', marginBottom: 8 },
  userBubble: {
    background: '#1a73e8', color: '#fff', padding: '8px 14px', borderRadius: '14px 14px 4px 14px',
    maxWidth: '75%', fontSize: '0.95rem',
  },
  assistantBubble: {
    background: '#f6f7f9', padding: '12px 14px', borderRadius: '14px 14px 14px 4px', maxWidth: '100%',
  },
  answer: { fontSize: '0.98rem', lineHeight: 1.5, marginBottom: 8 },
  warning: { color: '#a15c00', fontSize: '0.82rem', marginBottom: 8 },
  thinking: { color: '#888', fontStyle: 'italic' },
  error: { padding: 12, background: '#fdecea', color: '#a12622', borderRadius: 6 },
  form: { display: 'flex', gap: 8, borderTop: '1px solid #eee', paddingTop: 16 },
  input: { flex: 1, padding: '10px 12px', fontSize: '0.95rem', border: '1px solid #ccc', borderRadius: 6 },
  askBtn: {
    padding: '10px 20px', background: '#1a73e8', color: '#fff', border: 'none', borderRadius: 6,
    cursor: 'pointer', fontWeight: 600,
  },
  linkBtn: {
    background: 'none', border: 'none', color: '#1a73e8', cursor: 'pointer', padding: 0, fontSize: '0.85rem',
  },
  sql: {
    marginTop: 8, padding: 12, background: '#1e1e1e', color: '#d4d4d4', borderRadius: 6,
    fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  },
  tableWrap: { marginTop: 12, overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', background: '#fff' },
  th: { textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid #eee', color: '#666', fontWeight: 500 },
  td: { padding: '6px 8px', borderBottom: '1px solid #f0f0f0' },
  note: { marginTop: 8, color: '#888', fontSize: '0.8rem' },
}
