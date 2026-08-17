import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api, STATE_LABEL, DEMO_TITLES, fmtMoney, fmtDate } from '../api'
import { ActionBadge, Beam, EvidenceBars, FactorBars, ModeBadge, PipelineRail, ProgressSteps, useModels } from '../components/ui'

const OUTCOME_META = {
  auto_approve: { tone: 'cm', line: 'RESOLVED IN FAVOUR OF CARD MEMBER', icon: '🟢' },
  auto_deny: { tone: 'mr', line: 'RESOLVED IN FAVOUR OF MERCHANT', icon: '🔵' },
  represent_chargeback: { tone: 'mr', line: 'MERCHANT REPRESENTMENT PATH', icon: '🔵' },
  escalate_to_analyst: { tone: 'esc', line: 'HUMAN REVIEW REQUIRED', icon: '🟠' },
  request_more_evidence: { tone: 'info', line: 'MORE EVIDENCE REQUESTED', icon: '🔷' },
}

export default function DisputeDetail() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [events, setEvents] = useState([])
  const [running, setRunning] = useState(false)
  const [role, setRole] = useState('analyst')
  const [tab, setTab] = useState('ledger')
  const [views, setViews] = useState({})
  const [err, setErr] = useState('')
  const [thresholds, setThresholds] = useState(null)
  const autoRan = useRef(false)

  const reload = useCallback(() => {
    api.dispute(id).then(setData).catch((e) => setErr(e.message))
    for (const r of ['card_member', 'merchant', 'analyst'])
      api.view(id, r).then((v) => setViews((s) => ({ ...s, [r]: v }))).catch(() => {})
  }, [id])
  useEffect(() => { reload(); api.thresholds().then(setThresholds).catch(() => {}) }, [reload])

  useEffect(() => {
    const es = new EventSource(`/api/events/${id}`)
    es.onmessage = (m) => {
      try {
        const ev = JSON.parse(m.data)
        setEvents((prev) => [...prev, { ...ev, at: ev.ts ? new Date(ev.ts * 1000).toISOString() : new Date().toISOString() }])
        if (ev.stage === 'pipeline' && ev.status === 'complete') {
          setRunning(false)
          setTimeout(reload, 250)
        }
      } catch { /* keepalive */ }
    }
    return () => es.close()
  }, [id, reload])

  const runPipeline = useCallback(async () => {
    setErr(''); setRunning(true); setEvents([])
    try { await api.run(id) } catch (e) { setErr(e.message); setRunning(false) }
  }, [id])

  // one-click flagship flow: /disputes/D-DEMO-RAHUL?run=1 auto-runs once
  useEffect(() => {
    if (params.get('run') === '1' && !autoRan.current) {
      autoRan.current = true
      setParams({}, { replace: true })
      setTimeout(runPipeline, 400)
    }
  }, [params, setParams, runPipeline])

  if (err && !data) return <div className="error-box">{err}</div>
  if (!data) return <div className="note">Loading dispute…</div>
  const d = data.dispute
  const run = data.pipeline_run
  const stages = run?.stages || {}
  const decision = stages.decision || {}
  const action = stages.action || {}
  const score = data.decision?.final_score ?? decision.composite_score
  const approveAt = thresholds?.score_bands?.favor_cardholder ?? 0.3

  return (
    <>
      <div className="page-head case-head">
        <div>
          <h1 className="mono" style={{ fontSize: 20 }}>
            {d.id}
            {DEMO_TITLES[d.id] && <span className="case-title"> · {DEMO_TITLES[d.id]}</span>}
          </h1>
          <div className="sub">
            {fmtMoney(d.amount, d.currency)} · filed {fmtDate(d.filed_date)} · {STATE_LABEL[d.state] || d.state}
            {d.classified_code ? <> · <span className="code">{d.classified_code}</span></> : null}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <ModeBadge compact />
          <ActionBadge action={d.action} />
          <button className="btn primary" onClick={runPipeline} disabled={running}>
            {running ? 'Pipeline running…' : run ? '▶ Re-run pipeline' : '▶ Run pipeline'}
          </button>
        </div>
      </div>
      {err && <div className="error-box" style={{ marginBottom: 12 }}>{err}</div>}

      <div className="case-grid">
        {/* ------------------------------- left: the 10 stages, live */}
        <div className="card">
          <h2>10-stage pipeline <span className="tiny">real backend state · click any stage for its full output</span></h2>
          <PipelineRail events={events} record={stages} timings={stages.timings} />
        </div>

        {/* ------------------------------- right: decision + claim */}
        <div>
          <DecisionCard d={d} action={action} decision={decision} score={score}
                        approveAt={approveAt} reasoning={stages.reasoning} running={running} />
          <div className="card">
            <h2>Claim</h2>
            <p style={{ margin: '0 0 8px' }}>{d.description}</p>
            <dl className="kv">
              <dt>Network</dt><dd className="mono">{d.network}</dd>
              <dt>Member selected</dt><dd>{d.user_selected_code ? <span className="code">{d.user_selected_code}</span> : 'not selected'}</dd>
              <dt>System classified</dt><dd>{d.classified_code ? <span className="code">{d.classified_code}</span> : '—'}
                {d.classification_confidence != null && <span className="note"> · {Math.round(d.classification_confidence * 100)}%</span>}</dd>
              <dt>Network codes</dt><dd>{(d.network_reason_codes || []).map((c) => <span key={c} className="code" style={{ marginRight: 4 }}>{c}</span>)}</dd>
            </dl>
          </div>
        </div>
      </div>

      {/* ------------------------------- bottom: ledger / why / events / rules */}
      <div className="card" style={{ marginTop: 14 }}>
        <div className="role-tabs" role="tablist">
          {[['ledger', 'Evidence ledger'], ['why', 'Why this decision?'], ['events', 'Event stream'], ['rules', 'Network rules']].map(([k, l]) => (
            <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)} role="tab" aria-selected={tab === k}>{l}</button>
          ))}
        </div>
        {tab === 'ledger' && <EvidenceLedger stages={stages} analyst={views.analyst} disputeId={id} />}
        {tab === 'why' && <WhyDecision decision={decision} action={action} reasoning={stages.reasoning} approveAt={approveAt} />}
        {tab === 'events' && <EventStream events={events} />}
        {tab === 'rules' && <RuleInspector d={d} stages={stages} thresholds={thresholds} analyst={views.analyst} />}
      </div>

      {/* ------------------------------- three portals */}
      <div className="card" style={{ marginTop: 14 }}>
        <h2>Role views — same decision, three projections</h2>
        <div className="role-tabs" role="tablist">
          {[['card_member', 'Card member'], ['merchant', 'Merchant'], ['analyst', 'Analyst']].map(([k, l]) => (
            <button key={k} className={role === k ? 'on' : ''} onClick={() => setRole(k)} role="tab" aria-selected={role === k}>{l}</button>
          ))}
        </div>
        {role === 'card_member' && <CardMemberView v={views.card_member} />}
        {role === 'merchant' && <MerchantView v={views.merchant} id={id} onDone={reload} />}
        {role === 'analyst' && <AnalystView v={views.analyst} id={id} onDone={reload} action={action} />}
      </div>
    </>
  )
}

