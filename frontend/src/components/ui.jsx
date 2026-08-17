import React, { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { api, ACTION_META, STAGES } from '../api'

/* ---------------------------------------------------------------- shell */
let _modeCache = null
export function useModels() {
  const [models, setModels] = useState(_modeCache)
  useEffect(() => {
    if (!_modeCache) api.models().then((m) => { _modeCache = m; setModels(m) }).catch(() => {})
  }, [])
  return models
}

export function ModeBadge({ compact }) {
  const models = useModels()
  if (!models) return null
  const clf = models.components?.classifier
  const real = clf?.mode === 'real'
  return (
    <span className={`mode-badge ${real ? 'real' : 'demo'}`}
          title={real
            ? `REAL AI mode — ${clf.model}`
            : `Deterministic fallback active — ${clf?.model || 'demo adapters'}. The UI never claims a model ran when it did not.`}>
      <span className="dot" />
      {real ? 'AI MODE: REAL' : 'DEMO MODE'}
      {!compact && <small>{real ? 'BART-large-MNLI' : 'deterministic fallback'}</small>}
    </span>
  )
}

export function Shell({ children }) {
  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          Dispute Console
          <small>frictionless resolution</small>
        </div>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/disputes">Disputes</NavLink>
          <NavLink to="/new">File a dispute</NavLink>
          <NavLink to="/demo">Demo cases</NavLink>
          <NavLink to="/taxonomy">Taxonomy</NavLink>
          <NavLink to="/models">Models</NavLink>
        </nav>
        <div className="rail-mode"><ModeBadge /></div>
        <div className="foot">10-layer pipeline · Amex / Visa / MC codes · demo build</div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}

export function ActionBadge({ action }) {
  if (!action) return <span className="badge neutral">pending</span>
  const m = ACTION_META[action] || { label: action, tone: 'neutral' }
  return <span className={`badge ${m.tone}`}>{m.label}</span>
}

/* ---------------------------------------------------------------- beam */
export function Beam({ score }) {
  const s = Math.max(-1, Math.min(1, score ?? 0))
  const pct = ((s + 1) / 2) * 100
  return (
    <div className="beam" role="img"
         aria-label={`Decision score ${s >= 0 ? '+' : ''}${s.toFixed(2)} on a −1 merchant to +1 card member axis`}>
      <span className="pole left">MERCHANT −1.0</span>
      <span className="pole right">CARD MEMBER +1.0</span>
      <div className="axis" />
      <div className="zone" style={{ left: '35%', width: '30%' }} title="−0.3 … +0.3 escalation zone" />
      {[-1, -0.5, 0, 0.5, 1].map((t) => (
        <span key={t} className="tick" style={{ left: `${((t + 1) / 2) * 100}%` }}>{t > 0 ? `+${t}` : t}</span>
      ))}
      <div className="marker" style={{ left: `${pct}%` }}>
        <span className="val">{s >= 0 ? '+' : ''}{s.toFixed(2)}</span>
        <span className="pin" />
      </div>
    </div>
  )
}

/* --------------------------------------------------------- pipeline rail */
const fmtPct = (v) => (v == null ? null : `${Math.round(v * 100)}%`)

/** One-line human summary of each stage's real output. */
function stageSummary(key, p) {
  if (!p) return null
  try {
    switch (key) {
      case 'graph_context': {
        const bits = []
        if (p.prior_dispute_count != null) bits.push(`${p.prior_dispute_count} prior disputes`)
        if (p.merchant_dispute_rate != null) bits.push(`merchant rate ${fmtPct(p.merchant_dispute_rate)}`)
        if (p.existing_refund) bits.push('existing refund found')
        return bits.join(' · ') || 'context loaded'
      }
      case 'classification':
        return p.primary_code
          ? `${p.primary_code} · ${fmtPct(p.confidence)} · ${p.status}${p.override ? ' · corrected dropdown' : ''}`
          : p.status
      case 'evidence_mapping': {
        const n = (p.union_required || p.primary?.required_evidence || []).length
        const codes = (p.primary?.network_reason_codes || []).join(', ')
        return `${n} required evidence types${codes ? ` · network code ${codes}` : ''}`
      }
      case 'evidence_collection': {
        const got = (p.collected_types || []).length
        const missing = (p.missing_required || []).length
        return `${got} collected${missing ? ` · ${missing} missing` : ' · complete'} · ${fmtPct(p.completeness)}`
      }
      case 'evidence_scoring': {
        const s = p.summary || {}
        return ['strong', 'moderate', 'weak'].filter((k) => s[k])
          .map((k) => `${s[k]} ${k}`).join(' · ') || 'scored'
      }
      case 'integrity':
        return p.is_suspicious
          ? `FLAGGED · suspicion ${p.suspicion_score} · advisory only`
          : `CLEAR · suspicion ${p.suspicion_score ?? 0}`
      case 'decision': {
        const v = p.composite_score ?? p.final_score
        if (v == null) return null
        const dir = v > 0 ? 'card member' : v < 0 ? 'merchant' : 'neutral'
        return `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)} · leans ${dir}${p.conclusive_evidence?.length ? ' · conclusive fact' : ''}${p.conflict_hold ? ' · CONFLICT HOLD' : ''}`
      }
      case 'compliance': {
        const o = p.overrides || []
        return o.length ? `OVERRIDE: ${o.map((x) => x.rule).join(', ')}` : 'PASS'
      }
      case 'reasoning': {
        const cites = (p.rule_citations || []).map((c) => c.id || c.citation).filter(Boolean)
        return cites.length ? `cited ${cites.slice(0, 2).join(', ')}` : (p.decision_statement || '').slice(0, 60)
      }
      case 'action':
        return `${(p.action || '').replace(/_/g, ' ').toUpperCase()}${p.refund_amount ? ` · refund ${Math.round(p.refund_amount).toLocaleString('en-IN')}` : ''}`
      case 'feedback':
        return p.recorded ? 'outcome recorded for learning loop' : 'recorded'
      default:
        return null
    }
  } catch { return null }
}

function stageTone(key, p) {
  if (!p) return ''
  if (key === 'integrity' && p.is_suspicious) return 'warn'
  if (key === 'compliance' && (p.overrides || []).length) return 'warn'
  if (key === 'decision' && p.conflict_hold) return 'warn'
  if (key === 'action' && p.action === 'escalate_to_analyst') return 'escalated'
  return ''
}

export function PipelineRail({ events, record, timings }) {
  const [open, setOpen] = useState({})
  const byStage = {}
  for (const e of events || []) byStage[e.stage] = e
  return (
    <div className="pipe">
      {STAGES.map(([key, name], i) => {
        const ev = byStage[key]
        const status = ev?.status || (record?.[key] && Object.keys(record[key]).length ? 'complete' : 'idle')
        const payload = record?.[key] && Object.keys(record[key]).length
          ? record[key]
          : (ev?.payload_summary || null)
        const isOpen = open[key]
        const summary = stageSummary(key, payload)
        const tone = stageTone(key, payload)
        const t = timings?.[key]
        return (
          <div key={key} className={`stage ${status} ${tone}`}>
            <div className="dot" />
            <div className="head" role="button" tabIndex={0}
                 onClick={() => setOpen((o) => ({ ...o, [key]: !o[key] }))}
                 onKeyDown={(e) => e.key === 'Enter' && setOpen((o) => ({ ...o, [key]: !o[key] }))}>
              <span className="num">{String(i + 1).padStart(2, '0')}</span>
              <span className="name">{name}</span>
              {summary && <span className="summ">{summary}</span>}
              <span className="status">
                {t != null && <span className="dur">{(t * 1000).toFixed(0)}ms</span>}
                {status === 'complete' ? '✓' : status}
              </span>
            </div>
            {isOpen && payload ? <div className="body"><pre>{JSON.stringify(payload, null, 1)}</pre></div> : null}
          </div>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------- factors */
export function FactorBars({ breakdown }) {
  if (!breakdown) return null
  const entries = Object.entries(breakdown)
  return (
    <div>
      {entries.map(([name, f]) => {
        const v = f.weighted ?? 0
        const mag = Math.min(Math.abs(v) / 0.4, 1) * 50
        const style = v >= 0
          ? { left: '50%', width: `${mag}%`, background: 'var(--cm)' }
          : { right: '50%', width: `${mag}%`, background: 'var(--mr)' }
        return (
          <div key={name} className="factor" title={`${f.reason || ''} ${f.detail || ''}`}>
            <span className="fname">{name}</span>
            <div className="bar"><span className="mid" /><span className="seg" style={style} /></div>
            <span className="fval">{v >= 0 ? '+' : ''}{v.toFixed(3)} <span style={{ color: 'var(--muted)' }}>w{(f.weight ?? 0).toFixed(2)}</span></span>
          </div>
        )
      })}
    </div>
  )
}

export function EvidenceBars({ bars }) {
  if (!bars?.length) return <div className="note">No scored evidence yet.</div>
  return (
    <div>
      {bars.map((b) => (
        <div key={b.evidence} className={`evbar ${b.label === 'missing' ? 'missing' : ''}`}>
          <span className="label">{b.evidence}</span>
          <div className="track"><div className="fill" style={{ width: `${b.strength_pct}%` }} /></div>
          <span className="pct">{b.label === 'missing' ? 'missing' : `${b.strength_pct}%`}</span>
        </div>
      ))}
    </div>
  )
}

export function ProgressSteps({ steps }) {
  return (
    <div className="progress-steps">
      {steps.map((s) => (
        <div key={s.step} className={`st ${s.done ? 'done' : ''}`}>
          <div className="b" /><div className="t">{s.step.replace(/_/g, ' ')}</div>
        </div>
      ))}
    </div>
  )
}
