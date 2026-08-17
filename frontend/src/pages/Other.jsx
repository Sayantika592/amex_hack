import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, DEMO_BLURBS, STATE_LABEL, fmtMoney } from '../api'
import { ActionBadge } from '../components/ui'

export function NewDispute() {
  const nav = useNavigate()
  const [tax, setTax] = useState(null)
  const [txnId, setTxnId] = useState('')
  const [code, setCode] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api.taxonomy().then(setTax) }, [])
  const submit = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.file({ transaction_id: txnId.trim(), user_selected_code: code || null, description: desc })
      nav(`/disputes/${r.dispute_id}`)
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <>
      <div className="page-head">
        <h1>File a dispute</h1>
        <div className="sub">The dropdown selection is a hint — free-text classification decides, and disagreements are surfaced, not hidden.</div>
      </div>
      <div className="card" style={{ maxWidth: 640 }}>
        <label className="f">Transaction ID</label>
        <input className="f" value={txnId} onChange={(e) => setTxnId(e.target.value)}
               placeholder="e.g. T-DEMO-RAHUL or any T-… id from the dataset" />
        <label className="f">What went wrong (dropdown — optional)</label>
        <select className="f" value={code} onChange={(e) => setCode(e.target.value)}>
          <option value="">Let the system classify from my description</option>
          {(tax?.internal_types || []).filter((t) => t.in_techdoc).map((t) => (
            <option key={t.code} value={t.code}>{t.code} — {t.name}</option>
          ))}
        </select>
        <label className="f">Describe the problem in your own words</label>
        <textarea className="f" value={desc} onChange={(e) => setDesc(e.target.value)}
                  placeholder="e.g. The laptop screen was cracked when I opened the box…" />
        {err && <div className="error-box" style={{ marginTop: 10 }}>{err}</div>}
        <button className="btn primary" style={{ marginTop: 12 }} disabled={busy || !txnId || !desc} onClick={submit}>
          File dispute
        </button>
      </div>
    </>
  )
}

export function Demo() {
  const nav = useNavigate()
  const [cases, setCases] = useState([])
  useEffect(() => { api.demoCases().then((r) => setCases(r.items)) }, [])
  return (
    <>
      <div className="page-head">
        <h1>Demo cases</h1>
        <div className="sub">Eight seeded scenarios that exercise every edge of the pipeline. Open one, press “Run pipeline”, and watch the rail fill from real backend stages.</div>
      </div>
      <div className="grid cols-2">
        {cases.map((c) => (
          <div key={c.id} className="card rowlink" style={{ cursor: 'pointer' }} onClick={() => nav(`/disputes/${c.id}`)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span className="mono" style={{ fontWeight: 600 }}>{c.id}</span>
              <ActionBadge action={c.action} />
            </div>
            <div className="note" style={{ margin: '6px 0' }}>{DEMO_BLURBS[c.id] || c.description}</div>
            <div className="note">{fmtMoney(c.amount, c.currency)} · {STATE_LABEL[c.state] || c.state}
              {c.classified_code ? <> · <span className="code">{c.classified_code}</span></> : null}</div>
          </div>
        ))}
      </div>
    </>
  )
}

export function Taxonomy() {
  const [tax, setTax] = useState(null)
  useEffect(() => { api.taxonomy().then(setTax) }, [])
  if (!tax) return <div className="note">Loading taxonomy…</div>
  const macros = {}
  for (const t of tax.internal_types) (macros[t.macro_name || t.macro] ||= []).push(t)
  return (
    <>
      <div className="page-head">
        <h1>Dispute taxonomy</h1>
        <div className="sub">{tax.internal_types.length} internal types across 6 macro groups, mapped to Amex / Visa / Mastercard reason codes. One network code can map to several internal types and vice versa.</div>
      </div>
      {Object.entries(macros).map(([macro, types]) => (
        <div key={macro} className="card">
          <h2>{macro}</h2>
          <table className="data">
            <thead><tr><th>Code</th><th>Name</th><th>Amex</th><th>Visa</th><th>Mastercard</th><th>Source</th></tr></thead>
            <tbody>
              {types.map((t) => (
                <tr key={t.code}>
                  <td><span className="code">{t.code}</span></td>
                  <td>{t.name}</td>
                  <td>{(t.network_codes?.amex || []).map((c) => <span key={c} className="code" style={{ marginRight: 3 }}>{c}</span>)}</td>
                  <td>{(t.network_codes?.visa || []).map((c) => <span key={c} className="code" style={{ marginRight: 3 }}>{c}</span>)}</td>
                  <td>{(t.network_codes?.mastercard || []).map((c) => <span key={c} className="code" style={{ marginRight: 3 }}>{c}</span>)}</td>
                  <td className="note">{t.in_techdoc && t.in_excel ? 'tech doc + excel' : t.in_techdoc ? 'tech doc' : 'excel'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <div className="card">
        <h2>One network code → many internal types</h2>
        {(tax.one_to_many || []).map((m, i) => (
          <div key={i} className="note" style={{ padding: '3px 0' }}>
            <span className="code">{m.network}:{m.network_code}</span> → {m.internal_codes.map((c) => <span key={c} className="code" style={{ marginLeft: 4 }}>{c}</span>)}
            {m.description ? <span> — {m.description}</span> : null}
          </div>
        ))}
      </div>
    </>
  )
}

export function Models() {
  const [m, setM] = useState(null)
  useEffect(() => { api.models().then(setM) }, [])
  if (!m) return <div className="note">Loading model registry…</div>
  return (
    <>
      <div className="page-head">
        <h1>Model registry</h1>
        <div className="sub">Honest per-component modes. REAL means an actual model is loaded; DEMO means a deterministic stand-in with the identical interface — nothing pretends to be what it isn't.</div>
      </div>
      <div className="grid cols-2">
        {Object.entries(m.components || {}).map(([k, c]) => (
          <div key={k} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <h2 style={{ margin: 0 }}>{k}</h2>
              <span className={`badge ${c.mode === 'real' ? 'cm' : 'esc'}`}>{(c.mode || 'demo').toUpperCase()}</span>
            </div>
            <div className="note" style={{ marginTop: 8 }}>{c.detail || c.name || c.component}</div>
            {c.model && <div className="code" style={{ marginTop: 6 }}>{c.model}</div>}
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Runtime setting</h2>
        <div className="note">AI_MODE = <span className="code">{m.ai_mode_setting}</span>. Set <span className="code">AI_MODE=real</span> and install the ML extras to swap in BART-MNLI zero-shot classification, spaCy NLP, and the CLIP/BLIP-2 vision pipeline with no code changes.</div>
      </div>
    </>
  )
}