/* ================================================================ pieces */

function DecisionCard({ d, action, decision, score, approveAt, reasoning, running }) {
  const meta = OUTCOME_META[action.action]
  if (!meta) {
    return (
      <div className="card decision-hero pending">
        <div className="dh-line">{running ? 'PIPELINE RUNNING…' : 'NO DECISION YET'}</div>
        <div className="note">{running ? 'Stages are streaming on the left.' : 'Run the pipeline to produce a decision with full reasoning.'}</div>
      </div>
    )
  }
  const conclusive = decision.conclusive_evidence || []
  const burden = reasoning?.burden_of_proof || decision.burden_of_proof
  return (
    <div className={`card decision-hero ${meta.tone}`}>
      <div className="dh-line">{meta.icon} {meta.line}</div>
      {action.refund_amount > 0 && <div className="dh-amount">{fmtMoney(action.refund_amount, action.currency || d.currency)} REFUND</div>}
      <div className="dh-nums mono">
        {action.confidence != null && <span>Confidence <b>{Math.round(action.confidence * 100)}%</b></span>}
        {score != null && <span>Score <b>{score >= 0 ? '+' : ''}{Number(score).toFixed(2)}</b></span>}
        <span>Threshold <b>±{approveAt.toFixed(2)}</b></span>
      </div>
      <Beam score={score ?? 0} />
      {action.reason === 'compliance_override' && (
        <div className="warn-box" style={{ marginTop: 8 }}>Network-rule override: {action.detail || action.override_rule}</div>
      )}
      {decision.conflict_hold && (
        <div className="warn-box" style={{ marginTop: 8 }}>Conflicting sub-claims — auto-resolution paused pending clarification.</div>
      )}
      {conclusive.length > 0 && (
        <div className="ok-box" style={{ marginTop: 8 }}>
          Conclusive fact applied: {conclusive.map((c) => c.reason.replace(/_/g, ' ')).join(', ')}
        </div>
      )}
      {burden && <div className="note" style={{ marginTop: 8 }}>Burden of proof: <b>{burden.bearer}</b> — {burden.requirement || burden.rationale}</div>}
      {action.action === 'escalate_to_analyst' && (
        <div className="note" style={{ marginTop: 4 }}>Integrity/uncertainty prevents autonomous resolution — this is deliberate, not a failure.</div>
      )}
    </div>
  )
}

