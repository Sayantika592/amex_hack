"""ORM models.

Mirrors the Layer-0 knowledge-graph schema (Transaction, Cardholder, Merchant,
Device, Shipment, Dispute, Refund, Policy) plus operational tables.  The
taxonomy tables keep InternalDisputeType and NetworkReasonCode as SEPARATE
concepts joined through CodeMapping (many-to-many), exactly as the design
brief requires.

NOTE ON GROUND TRUTH: synthetic ground truth lives ONLY in
data/generated/ground_truth.csv and is never loaded into these tables — the
application cannot read it when making production-style decisions.
"""
import json
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, String, Text)
from sqlalchemy.orm import relationship

from backend.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ----------------------------------------------------------- taxonomy tables
class InternalDisputeTypeRow(Base):
    __tablename__ = "internal_dispute_types"
    code = Column(String, primary_key=True)          # NR-01 ... BA-09
    name = Column(String)
    label = Column(String)                           # zero-shot label
    macro = Column(String)
    macro_name = Column(String)
    description = Column(Text)
    in_techdoc = Column(Boolean, default=True)
    in_excel = Column(Boolean, default=True)


class NetworkReasonCodeRow(Base):
    __tablename__ = "network_reason_codes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    network = Column(String, index=True)             # amex | visa | mastercard
    code = Column(String, index=True)                # 4553 / 13.3 / 4853
    description = Column(Text)
    category = Column(String)
    resolution_approach = Column(Text)


class CodeMapping(Base):
    """Many-to-many bridge: NEVER assume one-to-one."""
    __tablename__ = "code_mappings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    internal_code = Column(String, ForeignKey("internal_dispute_types.code"), index=True)
    network = Column(String, index=True)
    network_code = Column(String, index=True)


# ------------------------------------------------------------- graph entities
class CardMember(Base):
    __tablename__ = "card_members"
    id = Column(String, primary_key=True)
    name = Column(String)
    tenure_years = Column(Float)
    card_tier = Column(String)                       # blinded from decisioning
    billing_zip = Column(String)
    billing_city = Column(String)
    email = Column(String)
    dispute_count = Column(Integer, default=0)
    demographic_note = Column(String, default="")    # blinded from decisioning


class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(String, primary_key=True)
    name = Column(String)
    dba_name = Column(String)
    mcc = Column(String)
    category = Column(String)
    size = Column(String)                            # small|mid|large (blinded)
    dispute_rate = Column(Float, default=0.0)
    dispute_loss_rate = Column(Float, default=0.0)
    avg_resolution_days = Column(Float, default=0.0)
    country = Column(String, default="IN")


class Device(Base):
    __tablename__ = "devices"
    id = Column(String, primary_key=True)
    fingerprint = Column(String)
    ip_geo = Column(String)
    user_agent = Column(String)
    linked_cardholders = Column(Integer, default=1)


class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True)
    name = Column(String)
    category = Column(String)
    price = Column(Float)
    listing_image_ref = Column(String)
    description = Column(Text)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String, primary_key=True)
    card_member_id = Column(String, ForeignKey("card_members.id"), index=True)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True)
    device_id = Column(String, ForeignKey("devices.id"), nullable=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=True)
    amount = Column(Float)
    currency = Column(String, default="INR")
    timestamp = Column(DateTime(timezone=True))
    mcc = Column(String)
    status = Column(String, default="settled")
    channel = Column(String, default="ecommerce")    # ecommerce|card_present|recurring|atm
    network = Column(String, default="amex")
    descriptor = Column(String)

    card_member = relationship("CardMember")
    merchant = relationship("Merchant")


class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(String, primary_key=True)
    transaction_id = Column(String, ForeignKey("transactions.id"), index=True)
    carrier = Column(String)
    tracking_number = Column(String)
    status = Column(String)                          # delivered|in_transit|lost|returned|none
    ship_date = Column(DateTime(timezone=True), nullable=True)
    delivery_date = Column(DateTime(timezone=True), nullable=True)
    delivery_zip = Column(String, nullable=True)
    signature_on_file = Column(Boolean, default=False)
    delivery_photo = Column(Boolean, default=False)
    gps_coordinates = Column(String, nullable=True)


