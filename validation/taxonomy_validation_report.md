# Taxonomy Validation Report

Generated: 2026-08-10T21:00:34.559324+00:00  
Source workbook: `/home/claude/dispute-resolution/config/taxonomy_source/Dispute_codes.xlsx`

## 1. Counts

- **techdoc types**: 36
- **excel taxonomy sheet types**: 36
- **excel all internal codes**: 39
- **amex network codes**: 28
- **visa network codes**: 14
- **mc network codes**: 12

## 2. Taxonomy codes found in the technical document (36)

`AR-01`, `AR-02`, `AR-03`, `BA-01`, `BA-02`, `BA-03`, `BA-04`, `BA-05`, `BA-06`, `BA-07`, `BA-08`, `CR-01`, `CR-02`, `CR-03`, `CR-04`, `CR-05`, `CR-06`, `NR-01`, `NR-02`, `NR-03`, `NR-04`, `NR-05`, `QD-01`, `QD-02`, `QD-03`, `QD-04`, `QD-05`, `QD-06`, `SP-01`, `SP-02`, `SP-03`, `SP-04`, `SP-05`, `SP-06`, `SP-07`, `SP-08`


## 3. Taxonomy codes found in the Excel

`AR-01`, `AR-02`, `AR-03`, `AR-04`, `AR-05`, `BA-01`, `BA-02`, `BA-03`, `BA-04`, `BA-05`, `BA-06`, `BA-07`, `BA-08`, `BA-09`, `CR-01`, `CR-02`, `CR-03`, `CR-04`, `CR-05`, `CR-06`, `NR-01`, `NR-02`, `NR-03`, `NR-04`, `NR-05`, `QD-01`, `QD-02`, `QD-03`, `QD-04`, `QD-05`, `QD-06`, `SP-01`, `SP-02`, `SP-03`, `SP-04`, `SP-05`, `SP-06`, `SP-07`, `SP-08`


## 4. Codes present in BOTH sources

`AR-01`, `AR-02`, `AR-03`, `BA-01`, `BA-02`, `BA-03`, `BA-04`, `BA-05`, `BA-06`, `BA-07`, `BA-08`, `CR-01`, `CR-02`, `CR-03`, `CR-04`, `CR-05`, `CR-06`, `NR-01`, `NR-02`, `NR-03`, `NR-04`, `NR-05`, `QD-01`, `QD-02`, `QD-03`, `QD-04`, `QD-05`, `QD-06`, `SP-01`, `SP-02`, `SP-03`, `SP-04`, `SP-05`, `SP-06`, `SP-07`, `SP-08`


## 5. Codes present ONLY in the technical document

_None_


## 6. Codes present ONLY in the Excel

`AR-04`, `AR-05`, `BA-09`


These labels appear in the Amex mapping sheet but not in the 36-type technical-document taxonomy. Per instructions they are **preserved exactly as supplied** — not deleted, not renamed, not assumed to be errors. The registry represents them with `in_techdoc = false`.


## 7. Network reason codes

- **amex** (28): `4507`, `4512`, `4513`, `4515`, `4516`, `4517`, `4521`, `4523`, `4527`, `4530`, `4534`, `4536`, `4540`, `4544`, `4553`, `4554`, `4750`, `4752`, `4754`, `4755`, `4763`, `4798`, `6003`, `6006`, `6008`, `6013`, `6014`, `6016`
- **visa** (14): `10.1`, `11.1-11.3`, `12.1`, `12.3`, `12.5`, `12.6`, `13.1`, `13.2`, `13.3`, `13.4`, `13.5`, `13.6`, `13.7`, `13.9`
- **mastercard** (12): `4808`, `4831`, `4834`, `4837`, `4846`, `4850`, `4853`, `4855`, `4859`, `4860`, `4863`, `6321`

## 8. One-to-many mappings (one network code → many internal types)