function EvidenceLedger({ stages, analyst, disputeId }) {
  const [open, setOpen] = useState(null)
  const models = useModels()
  const items = stages.evidence_scoring?.items || {}
  const missing = stages.evidence_collection?.missing_required || []
  const sourceByType = {}
  for (const e of analyst?.evidence_items || []) sourceByType[e.evidence_type] = e
  const rows = Object.entries(items)
  if (!rows.length && !missing.length) return <div className="note">Run the pipeline to collect and score evidence.</div>
  const visionMode = models?.components?.vision?.[0]?.mode || 'demo'
  return (
    <>
      <table className="data ledger">
        <thead><tr><th>Evidence</th><th>Source</th><th>Status</th><th>Strength</th><th>Supports</th><th></th></tr></thead>
        <tbody>
          {rows.map(([type, it]) => {
            const src = it.source_party || sourceByType[type]?.source_party || '—'
            const supports = it.supports ? it.supports.replace('cardholder', 'card member') : '—'
            const pct = Math.round((it.final_strength || 0) * 100)
            const isOpen = open === type
            const payload = sourceByType[type]?.payload
            return (
              <React.Fragment key={type}>
                <tr className="rowlink" onClick={() => setOpen(isOpen ? null : type)}>
                  <td><span className="code">{type}</span>{it.resolved_type && it.resolved_type !== type && <span className="tiny"> → {it.resolved_type}</span>}</td>
                  <td className="cap">{src}</td>
                  <td><span className="badge cm" style={{ background: 'var(--surface-2)', color: 'var(--ink-soft)' }}>collected</span></td>
                  <td>
                    <div className="strength-cell">
                      <div className="track"><div className={`fill s-${it.strength_label}`} style={{ width: `${pct}%` }} /></div>
                      <span className="mono">{pct}% {it.strength_label}</span>
                    </div>
                  </td>
                  <td className="cap">{supports}</td>
                  <td className="tiny">{isOpen ? '▾ close' : '▸ detail'}</td>
                </tr>
                {isOpen && (
                  <tr className="ledger-detail"><td colSpan={6}>
                    {it.vision && <VisionPanel vision={it.vision} mode={it.vision.mode || visionMode} model={it.vision.model} strength={it.final_strength} disputeId={disputeId} />}
                    {(it.notes || []).map((n, i) => <div key={i} className="note">· {n}</div>)}
                    {payload && <pre>{JSON.stringify(payload, null, 1)}</pre>}
                  </td></tr>
                )}
              </React.Fragment>
            )
          })}
          {missing.map((m) => (
            <tr key={m} className="missing-row">
              <td><span className="code">{m}</span></td>
              <td>—</td>
              <td><span className="badge esc">missing</span></td>
              <td><span className="tiny">not provided — feeds “request more evidence”</span></td>
              <td>—</td><td />
            </tr>
          ))}
        </tbody>
      </table>
      <div className="note" style={{ marginTop: 8 }}>
        Every item is scored before the decision model sees it (base strength × quality × recency). Missing required evidence is shown, never hidden.
      </div>
    </>
  )
}