class Policy(Base):
    __tablename__ = "policies"
    id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True)
    type = Column(String)                            # return|cancellation|warranty|no_show
    return_window_days = Column(Integer, nullable=True)
    terms = Column(Text)


class Refund(Base):
    __tablename__ = "refunds"
    id = Column(String, primary_key=True)
    transaction_id = Column(String, ForeignKey("transactions.id"), index=True)
    merchant_id = Column(String, ForeignKey("merchants.id"))
    amount = Column(Float)
    status = Column(String)                          # completed|initiated|promised|none
    initiated_date = Column(DateTime(timezone=True), nullable=True)
    completed_date = Column(DateTime(timezone=True), nullable=True)
    channel = Column(String, default="card")


class Dispute(Base):
    __tablename__ = "disputes"
    id = Column(String, primary_key=True)
    transaction_id = Column(String, ForeignKey("transactions.id"), index=True)
    card_member_id = Column(String, ForeignKey("card_members.id"), index=True)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True)
    network = Column(String, default="amex")
    user_selected_code = Column(String)              # dropdown selection
    description = Column(Text)                       # free text
    filed_date = Column(DateTime(timezone=True))
    state = Column(String, default="filed")          # lifecycle state machine
    classified_code = Column(String, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    network_reason_codes = Column(JSON, default=list)
    outcome = Column(String, nullable=True)          # favor_cardholder|favor_merchant|inconclusive
    action = Column(String, nullable=True)
    final_score = Column(Float, nullable=True)
    resolved_date = Column(DateTime(timezone=True), nullable=True)
    merchant_notified_date = Column(DateTime(timezone=True), nullable=True)
    merchant_responded = Column(Boolean, default=False)
    is_historical = Column(Boolean, default=False)   # pre-existing history for graph signals
    amount = Column(Float)
    currency = Column(String, default="INR")

    transaction = relationship("Transaction")
    card_member = relationship("CardMember")
    merchant = relationship("Merchant")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id = Column(String, primary_key=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), index=True)
    evidence_type = Column(String, index=True)
    source_party = Column(String)                    # system|cardholder|merchant
    payload = Column(JSON)
    collected_at = Column(DateTime(timezone=True), default=utcnow)
    dated = Column(Boolean, default=True)
    age_days = Column(Float, default=0.0)


class MerchantResponse(Base):
    __tablename__ = "merchant_responses"
    id = Column(String, primary_key=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), index=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    response_type = Column(String)                   # accept|contest|no_response
    statement = Column(Text)
    evidence_refs = Column(JSON, default=list)
    is_representment = Column(Boolean, default=False)


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(String, primary_key=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), index=True)
    decided_at = Column(DateTime(timezone=True), default=utcnow)
    final_score = Column(Float)
    outcome = Column(String)
    action = Column(String)
    confidence = Column(Float)
    factor_breakdown = Column(JSON)
    compliance = Column(JSON)
    integrity = Column(JSON)
    burden = Column(JSON)
    explanation = Column(JSON)
    decided_by = Column(String, default="system")    # system|analyst
    is_representment = Column(Boolean, default=False)


class PipelineRun(Base):
    """Machine-readable record of every pipeline stage for a dispute run —
    the frontend visualizes THIS, not fake animations."""
    __tablename__ = "pipeline_runs"
    id = Column(String, primary_key=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), index=True)
    started_at = Column(DateTime(timezone=True), default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    stages = Column(JSON)                            # {classification: {...}, ...}
    trigger = Column(String, default="filing")       # filing|representment|api|evaluation


class AnalystAction(Base):
    __tablename__ = "analyst_actions"
    id = Column(String, primary_key=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), index=True)
    analyst_id = Column(String, default="analyst-demo")
    action = Column(String)                          # accept|modify|override
    new_outcome = Column(String, nullable=True)
    reason = Column(Text)                            # feeds the learning loop
    created_at = Column(DateTime(timezone=True), default=utcnow)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    id = Column(String, primary_key=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), index=True)
    signal_type = Column(String)   # issuer_decision|representment_result|analyst_override|cardholder_escalation|resolution_time
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=utcnow)


def to_dict(obj):
    d = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        d[c.name] = v
    return d


def dumps(obj):
    return json.dumps(to_dict(obj), default=str)
