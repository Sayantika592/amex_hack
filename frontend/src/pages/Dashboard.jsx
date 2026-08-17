import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ACTION_META, STATE_LABEL, DEMO_BLURBS, DEMO_TITLES, fmtMoney, fmtDate } from '../api'
import { ActionBadge } from '../components/ui'

const dash = (v, f = (x) => x) => (v == null ? '—' : f(v))

export function Dashboard() {
  const nav = useNavigate()
  const [stats, setStats] = useState(null)
  const [acc, setAcc] = useState(null)
  const [demo, setDemo] = useState(null)
  useEffect(() => {
    api.stats().then(setStats)
    api.accuracy().then(setAcc)
    api.demoCases().then(setDemo).catch(() => setDemo({ items: [] }))
  }, [])
  if (!stats) return <div className="note">Loading operational stats…</div>
  const byAction = stats.by_action || {}
  const cats = Object.entries(stats.by_category || {})
    .filter(([k]) => k && k !== 'null').sort((a, b) => b[1] - a[1]).slice(0, 8)
  const retrain = acc?.retraining_candidates || []
  const rahul = (demo?.items || []).find((c) => c.id === 'D-DEMO-RAHUL')
  const others = (demo?.items || []).filter((c) => c.id !== 'D-DEMO-RAHUL')
  const today = stats.today || {}

  return (
    <>
      <div className="page-head">
        <h1>Dispute Resolution Console</h1>
        <div className="sub">Live queue · resolution mix · learning-loop health</div>
      </div>

      {/* ---- flagship demo case, one click ---- */}
      {rahul && (
        <div className="hero card">
          <div className="hero-left">
            <div className="hero-kicker">LIVE DEMO CASE <span className="badge cm" style={{ marginLeft: 8 }}>Recommended demo</span></div>
            <div className="hero-title mono">{rahul.id}</div>
            <div className="hero-line">{DEMO_TITLES[rahul.id]} · {fmtMoney(rahul.amount, rahul.currency)} · <span className="code">QD-01</span> damaged goods</div>
            <div className="note">{DEMO_BLURBS[rahul.id]}</div>
          </div>
          <div className="hero-right">
            <ActionBadge action={rahul.action} />
            <button className="btn primary big" onClick={() => nav('/disputes/D-DEMO-RAHUL?run=1')}>
              ▶ Run live resolution
            </button>
            <div className="note" style={{ textAlign: 'right' }}>Streams all 10 stages from the real backend over SSE.</div>
          </div>
        </div>
      )}

      {/* ---- headline metrics (— when nothing has run) ---- */}
      <div className="grid cols-4" style={{ marginTop: 14 }}>
        <div className="card stat"><div className="n">{dash(stats.total_disputes)}</div><div className="l">Total disputes</div></div>
        <div className="card stat"><div className="n">{dash(stats.auto_resolution_rate, (v) => `${Math.round(v * 100)}%`)}</div><div className="l">Auto-resolution rate</div></div>
        <div className="card stat"><div className="n">{dash(stats.avg_pipeline_seconds, (v) => `${v.toFixed(2)}s`)}</div><div className="l">Avg pipeline time <span className="tiny">measured</span></div></div>
        <div className="card stat"><div className="n">{stats.pipeline_runs ? (byAction.escalate_to_analyst || 0) : '—'}</div><div className="l">Analyst queue</div></div>
      </div>

      {today.runs > 0 && (
        <div className="card today" style={{ marginTop: 14 }}>
          <h2>Today</h2>
          <div className="today-row">
            <span><b>{today.cases}</b> cases processed</span>
            <span><b>{today.auto_resolved}</b> auto-resolved</span>
            <span><b>{today.escalated}</b> escalated</span>
            <span><b>{today.evidence_requested}</b> evidence requested</span>
            <span><b>{today.runs}</b> pipeline runs</span>
          </div>
        </div>
      )}

      {/* ---- seeded scenario launcher ---- */}
      <div className="card" style={{ marginTop: 14 }}>
        <h2>Seeded demo scenarios</h2>
        <div className="note" style={{ marginBottom: 10 }}>
          One happy path, two edge cases (conflict → human review, integrity → escalation), and five more — each runs the real pipeline.
        </div>
        <div className="launcher">
          {others.map((c) => {
            const tone = c.id === 'D-DEMO-FRAUD' ? 'mr'
              : ['D-DEMO-CONFLICT', 'D-DEMO-VAGUE'].includes(c.id) ? 'esc' : 'cm'
            return (
              <button key={c.id} className={`launch ${tone}`} onClick={() => nav(`/disputes/${c.id}`)}>
                <span className="lt">{DEMO_TITLES[c.id] || c.id}</span>
                <span className="li mono">{c.id}</span>
                <span className="lb">{DEMO_BLURBS[c.id]}</span>
                <span className="ls"><ActionBadge action={c.action} /></span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <div className="card">
          <h2>Resolution mix</h2>
          {stats.pipeline_runs === 0 && <div className="note">No runs yet — run a demo case above to populate.</div>}
          {Object.entries(ACTION_META).map(([k, m]) => {
            const n = byAction[k] || 0
            const total = Object.values(byAction).reduce((a, b) => a + b, 0) || 1
            return (
              <div key={k} className="evbar">
                <span className="label">{m.label}</span>
                <div className="track"><div className="fill" style={{ width: `${(n / total) * 100}%`, background: `var(--${m.tone === 'neutral' ? 'muted' : m.tone})` }} /></div>
                <span className="pct">{n || '—'}</span>
              </div>
            )
          })}
        </div>
        <div className="card">
          <h2>Top dispute categories</h2>
          {cats.map(([code, n]) => (
            <div key={code} className="evbar">
              <span className="label">{code}</span>
              <div className="track"><div className="fill" style={{ width: `${(n / (cats[0]?.[1] || 1)) * 100}%`, background: 'var(--info)' }} /></div>
              <span className="pct">{n}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ---- business impact, honestly labeled ---- */}
      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <div className="card">
          <h2>Projected impact <span className="tiny">synthetic benchmark · assumptions stated</span></h2>
          <dl className="kv">
            <dt>Manual resolution today</dt><dd>30–45 days · 3–5 handoffs</dd>
            <dt>Prototype pipeline time</dt><dd className="mono">{dash(stats.avg_pipeline_seconds, (v) => `${v.toFixed(2)}s measured`)} per dispute</dd>
            <dt>Target resolution</dt><dd>&lt;47 min <span className="tiny">projected</span></dd>
            <dt>Auto-resolution target</dt><dd>82% <span className="tiny">projected · assumes 70% structured-evidence coverage</span></dd>
            <dt>Cost per dispute</dt><dd>$25–40 manual → $3–5 auto <span className="tiny">projected</span></dd>
          </dl>
          <div className="note">Projections are mechanism-level on synthetic data — not measured production performance.</div>
        </div>
        <div className="card">
          <h2>Learning loop — weekly implied accuracy</h2>
          {!acc ? <div className="note">Loading…</div> : (
            <>
              <div className="note" style={{ marginBottom: 8 }}>
                Implied accuracy = 1 − (analyst overrides + representment reversals) / decisions.
                Categories under the {Math.round((acc.accuracy_floor || 0.85) * 100)}% floor with ≥10 decisions trigger retraining.
              </div>
              {retrain.length
                ? <div className="error-box">Retraining flagged: {retrain.join(', ')}</div>
                : <div className="ok-box">No category is below the retraining floor.</div>}
            </>
          )}
        </div>
      </div>
    </>
  )
}

export function Disputes() {
  const nav = useNavigate()
  const [data, setData] = useState(null)
  const [state, setState] = useState('')
  const [action, setAction] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => {
    const p = new URLSearchParams()
    if (state) p.set('state', state)
    if (action) p.set('action', action)
    if (q) p.set('q', q)
    api.disputes('?' + p.toString()).then(setData)
  }, [state, action, q])
  return (
    <>
      <div className="page-head">
        <h1>Disputes</h1>
        <div className="sub">{data ? `${data.total} matching disputes` : 'Loading…'}</div>
      </div>
      <div className="card" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <input className="f" style={{ maxWidth: 260 }} placeholder="Search by ID or description"
               value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="f" style={{ maxWidth: 200 }} value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">Any state</option>
          {Object.entries(STATE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="f" style={{ maxWidth: 220 }} value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">Any action</option>
          {Object.entries(ACTION_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>
      <div className="card">
        <table className="data">
          <thead><tr>
            <th>Dispute</th><th>Category</th><th>Amount</th><th>Filed</th>
            <th>State</th><th>Score</th><th>Action</th>
          </tr></thead>
          <tbody>
            {(data?.items || []).map((d) => (
              <tr key={d.id} className="rowlink" onClick={() => nav(`/disputes/${d.id}`)}>
                <td className="mono">{d.id}</td>
                <td>{d.classified_code ? <span className="code">{d.classified_code}</span> : <span className="note">unclassified</span>}</td>
                <td>{fmtMoney(d.amount, d.currency)}</td>
                <td>{fmtDate(d.filed_date)}</td>
                <td>{STATE_LABEL[d.state] || d.state}</td>
                <td className="mono">{d.final_score != null ? (d.final_score >= 0 ? '+' : '') + d.final_score.toFixed(2) : '—'}</td>
                <td><ActionBadge action={d.action} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.items.length && <div className="note" style={{ padding: 14 }}>No disputes match these filters — clear a filter or file a new dispute.</div>}
      </div>
    </>
  )
}