function VisionPanel({ vision, mode, model, strength, disputeId }) {
  const real = mode === 'real'
  const [imgErr, setImgErr] = useState(false)
  return (
    <div className="vision-panel">
      <div className="vp-head">
        IMAGE VERIFICATION
        <span className={`mode-badge ${real ? 'real' : 'demo'}`} style={{ marginLeft: 8 }}
              title={model || ''}>
          <span className="dot" />{real ? `${model || 'CLIP + BLIP-2'} · REAL` : 'DeterministicVision · DEMO fallback'}
        </span>
      </div>
      {!imgErr && disputeId && (
        <div className="vp-images">
          <figure>
            <img src={api.imageUrl(disputeId, 'listing')} alt="Merchant listing image"
                 onError={() => setImgErr(true)} />
            <figcaption>Merchant listing</figcaption>
          </figure>
          <div className="vp-arrow" aria-hidden="true">vs</div>
          <figure>
            <img src={api.imageUrl(disputeId, 'photo')} alt="Card member's uploaded photo"
                 onError={() => setImgErr(true)} />
            <figcaption>Card member's photo</figcaption>
          </figure>
        </div>
      )}
      <dl className="kv">
        <dt>Product match</dt><dd className="mono">{vision.product_match === null ? 'inconclusive' : vision.product_match ? `YES · ${Math.round((vision.combined_score || 0) * 100)}%` : 'NO'}</dd>
        {vision.image_similarity != null && <><dt>{real ? 'CLIP similarity' : 'Image similarity'}</dt><dd className="mono">{vision.image_similarity}</dd></>}
        <dt>Damage detected</dt><dd className="mono">{vision.has_damage ? `YES · ${(vision.severity_label || '').toUpperCase()}` : 'NO'}</dd>
        {vision.damage_description && <><dt>{real ? 'BLIP-2 description' : 'Damage description'}</dt><dd>“{vision.damage_description}”</dd></>}
        {strength != null && <><dt>Evidence strength</dt><dd className="mono">{strength}</dd></>}
      </dl>
    </div>
  )
}

function WhyDecision({ decision, action, reasoning, approveAt }) {
  const fb = decision.factor_breakdown
  if (!fb) return <div className="note">Run the pipeline to see the weighted reasoning.</div>
  const textByDim = {}
  for (const f of reasoning?.detailed_factors || []) textByDim[f.dimension] = f.text
  const rows = Object.entries(fb)
    .filter(([, f]) => (f.weight ?? 0) > 0 || Math.abs(f.weighted ?? 0) > 0.0001)
    .sort((a, b) => Math.abs(b[1].weighted ?? 0) - Math.abs(a[1].weighted ?? 0))
  const total = decision.composite_score ?? decision.final_score ?? 0
  return (
    <div className="why">
      {rows.map(([dim, f]) => {
        const v = f.weighted ?? 0
        return (
          <div key={dim} className="why-row">
            <span className={`why-val mono ${v > 0 ? 'pos' : v < 0 ? 'neg' : ''}`}>{v >= 0 ? '+' : ''}{v.toFixed(2)}</span>
            <span className="why-dim">{dim.replace(/_/g, ' ')} <span className="tiny">w {(f.weight ?? 0).toFixed(2)}</span></span>
            <span className="why-text">{textByDim[dim] || (f.reason || '').replace(/_/g, ' ')}{f.detail ? ` — ${f.detail}` : ''}</span>
          </div>
        )
      })}
      <div className="why-total">
        <span className={`why-val mono ${total > 0 ? 'pos' : total < 0 ? 'neg' : ''}`}>{total >= 0 ? '+' : ''}{Number(total).toFixed(2)}</span>
        <span className="why-dim">FINAL SCORE</span>
        <span className="why-text mono">
          {action.action ? `→ ${action.action.replace(/_/g, ' ').toUpperCase()}` : ''}
          <span className="tiny" style={{ marginLeft: 8 }}>decisive only outside ±{approveAt.toFixed(2)}</span>
        </span>
      </div>
      {reasoning?.summary && <p className="note" style={{ marginTop: 10 }}>{reasoning.summary}</p>}
    </div>
  )
}

