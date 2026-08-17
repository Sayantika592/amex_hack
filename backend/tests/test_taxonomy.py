"""Taxonomy registry: 36 tech-doc types + Excel-only codes preserved,
network reason codes kept as a separate concept (never one-to-one)."""
from backend.taxonomy.registry import get_registry


def test_registry_loads_all_codes():
    reg = get_registry()
    codes = set(reg.all_codes())
    assert len(codes) >= 36
    # spot-check every macro family from the tech doc
    for c in ("NR-01", "QD-01", "BA-01", "CR-03", "AR-01", "SP-08"):
        assert c in codes, c


def test_excel_only_codes_preserved_not_deleted():
    """claude_prompt.txt: BA-09 / AR-04 / AR-05 appear only in the Excel and
    must be preserved, not silently dropped or renamed."""
    reg = get_registry()
    codes = set(reg.all_codes())
    extra = {"BA-09", "AR-04", "AR-05"} & codes
    assert extra == {"BA-09", "AR-04", "AR-05"}
    for c in extra:
        t = reg.get(c)
        assert t.in_excel and not t.in_techdoc, (c, t.in_excel, t.in_techdoc)


def test_network_codes_are_separate_concept():
    """One internal type can map to multiple network codes and vice versa."""
    reg = get_registry()
    qd01 = reg.get("QD-01")
    assert qd01 is not None
    assert isinstance(qd01.network_codes, dict)
    # amex mapping exists for QD-01 per the supplied Excel
    assert qd01.network_codes.get("amex"), "QD-01 must map to >=1 Amex code"
    # at least one network code is shared by multiple internal types
    seen = {}
    shared = False
    for code in reg.all_codes():
        t = reg.get(code)
        for net, ncodes in (t.network_codes or {}).items():
            for nc in ncodes:
                key = (net, nc)
                if key in seen and seen[key] != code:
                    shared = True
                seen[key] = code
    assert shared, "expected at least one many-to-one network-code mapping"


def test_get_unknown_code_returns_none():
    assert get_registry().get("ZZ-99") is None