- `amex 4513` (Credit Not Presented) → `BA-04`, `CR-01`, `SP-02`
- `amex 4544` (Cancellation Of Recurring Goods / Services) → `CR-03`, `CR-04`
- `amex 4553` (Not As Described Or Defective Merchandise) → `QD-01`, `QD-02`, `QD-03`, `QD-04`, `QD-05`, `QD-06`
- `amex 4554` (Goods And Services Not Received) → `NR-01`, `NR-02`, `NR-03`, `NR-04`, `NR-05`
- `visa 13.1` (n/a) → `NR-01`, `NR-02`, `NR-03`, `NR-04`, `NR-05`, `SP-03`
- `mastercard 4853` (n/a) → `NR-01`, `NR-04`, `QD-01`, `QD-02`, `QD-03`, `QD-04`, `QD-05`, `QD-06`, `BA-04`, `CR-01`, `CR-02`, `CR-03`, `CR-04`, `CR-05`, `CR-06`, `SP-01`, `SP-03`, `SP-04`, `SP-05`, `SP-06`, `SP-07`
- `mastercard 4855` (n/a) → `NR-01`, `NR-03`
- `visa 13.3` (n/a) → `QD-01`, `QD-02`, `QD-03`, `QD-05`, `QD-06`, `SP-02`
- `mastercard 4834` (n/a) → `BA-01`, `BA-05`
- `visa 12.5` (n/a) → `BA-02`, `BA-06`
- `mastercard 4831` (n/a) → `BA-02`, `BA-03`
- `visa 13.2` (n/a) → `BA-03`, `CR-03`, `CR-04`
- `visa 13.7` (n/a) → `CR-01`, `CR-02`, `CR-05`, `CR-06`, `SP-03`
- `mastercard 4859` (n/a) → `CR-05`, `SP-02`, `SP-08`
- `visa 13.5` (n/a) → `SP-04`, `SP-06`, `SP-07`

## 9. Many-to-one mappings (one internal type ← many network codes)

- `NR-01` ← `mastercard`: `4853`, `4855`
- `BA-01` ← `amex`: `4512`, `4534`
- `BA-04` ← `mastercard`: `4853`, `4860`
- `CR-05` ← `mastercard`: `4853`, `4859`
- `AR-01` ← `mastercard`: `4863`, `6321`
- `AR-02` ← `amex`: `4521`, `4755`
- `AR-03` ← `amex`: `4523`, `4527`
- `SP-03` ← `visa`: `13.1`, `13.7`

## 10. Unresolved discrepancies

### 10.1 Excel-only internal codes

`AR-04`, `AR-05`, `BA-09`


### 10.2 Amex codes with no internal-type mapping

- `Amex 4516` — Request For Support Not Fulfilled (Excel category: Process; field: 'N/A — escalation trigger') — handled as: Merchant failed to respond; auto-favor cardholder per network rules
- `Amex 4517` — Request For Support Illegible / Incomplete (Excel category: Process; field: 'N/A — escalation trigger') — handled as: Merchant provided insufficient docs; auto-favor cardholder per network rules
- `Amex 6003` — Retrieval Request: Issuer requires to validate claims (Excel category: Retrieval; field: 'blank') — handled as: Provide signed receipt, booking confirmation, or delivery proof
- `Amex 6006` — Retrieval Request: Legal Request or Fraud Analysis (Excel category: Retrieval; field: 'blank') — handled as: Provide itemized receipt, delivery proof, or legal records
- `Amex 6008` — Retrieval Request: Card Member requests copy bearing signature (Excel category: Retrieval; field: 'blank') — handled as: Provide signed receipt or policy details
- `Amex 6013` — Retrieval Request: Repeat Request (Excel category: Retrieval; field: 'blank') — handled as: Refer to original Retrieval Request documentation
- `Amex 6014` — Retrieval Request: Card Member does not recognise Transaction (Excel category: Retrieval; field: 'blank') — handled as: Provide signed receipt, delivery proof, or IP address
- `Amex 6016` — Retrieval Request: Card Member needs for personal records (Excel category: Retrieval; field: 'blank') — handled as: Provide itemized receipt or policy details

### 10.3 Tech-doc types with no Amex code in the Excel (TBD/N/A)

`BA-06`, `BA-07`, `CR-02`, `CR-05`, `CR-06`, `SP-03`, `SP-04`, `SP-05`, `SP-06`, `SP-08`


## 11. Resolution policy

Both taxonomies are preserved verbatim. The registry represents Excel-only internal codes (flagged in_techdoc=false) so the pipeline can process any Amex reason code in the workbook. Amex codes that map to no internal type (Process 4516/4517, Retrieval 6003-6016) are handled as escalation / retrieval triggers, not classifiable dispute categories. Types the Excel lists as 'TBD/N/A' for Amex still resolve on Visa/Mastercard and route to the closest Amex family code at filing time with an analyst note.