function EventStream({ events }) {
  const real = events.filter((e) => e.stage)
  if (!real.length) return <div className="note">Run the pipeline — live SSE events from the backend will appear here.</div>
  return (
    <div className="stream mono">
      {real.map((e, i) => (
        <div key={i} className={`ev ${i === real.length - 1 ? 'last' : ''}`}>
          <span className="ts">{(e.at || '').slice(11, 19)}</span>
          <span className="st">{e.stage}</span>
          <span className="ss">{e.status}</span>
          {e.payload_summary && Object.keys(e.payload_summary).length > 0 &&
            <span className="sp">{JSON.stringify(e.payload_summary).slice(0, 90)}</span>}
        </div>
      ))}
    </div>
  )
}

function RuleInspector({ d, stages, thresholds, analyst }) {
  const mapping = stages.evidence_mapping?.primary || {}
  const cites = stages.reasoning?.rule_citations || []
  const burden = stages.reasoning?.burden_of_proof || analyst?.burden_of_proof
  return (
    <div className="grid cols-2">
      <dl className="kv">
        <dt>Network</dt><dd className="cap">{d.network === 'amex' ? 'American Express' : d.network}</dd>
        <dt>Internal type</dt><dd>{d.classified_code ? <span className="code">{d.classified_code}</span> : '—'}</dd>
        <dt>Network reason codes</dt><dd>{(mapping.network_reason_codes || d.network_reason_codes || []).map((c) => <span key={c} className="code" style={{ marginRight: 4 }}>{c}</span>)}</dd>
        <dt>Required evidence</dt><dd>{(mapping.required_evidence || []).map((e) => <span key={e} className="code" style={{ marginRight: 4, marginBottom: 4, display: 'inline-block' }}>{e}</span>)}</dd>
        <dt>Burden of proof</dt><dd>{burden ? <><b className="cap">{burden.bearer}</b> — {burden.requirement || burden.rationale}</> : '—'}</dd>
        <dt>Decision thresholds</dt><dd className="mono">approve ≥ +{thresholds?.score_bands?.favor_cardholder ?? 0.3} · escalate within ±{Math.abs(thresholds?.score_bands?.escalation_low ?? 0.3)} · source {thresholds?.source || 'config'}</dd>
      </dl>
      <div>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 13, margin: '0 0 6px' }}>Rules retrieved for this case (RAG)</h2>
        {!cites.length && <div className="note">No rule citations yet — they attach when the reasoning stage runs.</div>}
        {cites.map((c, i) => (
          <div key={i} className="cite">
            <div className="mono" style={{ fontWeight: 600 }}>{c.id || c.citation}</div>
            <div className="note">{c.text}</div>
          </div>
        ))}
        <div className="note" style={{ marginTop: 8 }}>Evidence requirements and thresholds are configuration (YAML), not code — a network rule change is a config edit.</div>
      </div>
    </div>
  )
}

/* ================================================================ roles */

