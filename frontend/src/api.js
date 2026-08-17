const j = (r) => {
  if (!r.ok) return r.json().then((b) => { throw new Error(b.detail || r.statusText) })
  return r.json()
}
const get = (u) => fetch(u).then(j)
const post = (u, body) =>
  fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' },
             body: body ? JSON.stringify(body) : undefined }).then(j)

export const api = {
  stats: () => get('/api/dashboard/stats'),
  accuracy: () => get('/api/dashboard/accuracy'),
  disputes: (params = '') => get('/api/disputes' + params),
  dispute: (id) => get(`/api/disputes/${id}`),
  view: (id, role) => get(`/api/disputes/${id}/view/${role}`),
  run: (id) => post(`/api/disputes/${id}/run`),
  file: (body) => post('/api/disputes', body),
  merchantResponse: (id, body) => post(`/api/disputes/${id}/merchant-response`, body),
  representment: (id, body) => post(`/api/disputes/${id}/representment`, body),
  analystOverride: (id, body) => post(`/api/disputes/${id}/analyst-override`, body),
  escalate: (id, body) => post(`/api/disputes/${id}/escalate`, body),
  taxonomy: () => get('/api/meta/taxonomy'),
  models: () => get('/api/meta/models'),
  demoCases: () => get('/api/demo/cases'),
  thresholds: () => get('/api/meta/thresholds'),
  imageUrl: (id, kind) => `/api/disputes/${id}/image/${kind}`,
}

export const ACTION_META = {
  auto_approve: { label: 'Approved for card member', tone: 'cm' },
  auto_deny: { label: 'Resolved for merchant', tone: 'mr' },
  represent_chargeback: { label: 'Merchant representment path', tone: 'mr' },
  escalate_to_analyst: { label: 'Escalated to analyst', tone: 'esc' },
  request_more_evidence: { label: 'More evidence requested', tone: 'info' },
}

export const STATE_LABEL = {
  filed: 'Filed', evidence_gathering: 'Gathering evidence',
  merchant_response_window: 'Merchant window', decision: 'Deciding',
  escalated: 'Escalated', resolved: 'Resolved', appealed: 'Appealed', final: 'Final',
}

export const STAGES = [
  ['graph_context', 'Knowledge graph'],
  ['classification', 'Classification'],
  ['evidence_mapping', 'Evidence mapping'],
  ['evidence_collection', 'Dynamic collection'],
  ['evidence_scoring', 'Evidence scoring'],
  ['integrity', 'Dispute integrity'],
  ['decision', 'Decision model'],
  ['compliance', 'Compliance rules'],
  ['action', 'Action'],
  ['feedback', 'Feedback loop'],
]

export const DEMO_BLURBS = {
  'D-DEMO-RAHUL': 'The worked example: cracked laptop (QD-01). Vision verifies damage, graph confirms delivery, refund auto-approved.',
  'D-DEMO-DUP': 'Two identical charges 90 seconds apart — the duplicate detector makes the case conclusive.',
  'D-DEMO-SUB': 'Subscription cancelled before renewal with a confirmation number — conclusive for the card member.',
  'D-DEMO-NORESP': 'Merchant response window expired — network rules resolve non-response as \u201cno proof provided\u201d.',
  'D-DEMO-CONFLICT': '\u201cNever arrived AND damaged on arrival\u201d — logically conflicting sub-claims put the case on hold.',
  'D-DEMO-VAGUE': 'Unclassifiable free text — the system requests clarification instead of guessing.',
  'D-DEMO-FRAUD': 'Frequent filer, shared device, filed one hour after purchase — integrity flags route to an analyst (never auto-deny).',
  'D-DEMO-MOOT': 'A refund already completed via UPI — the dispute is moot and closes for the merchant.',
}

export const DEMO_TITLES = {
  'D-DEMO-RAHUL': "Rahul's damaged laptop",
  'D-DEMO-DUP': 'Duplicate charge',
  'D-DEMO-SUB': 'Cancelled subscription billed',
  'D-DEMO-NORESP': 'Merchant never responded',
  'D-DEMO-CONFLICT': 'Conflicting claims',
  'D-DEMO-VAGUE': 'Vague description',
  'D-DEMO-FRAUD': 'Integrity flag (friendly fraud)',
  'D-DEMO-MOOT': 'Refund already issued',
}

export const fmtMoney = (v, c = 'INR') =>
  v == null ? '—' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: c, maximumFractionDigits: 0 }).format(v)

export const fmtDate = (s) => (s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
