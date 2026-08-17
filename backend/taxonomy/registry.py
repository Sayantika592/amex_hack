"""Runtime taxonomy registry.

Three concepts stay SEPARATE (never interchangeable), per the design brief:
  * InternalDisputeType  (NR-01, QD-01, ... plus Excel-only BA-09/AR-04/AR-05)
  * Network              (amex | visa | mastercard)
  * NetworkReasonCode    (Amex 4553, Visa 13.3, MC 4853, ...)

Flow:  description -> NLP -> InternalDisputeType -> network mapping ->
NetworkReasonCode -> network evidence rules -> decision engine.

Mappings are many-to-many: Amex 4553 covers QD-01..QD-06; BA-01 is reached by
Amex 4512 and 4534.  The Excel workbook is authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from backend.taxonomy import techdoc
from backend.taxonomy.loader import load_excel_taxonomy


@dataclass
class InternalDisputeType:
    code: str
    name: str
    label: str                      # zero-shot classifier label
    macro: str
    macro_name: str
    description: str = ""
    key_evidence: str = ""
    auto_fetch_sources: str = ""
    in_techdoc: bool = True
    in_excel: bool = True
    network_codes: dict = field(default_factory=lambda: {"amex": [], "visa": [], "mastercard": []})


@dataclass
class NetworkReasonCode:
    network: str
    code: str
    description: str
    internal_codes: list
    category: str = ""
    resolution_approach: str = ""


class TaxonomyRegistry:
    def __init__(self):
        excel = load_excel_taxonomy()
        self.types: dict[str, InternalDisputeType] = {}
        self.network_codes: dict[tuple[str, str], NetworkReasonCode] = {}

        # 1. every tech-doc type
        for code, label in techdoc.TECHDOC_TYPES:
            ex = excel["types"].get(code, {})
            self.types[code] = InternalDisputeType(
                code=code,
                name=ex.get("name", label),
                label=label,
                macro=techdoc.macro_of(code),
                macro_name=techdoc.MACRO_CATEGORIES[techdoc.macro_of(code)],
                description=ex.get("description", ""),
                key_evidence=ex.get("key_evidence", ""),
                auto_fetch_sources=ex.get("auto_fetch_sources", ""),
                in_techdoc=True,
                in_excel=code in excel["types"],
                network_codes={
                    "amex": list(ex.get("amex_codes", [])),
                    "visa": list(ex.get("visa_codes", [])),
                    "mastercard": list(ex.get("mc_codes", [])),
                },
            )

        # 2. Excel-only internal codes referenced in the Amex mapping sheet
        #    (e.g. BA-09, AR-04, AR-05) — preserved, never deleted or renamed.
        for m in excel["amex_mappings"]:
            for ic in m["internal_codes"]:
                if ic not in self.types:
                    macro = ic.split("-")[0]
                    self.types[ic] = InternalDisputeType(
                        code=ic,
                        name=f"{m['network_description']} (Excel-only mapping)",
                        label=m["network_description"],
                        macro=macro,
                        macro_name=techdoc.MACRO_CATEGORIES.get(macro, m["excel_category"]),
                        description=f"Internal label present only in the Excel "
                                    f"mapping sheet (Amex {m['network_code']}: "
                                    f"{m['network_description']}).",
                        in_techdoc=False,
                        in_excel=True,
                    )
                if m["network_code"] not in self.types[ic].network_codes["amex"]:
                    self.types[ic].network_codes["amex"].append(m["network_code"])

        # 3. NetworkReasonCode objects — Amex from the mapping sheet
        for m in excel["amex_mappings"]:
            self.network_codes[("amex", m["network_code"])] = NetworkReasonCode(
                network="amex", code=m["network_code"],
                description=m["network_description"],
                internal_codes=list(m["internal_codes"]),
                category=m["excel_category"],
                resolution_approach=m["resolution_approach"],
            )
        #    Visa / Mastercard from the taxonomy sheet columns
        for t in excel["types"].values():
            for net, key in (("visa", "visa_codes"), ("mastercard", "mc_codes")):
                for nc in t[key]:
                    k = (net, nc)
                    if k not in self.network_codes:
                        self.network_codes[k] = NetworkReasonCode(
                            network=net, code=nc, description="", internal_codes=[])
                    if t["code"] not in self.network_codes[k].internal_codes:
                        self.network_codes[k].internal_codes.append(t["code"])

    # ------------------------------------------------------------------ API
    def get(self, code: str) -> InternalDisputeType | None:
        return self.types.get(code)

    def all_codes(self) -> list[str]:
        return list(self.types.keys())

    def techdoc_codes(self) -> list[str]:
        return [c for c, t in self.types.items() if t.in_techdoc]

    def labels(self) -> list[str]:
        """36 zero-shot labels in tech-doc order (classifier candidate set)."""
        return [techdoc.CODE_TO_LABEL[c] for c in techdoc.TECHDOC_CODES]

    def label_to_code(self, label: str) -> str | None:
        return techdoc.LABEL_TO_CODE.get(label)

    def network_codes_for(self, internal_code: str, network: str) -> list[str]:
        t = self.types.get(internal_code)
        return list(t.network_codes.get(network, [])) if t else []

    def internal_codes_for(self, network: str, network_code: str) -> list[str]:
        rc = self.network_codes.get((network, str(network_code)))
        return list(rc.internal_codes) if rc else []

    def reason_code(self, network: str, network_code: str) -> NetworkReasonCode | None:
        return self.network_codes.get((network, str(network_code)))

    def one_to_many(self) -> list[dict]:
        return [
            {"network": rc.network, "network_code": rc.code,
             "internal_codes": rc.internal_codes, "description": rc.description}
            for rc in self.network_codes.values() if len(rc.internal_codes) > 1
        ]

    def many_to_one(self) -> list[dict]:
        out = []
        for code, t in self.types.items():
            for net, codes in t.network_codes.items():
                if len(codes) > 1:
                    out.append({"internal_code": code, "network": net,
                                "network_codes": codes})
        return out


@lru_cache(maxsize=1)
def get_registry() -> TaxonomyRegistry:
    return TaxonomyRegistry()