function CardMemberView({ v }) {
  if (!v) return <div className="note">Run the pipeline to populate this view.</div>
  return (
    <div className="grid cols-2">
      <div>
        <div style={{ fontFamily: 'var(--display)', fontSize: 18, fontWeight: 700 }}>{v.status_label}</div>
        {v.refund_amount != null && <div className="ok-box" style={{ margin: '8px 0' }}>Refund of {fmtMoney(v.refund_amount)} to your card. {v.refund_note || ''}</div>}
        <ProgressSteps steps={v.progress || []} />
        {v.decision_statement && <p>{v.decision_statement}</p>}
        {v.confidence_pct != null && <div className="note">Decision confidence {v.confidence_pct}%.</div>}
      </div>
      <div>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 13, margin: '0 0 8px' }}>Why we decided this</h2>
        {(v.why || []).map((w, i) => (
          <div key={i} className="evbar">
            <span className="label" style={{ fontFamily: 'var(--body)' }}>{w.text}</span>
            <div className="track"><div className="fill" style={{ width: `${w.weight_pct}%` }} /></div>
            <span className="pct">{w.weight_pct}%</span>
          </div>
        ))}
        {v.what_we_need_from_you?.length ? (
          <div className="card" style={{ marginTop: 10, background: 'var(--surface-2)' }}>
            <h2>What we need from you</h2>
            {v.what_we_need_from_you.map((e) => <div key={e} className="code" style={{ marginRight: 6 }}>{e}</div>)}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function MerchantView({ v, id, onDone }) {
  const [statement, setStatement] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  if (!v) return <div className="note">Run the pipeline to populate this view.</div>
  const respond = async (kind) => {
    setBusy(true); setMsg('')
    try {
      if (kind === 'represent') await api.representment(id, { statement })
      else await api.merchantResponse(id, { statement, response_type: kind })
      setMsg('Submitted — the pipeline re-ran with your evidence.')
      onDone()
    } catch (e) { setMsg(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="grid cols-2">
      <div>
        <dl className="kv">
          <dt>Outcome</dt><dd>{v.outcome || 'pending'}</dd>
          <dt>Category</dt><dd>{v.category || '—'}</dd>
          <dt>Response window</dt><dd>{v.response_window_days_left != null ? `${v.response_window_days_left} days remaining` : v.response_deadline || '—'}</dd>
          <dt>Burden of proof</dt><dd>{v.burden_of_proof?.bearer || '—'} — {v.burden_of_proof?.rationale || v.burden_of_proof?.requirement || ''}</dd>
        </dl>
        {v.decision_statement && <p>{v.decision_statement}</p>}
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 13, margin: '12px 0 6px' }}>Evidence strength on file</h2>
        <EvidenceBars bars={v.evidence_strength_bars} />
        {v.what_would_help?.length ? (
          <div className="warn-box" style={{ marginTop: 8 }}>What would strengthen your case: {v.what_would_help.join(', ')}</div>
        ) : null}
      </div>
      <div>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 13, margin: '0 0 6px' }}>Respond to this dispute</h2>
        <textarea className="f" placeholder="Merchant statement — describe your evidence"
                  value={statement} onChange={(e) => setStatement(e.target.value)} />
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button className="btn" disabled={busy || !statement} onClick={() => respond('contest')}>Contest with statement</button>
          <button className="btn" disabled={busy} onClick={() => respond('accept')}>Accept the dispute</button>
          {v.can_represent && <button className="btn primary" disabled={busy || !statement} onClick={() => respond('represent')}>File representment</button>}
        </div>
        {msg && <div className="note" style={{ marginTop: 8 }}>{msg}</div>}
      </div>
    </div>
  )
}

