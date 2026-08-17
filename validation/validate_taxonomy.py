"""Compares the technical-document taxonomy with the supplied Excel workbook
and writes /validation/taxonomy_validation_report.md.

Nothing is deleted, renamed, or assumed to be an error: discrepancies are
DOCUMENTED and the system remains capable of representing every mapping in
the Excel (the registry keeps Excel-only codes such as BA-09 / AR-04 / AR-05).

Run:  python -m validation.validate_taxonomy
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.taxonomy import techdoc
from backend.taxonomy.loader import load_excel_taxonomy
from backend.taxonomy.registry import get_registry

REPORT_MD = Path(__file__).resolve().parent / "taxonomy_validation_report.md"
REPORT_JSON = Path(__file__).resolve().parent / "taxonomy_validation_report.json"


def build_report() -> dict:
    excel = load_excel_taxonomy()
    reg = get_registry()

    techdoc_codes = set(techdoc.TECHDOC_CODES)
    excel_sheet_codes = set(excel["types"].keys())
    excel_mapping_refs = set()
    for m in excel["amex_mappings"]:
        excel_mapping_refs.update(m["internal_codes"])
    excel_all = excel_sheet_codes | excel_mapping_refs

    unmapped_network_codes = [
        {"network_code": m["network_code"], "description": m["network_description"],
         "excel_category": m["excel_category"], "raw_internal_field": m["raw_internal_field"],
         "resolution_approach": m["resolution_approach"]}
        for m in excel["amex_mappings"] if not m["internal_codes"]
    ]
    types_without_amex_code = sorted(
        c for c in techdoc_codes
        if c in excel["types"] and not excel["types"][c]["amex_codes"])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_excel": excel["source_file"],
        "counts": {
            "techdoc_types": len(techdoc_codes),
            "excel_taxonomy_sheet_types": len(excel_sheet_codes),
            "excel_all_internal_codes": len(excel_all),
            "amex_network_codes": len(excel["amex_mappings"]),
            "visa_network_codes": len([k for k in reg.network_codes if k[0] == "visa"]),
            "mc_network_codes": len([k for k in reg.network_codes if k[0] == "mastercard"]),
        },
        "codes_in_techdoc": sorted(techdoc_codes),
        "codes_in_excel": sorted(excel_all),
        "codes_in_both": sorted(techdoc_codes & excel_all),
        "codes_only_in_techdoc": sorted(techdoc_codes - excel_all),
        "codes_only_in_excel": sorted(excel_all - techdoc_codes),
        "network_reason_codes": {
            "amex": sorted({m["network_code"] for m in excel["amex_mappings"]}),
            "visa": sorted({k[1] for k in reg.network_codes if k[0] == "visa"}),
            "mastercard": sorted({k[1] for k in reg.network_codes if k[0] == "mastercard"}),
        },
        "one_to_many_mappings": reg.one_to_many(),
        "many_to_one_mappings": reg.many_to_one(),
        "unresolved_discrepancies": {
            "excel_only_internal_codes": sorted(excel_all - techdoc_codes),
            "amex_codes_with_no_internal_mapping": unmapped_network_codes,
            "techdoc_types_with_no_amex_code_in_excel": types_without_amex_code,
        },
        "resolution_policy": (
            "Both taxonomies are preserved verbatim. The registry represents "
            "Excel-only internal codes (flagged in_techdoc=false) so the "
            "pipeline can process any Amex reason code in the workbook. "
            "Amex codes that map to no internal type (Process 4516/4517, "
            "Retrieval 6003-6016) are handled as escalation / retrieval "
            "triggers, not classifiable dispute categories. Types the Excel "
            "lists as 'TBD/N/A' for Amex still resolve on Visa/Mastercard "
            "and route to the closest Amex family code at filing time with "
            "an analyst note."),
    }
    return report


def _md(report: dict) -> str:
    L = []
    L.append("# Taxonomy Validation Report\n")
    L.append(f"Generated: {report['generated_at']}  ")
    L.append(f"Source workbook: `{report['source_excel']}`\n")
    L.append("## 1. Counts\n")
    for k, v in report["counts"].items():
        L.append(f"- **{k.replace('_', ' ')}**: {v}")
    L.append("\n## 2. Taxonomy codes found in the technical document (36)\n")
    L.append(", ".join(f"`{c}`" for c in report["codes_in_techdoc"]))
    L.append("\n\n## 3. Taxonomy codes found in the Excel\n")
    L.append(", ".join(f"`{c}`" for c in report["codes_in_excel"]))
    L.append("\n\n## 4. Codes present in BOTH sources\n")
    L.append(", ".join(f"`{c}`" for c in report["codes_in_both"]))
    L.append("\n\n## 5. Codes present ONLY in the technical document\n")
    L.append(", ".join(f"`{c}`" for c in report["codes_only_in_techdoc"]) or "_None_")
    L.append("\n\n## 6. Codes present ONLY in the Excel\n")
    only_excel = report["codes_only_in_excel"]
    L.append(", ".join(f"`{c}`" for c in only_excel) or "_None_")
    if only_excel:
        L.append("\n\nThese labels appear in the Amex mapping sheet but not in the "
                 "36-type technical-document taxonomy. Per instructions they are "
                 "**preserved exactly as supplied** — not deleted, not renamed, "
                 "not assumed to be errors. The registry represents them with "
                 "`in_techdoc = false`.")
    L.append("\n\n## 7. Network reason codes\n")
    for net, codes in report["network_reason_codes"].items():
        L.append(f"- **{net}** ({len(codes)}): " + ", ".join(f"`{c}`" for c in codes))
    L.append("\n## 8. One-to-many mappings (one network code → many internal types)\n")
    for m in report["one_to_many_mappings"]:
        L.append(f"- `{m['network']} {m['network_code']}` "
                 f"({m['description'] or 'n/a'}) → "
                 + ", ".join(f"`{c}`" for c in m["internal_codes"]))
    L.append("\n## 9. Many-to-one mappings (one internal type ← many network codes)\n")
    for m in report["many_to_one_mappings"]:
        L.append(f"- `{m['internal_code']}` ← `{m['network']}`: "
                 + ", ".join(f"`{c}`" for c in m["network_codes"]))
    L.append("\n## 10. Unresolved discrepancies\n")
    ud = report["unresolved_discrepancies"]
    L.append("### 10.1 Excel-only internal codes\n")
    L.append(", ".join(f"`{c}`" for c in ud["excel_only_internal_codes"]) or "_None_")
    L.append("\n\n### 10.2 Amex codes with no internal-type mapping\n")
    for u in ud["amex_codes_with_no_internal_mapping"]:
        L.append(f"- `Amex {u['network_code']}` — {u['description']} "
                 f"(Excel category: {u['excel_category']}; field: "
                 f"'{u['raw_internal_field'] or 'blank'}') — handled as: "
                 f"{u['resolution_approach']}")
    L.append("\n### 10.3 Tech-doc types with no Amex code in the Excel (TBD/N/A)\n")
    L.append(", ".join(f"`{c}`" for c in ud["techdoc_types_with_no_amex_code_in_excel"]) or "_None_")
    L.append("\n\n## 11. Resolution policy\n")
    L.append(report["resolution_policy"])
    L.append("\n")
    return "\n".join(L)


def main() -> dict:
    report = build_report()
    REPORT_JSON.write_text(json.dumps(report, indent=2))
    REPORT_MD.write_text(_md(report))
    print(f"Taxonomy validation report written:\n  {REPORT_MD}\n  {REPORT_JSON}")
    print(f"  techdoc types: {report['counts']['techdoc_types']}, "
          f"excel internal codes: {report['counts']['excel_all_internal_codes']}, "
          f"only-in-excel: {report['codes_only_in_excel']}")
    return report


if __name__ == "__main__":
    main()
