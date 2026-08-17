"""The internal dispute taxonomy EXACTLY as described by the Technical Design
Document (36 types across 6 macro-categories).

This module is intentionally independent of the Excel workbook.  The Excel is
the authoritative source for network-code mappings; this file is the
authoritative record of what the technical document says.  validation/
validate_taxonomy.py compares the two and reports discrepancies — neither
source is ever silently altered.
"""

MACRO_CATEGORIES = {
    "NR": "Non-Receipt & Delivery",
    "QD": "Quality & Description",
    "BA": "Billing & Amount",
    "CR": "Cancellation & Returns",
    "AR": "Authorization & Recognition",
    "SP": "Special & Industry-Specific",
}

# (code, canonical zero-shot label from the TDD classifier label list)
TECHDOC_TYPES = [
    ("NR-01", "Goods not received"),
    ("NR-02", "Goods partially received"),
    ("NR-03", "Services not rendered"),
    ("NR-04", "Digital goods not delivered"),
    ("NR-05", "Late delivery"),
    ("QD-01", "Goods damaged on arrival"),
    ("QD-02", "Goods defective"),
    ("QD-03", "Goods not as described"),
    ("QD-04", "Counterfeit goods"),
    ("QD-05", "Wrong item sent"),
    ("QD-06", "Quality unacceptable"),
    ("BA-01", "Duplicate charge"),
    ("BA-02", "Incorrect amount"),
    ("BA-03", "Paid by other means"),
    ("BA-04", "Refund not processed"),
    ("BA-05", "Credit posted as charge"),
    ("BA-06", "Charge exceeds authorization"),
    ("BA-07", "Installment billing dispute"),
    ("BA-08", "Currency conversion dispute"),
    ("CR-01", "Goods returned no refund"),
    ("CR-02", "Order cancelled still charged"),
    ("CR-03", "Cancelled recurring subscription"),
    ("CR-04", "Free trial to paid without consent"),
    ("CR-05", "Hotel no-show"),
    ("CR-06", "Goods refused at delivery"),
    ("AR-01", "Unrecognized charge"),
    ("AR-02", "Authorization not obtained"),
    ("AR-03", "Card-present transaction not recognized"),
    ("SP-01", "Vehicle rental dispute"),
    ("SP-02", "Hotel incidental charges"),
    ("SP-03", "Airline travel dispute"),
    ("SP-04", "Timeshare dispute"),
    ("SP-05", "Insurance covered charge"),
    ("SP-06", "Promotional terms dispute"),
    ("SP-07", "Misrepresentation"),
    ("SP-08", "ATM dispute"),
]

TECHDOC_CODES = [c for c, _ in TECHDOC_TYPES]
CODE_TO_LABEL = dict(TECHDOC_TYPES)
LABEL_TO_CODE = {l: c for c, l in TECHDOC_TYPES}

assert len(TECHDOC_CODES) == 36, "Technical document defines exactly 36 types"


def macro_of(code: str) -> str:
    return code.split("-")[0]