function AnalystView({ v, id, onDone, action }) {
  const [act, setAct] = useState('accept')
  const [outcome, setOutcome] = useState('favor_cardholder')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [recorded, setRecorded] = useState(null)
  if (!v) return <div className="note">Run the pipeline to populate this view.</div>
  const expl = v.explanation || {}
  const systemRec = (action?.action || v.dispute?.action || '').replace(/_/g, ' ')
  const submit = async () => {
    setBusy(true); setMsg('')
    try {
      await api.analystOverride(id, {
        action: act, new_outcome: act === 'accept' ? null : outcome, reason,
      })
      setRecorded({ system: systemRec, analyst: act === 'accept' ? `accept (${systemRec})` : `${act} → ${outcome.replace(/_/g, ' ')}`, reason })
      setMsg('')
      onDone()
    } catch (e) { setMsg(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="grid cols-2">
      <div>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 13, margin: '0 0 6px' }}>Factor breakdown (weighted)</h2>
        <FactorBars breakdown={v.factor_breakdown} />
        <hr className="divider" />
        <dl className="kv">
          <dt>Burden of proof</dt><dd>{v.burden_of_proof?.bearer} — {v.burden_of_proof?.rationale || v.burden_of_proof?.requirement}</dd>
          <dt>Integrity</dt><dd>
            suspicion {v.integrity_signals?.suspicion_score ?? 0}
            {v.integrity_signals?.is_suspicious ? <span className="badge esc" style={{ marginLeft: 6 }}>flagged — advisory only, never auto-denied</span> : null}
          </dd>
          <dt>Fairness</dt><dd className="note">{v.counterfactual_note}</dd>
        </dl>
        {(v.integrity_signals?.signals || []).map((s, i) => (
          <div key={i} className="note">· {s.signal}: {s.detail}</div>
        ))}
        {expl.decision_statement && (<><hr className="divider" /><p>{expl.decision_statement}</p></>)}
        {(v.compliance?.overrides || []).map((o, i) => (
          <div key={i} className="badge info" style={{ marginRight: 6 }}>{o.rule}</div>
        ))}
      </div>
      <div>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 13, margin: '0 0 6px' }}>Analyst decision</h2>
        {recorded ? (
          <div className="ok-box override-confirm">
            <div className="mono" style={{ fontWeight: 700 }}>DECISION RECORDED</div>
            <dl className="kv" style={{ marginTop: 6 }}>
              <dt>System recommendation</dt><dd className="cap">{recorded.system || '—'}</dd>
              <dt>Analyst decision</dt><dd className="cap">{recorded.analyst}</dd>
              <dt>Reason</dt><dd>{recorded.reason}</dd>
            </dl>
            <div className="note">✓ Override recorded · ✓ Feedback event created — this trains the learning loop (Layer 9).</div>
          </div>
        ) : (
          <>
            {systemRec && <div className="note" style={{ marginBottom: 6 }}>System recommendation: <b className="cap">{systemRec}</b></div>}
            <label className="f">Action</label>
            <select className="f" value={act} onChange={(e) => setAct(e.target.value)}>
              <option value="accept">Accept the system decision</option>
              <option value="modify">Modify the outcome</option>
              <option value="override">Override the outcome</option>
            </select>
            {act !== 'accept' && (
              <>
                <label className="f">New outcome</label>
                <select className="f" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                  <option value="favor_cardholder">Favor card member</option>
                  <option value="favor_merchant">Favor merchant</option>
                </select>
              </>
            )}
            <label className="f">Reason (required — recorded as a learning signal)</label>
            <textarea className="f" value={reason} onChange={(e) => setReason(e.target.value)}
                      placeholder="Why — this feeds Layer 9 and weekly accuracy reports" />
            <button className="btn primary" style={{ marginTop: 10 }} disabled={busy || !reason} onClick={submit}>
              Record decision
            </button>
          </>
        )}
        {msg && <div className="error-box" style={{ marginTop: 8 }}>{msg}</div>}
        <hr className="divider" />
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 13, margin: '0 0 6px' }}>Evidence docket</h2>
        {(v.evidence_items || []).map((e) => (
          <div key={e.id} className="note" style={{ padding: '3px 0' }}>
            <span className="code">{e.evidence_type}</span> from {e.source_party}
          </div>
        ))}
        {(v.merchant_responses || []).map((r) => (
          <div key={r.id} className="note" style={{ padding: '3px 0' }}>
            Merchant {r.is_representment ? 'representment' : r.response_type}: “{r.statement}”
          </div>
        ))}
        {(v.analyst_actions || []).map((a) => (
          <div key={a.id} className="note" style={{ padding: '3px 0' }}>
            Prior analyst action: {a.action} — “{a.reason}”
          </div>
        ))}
      </div>
    </div>
  )
}
