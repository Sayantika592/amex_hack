"""Layer 0 — Knowledge Graph foundation.

Entities (card member, merchant, transaction, device, shipment, refund,
dispute, policy) and their relationships become queryable signals that can
flip an outcome:
  * a refund already issued through another channel  -> dispute is moot
  * one card member, many same-category disputes     -> integrity flag
  * merchant losing most disputes                    -> tips toward card member
  * delivery to an address used many times before    -> strengthens delivery

GRAPH_MODE=memory  -> MemoryGraph, a relationship-query facade over the
                      relational store (zero infrastructure, same contract)
GRAPH_MODE=neo4j   -> Neo4jGraph, real Cypher (TDD §3 queries verbatim)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from backend.config import settings


class GraphBackend(ABC):
    name = "base"
    mode = "memory"

    @abstractmethod
    def get_dispute_context(self, dispute_id: str) -> dict: ...

    @abstractmethod
    def get_merchant_dispute_rate(self, merchant_id: str) -> float: ...

    @abstractmethod
    def get_cardholder_pattern(self, card_member_id: str,
                               exclude_dispute_id: str | None = None) -> list[dict]: ...


class MemoryGraph(GraphBackend):
    """Relationship queries over the relational store."""
    name = "MemoryGraph (DB-backed relationship queries)"
    mode = "memory"

    def __init__(self):
        # imported lazily so the module is importable without a DB
        from backend.db.database import SessionLocal
        self.SessionLocal = SessionLocal

    def get_merchant_dispute_rate(self, merchant_id: str) -> float:
        from backend.db import models as m
        with self.SessionLocal() as db:
            txns = db.query(m.Transaction).filter_by(merchant_id=merchant_id).count()
            disputes = db.query(m.Dispute).filter_by(merchant_id=merchant_id).count()
            return round(disputes / txns, 4) if txns else 0.0

    def get_cardholder_pattern(self, card_member_id, exclude_dispute_id=None):
        from backend.db import models as m
        with self.SessionLocal() as db:
            q = (db.query(m.Dispute)
                   .filter(m.Dispute.card_member_id == card_member_id))
            if exclude_dispute_id:
                q = q.filter(m.Dispute.id != exclude_dispute_id)
            rows = q.order_by(m.Dispute.filed_date.desc()).limit(20).all()
            return [{"dispute_id": d.id,
                     "category": d.classified_code or d.user_selected_code,
                     "outcome": d.outcome, "filed_date":
                     d.filed_date.isoformat() if d.filed_date else None}
                    for d in rows]

    def get_dispute_context(self, dispute_id: str) -> dict:
        from backend.db import models as m
        with self.SessionLocal() as db:
            d = db.get(m.Dispute, dispute_id)
            if not d:
                return {"error": f"dispute {dispute_id} not found"}
            txn = db.get(m.Transaction, d.transaction_id) if d.transaction_id else None
            ch = db.get(m.CardMember, d.card_member_id)
            mer = db.get(m.Merchant, d.merchant_id)
            dev = db.get(m.Device, txn.device_id) if txn and txn.device_id else None
            shp = (db.query(m.Shipment).filter_by(transaction_id=txn.id).first()
                   if txn else None)
            pol = (db.query(m.Policy).filter_by(merchant_id=mer.id, type="return").first()
                   if mer else None)
            refund = (db.query(m.Refund).filter_by(transaction_id=txn.id)
                        .order_by(m.Refund.initiated_date.desc()).first() if txn else None)

            prior = self.get_cardholder_pattern(d.card_member_id, exclude_dispute_id=d.id)
            merchant_txn_ct = db.query(m.Transaction).filter_by(merchant_id=d.merchant_id).count()
            merchant_dsp_ct = (db.query(m.Dispute).filter(
                m.Dispute.merchant_id == d.merchant_id, m.Dispute.id != d.id).count())
            merchant_losses = db.query(m.Dispute).filter(
                m.Dispute.merchant_id == d.merchant_id,
                m.Dispute.outcome == "favor_cardholder", m.Dispute.id != d.id).count()
            resolved = db.query(m.Dispute).filter(
                m.Dispute.merchant_id == d.merchant_id,
                m.Dispute.outcome.isnot(None), m.Dispute.id != d.id).count()

            # address familiarity: delivered shipments to this card member's zip
            addr_deliveries = 0
            if ch and ch.billing_zip:
                addr_deliveries = (db.query(m.Shipment)
                    .join(m.Transaction, m.Shipment.transaction_id == m.Transaction.id)
                    .filter(m.Transaction.card_member_id == ch.id,
                            m.Shipment.delivery_zip == ch.billing_zip,
                            m.Shipment.status == "delivered").count())

            # same product reported damaged by other card members (pattern signal)
            same_product_damage = 0
            if txn and txn.product_id:
                same_product_damage = (db.query(m.Dispute)
                    .join(m.Transaction, m.Dispute.transaction_id == m.Transaction.id)
                    .filter(m.Transaction.product_id == txn.product_id,
                            m.Dispute.id != d.id,
                            m.Dispute.classified_code.in_(["QD-01", "QD-02"])).count())

            same_cat = sum(1 for p in prior
                           if p["category"] and d.user_selected_code and
                           p["category"].split("-")[0] == d.user_selected_code.split("-")[0])

            return {
                "dispute_id": d.id,
                "transaction": {
                    "id": txn.id, "amount": txn.amount, "currency": txn.currency,
                    "timestamp": txn.timestamp.isoformat() if txn.timestamp else None,
                    "mcc": txn.mcc, "channel": txn.channel, "network": txn.network,
                    "descriptor": txn.descriptor, "product_id": txn.product_id,
                } if txn else None,
                "cardholder": {
                    "id": ch.id, "tenure_years": ch.tenure_years,
                    "billing_zip": ch.billing_zip,
                    "prior_dispute_count": len(prior),
                } if ch else None,
                "merchant": {
                    "id": mer.id, "name": mer.name, "mcc": mer.mcc,
                    "category": mer.category,
                } if mer else None,
                "device": {
                    "id": dev.id, "linked_cardholders": dev.linked_cardholders,
                    "ip_geo": dev.ip_geo,
                } if dev else {},
                "shipment": {
                    "id": shp.id, "carrier": shp.carrier, "status": shp.status,
                    "tracking_number": shp.tracking_number,
                    "delivery_zip": shp.delivery_zip,
                    "signature_on_file": shp.signature_on_file,
                    "delivery_date": shp.delivery_date.isoformat() if shp.delivery_date else None,
                } if shp else None,
                "return_policy": {
                    "return_window_days": pol.return_window_days, "terms": pol.terms,
                } if pol else None,
                "existing_refund": {
                    "id": refund.id, "amount": refund.amount, "status": refund.status,
                    "channel": refund.channel,
                } if refund else None,
                "prior_disputes": prior,
                "prior_same_macro_category": same_cat,
                "merchant_dispute_ct": merchant_dsp_ct,
                "merchant_transaction_ct": merchant_txn_ct,
                "merchant_dispute_rate": round(merchant_dsp_ct / merchant_txn_ct, 4)
                                         if merchant_txn_ct else 0.0,
                "merchant_loss_rate": round(merchant_losses / resolved, 3) if resolved else 0.0,
                "address_familiarity_deliveries": addr_deliveries,
                "same_product_damage_reports": same_product_damage,
                "graph_backend": self.name,
            }


class Neo4jGraph(GraphBackend):
    """Real Neo4j implementation — Cypher queries from TDD §3.
    Requires `pip install neo4j` and a reachable Neo4j instance
    (docker compose --profile neo4j up)."""
    name = "Neo4j"
    mode = "neo4j"

    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def get_dispute_context(self, dispute_id: str) -> dict:
        with self.driver.session() as session:
            rec = session.run(
                """
                MATCH (dsp:Dispute {id: $did})-[:ON_TRANSACTION]->(t:Transaction)
                OPTIONAL MATCH (t)-[:HAS_CARDHOLDER]->(c)
                OPTIONAL MATCH (t)-[:HAS_MERCHANT]->(m)
                OPTIONAL MATCH (t)-[:HAS_SHIPMENT]->(s)
                OPTIONAL MATCH (t)-[:USED_DEVICE]->(d)
                OPTIONAL MATCH (c)-[:FILED_DISPUTE]->(pd) WHERE pd.id <> $did
                OPTIONAL MATCH (m)-[:HAS_RETURN_POLICY]->(rp)
                OPTIONAL MATCH (m)<-[:AGAINST_MERCHANT]-(md) WHERE md.id <> $did
                RETURN t, c, m, s, d,
                       collect(DISTINCT pd) AS prior_disputes,
                       rp,
                       count(DISTINCT md) AS merchant_dispute_ct
                """, did=dispute_id).single()
            if rec is None:
                return {"error": f"dispute {dispute_id} not found in graph"}
            out = {k: (dict(rec[k]) if rec[k] is not None and k not in
                       ("prior_disputes", "merchant_dispute_ct") else rec[k])
                   for k in rec.keys()}
            out["prior_disputes"] = [dict(p) for p in rec["prior_disputes"]]
            out["graph_backend"] = self.name
            return out

    def get_merchant_dispute_rate(self, merchant_id: str) -> float:
        with self.driver.session() as session:
            rec = session.run(
                """
                MATCH (m:Merchant {id: $mid})<-[:HAS_MERCHANT]-(t:Transaction)
                OPTIONAL MATCH (t)<-[:ON_TRANSACTION]-(d:Dispute)
                RETURN toFloat(count(d))/count(t) AS dispute_rate
                """, mid=merchant_id).single()
            return float(rec["dispute_rate"] or 0.0)

    def get_cardholder_pattern(self, card_member_id, exclude_dispute_id=None):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (c:Cardholder {id: $cid})-[:FILED_DISPUTE]->(d:Dispute)
                WHERE $skip IS NULL OR d.id <> $skip
                RETURN d.id AS dispute_id, d.category AS category,
                       d.outcome AS outcome, d.filed_date AS filed_date
                ORDER BY d.filed_date DESC LIMIT 20
                """, cid=card_member_id, skip=exclude_dispute_id)
            return [r.data() for r in result]


_warning = None


@lru_cache(maxsize=1)
def get_graph() -> GraphBackend:
    global _warning
    if settings.graph_mode == "neo4j":
        try:
            return Neo4jGraph(settings.neo4j_uri, settings.neo4j_user,
                              settings.neo4j_password)
        except Exception as exc:
            _warning = f"Neo4j unavailable ({exc}); using MemoryGraph."
            print(f"[graph] WARNING: {_warning}")
    return MemoryGraph()


def graph_info():
    g = get_graph()
    return {"component": "knowledge_graph", "requested_mode": settings.graph_mode,
            "model": g.name, "mode": g.mode, "fallback_warning": _warning}
