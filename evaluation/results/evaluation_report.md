# Evaluation Report

Generated: 2026-08-10T21:27:02.549296+00:00  
Disputes evaluated: **7000** (pipeline errors: 0)

> All data is synthetic. Accuracy claims are mechanism-level, not real-world (per the design document's data & evaluation plan).

## Classification (Layer 1)
- Accuracy on clear descriptions: **98.8%** (6437 cases)
- Vague descriptions correctly flagged for review: 563/563

## Decisions (Layers 4–8)
- Verdicts: {'deferred': 2867, 'correct': 4108, 'wrong': 25}
- Accuracy when decisive: **99.4%**
- Accuracy including deferrals as neither: 58.7%
- Deferral (escalate / request-evidence) rate: 41.0% — deliberate cost-asymmetric behaviour: uncertain cases defer to humans instead of auto-denying
- Auto-resolution rate: **41.7%**
- Action mix: {'escalate_to_analyst': 1947, 'request_more_evidence': 2134, 'auto_approve': 2319, 'represent_chargeback': 516, 'auto_deny': 84}

## Dispute Integrity (Layer 5, advisory only)
- Friendly-fraud suspects in ground truth: 424
- Flagged or escalated: 424 (detection rate 100.0%)
- No flagged case is ever auto-denied — flags route to an analyst.

## Fairness — counterfactual identity swap
- Sample re-run with swapped identity attributes: 200
- Outcomes changed: 0
- **Invariance rate: 100.0%**

## Timing
- Mean pipeline time per dispute: 0.026s (p95: 0.043s)

## Per-category verdicts

| Category | Correct | Deferred | Wrong |
|---|---|---|---|
| AR-01 | 75 | 146 | 0 |
| AR-02 | 41 | 133 | 0 |
| AR-03 | 34 | 74 | 0 |
| BA-01 | 451 | 54 | 0 |
| BA-02 | 230 | 31 | 0 |
| BA-03 | 32 | 78 | 0 |
| BA-04 | 333 | 28 | 0 |
| BA-05 | 46 | 19 | 0 |
| BA-06 | 99 | 15 | 0 |
| BA-07 | 99 | 12 | 0 |
| BA-08 | 39 | 83 | 0 |
| CR-01 | 192 | 127 | 0 |
| CR-02 | 187 | 23 | 0 |
| CR-03 | 337 | 47 | 0 |
| CR-04 | 81 | 168 | 0 |
| CR-05 | 51 | 74 | 0 |
| CR-06 | 66 | 57 | 0 |
| NR-01 | 328 | 247 | 0 |
| NR-02 | 166 | 18 | 0 |
| NR-03 | 54 | 129 | 0 |
| NR-04 | 153 | 24 | 0 |
| NR-05 | 61 | 62 | 0 |
| QD-01 | 326 | 168 | 19 |
| QD-02 | 60 | 170 | 0 |
| QD-03 | 87 | 219 | 0 |
| QD-04 | 44 | 97 | 0 |
| QD-05 | 114 | 66 | 0 |
| QD-06 | 28 | 83 | 6 |
| SP-01 | 40 | 76 | 0 |
| SP-02 | 30 | 80 | 0 |
| SP-03 | 32 | 92 | 0 |
| SP-04 | 23 | 36 | 0 |
| SP-05 | 26 | 35 | 0 |
| SP-06 | 20 | 41 | 0 |
| SP-07 | 17 | 42 | 0 |
| SP-08 | 106 | 13 | 0 |
