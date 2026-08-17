"""Materializes the two large configuration files so compliance/product teams
can edit them directly without touching code:

  * config/evidence_matrix.yaml — Layer 2 network-specific evidence mapping
  * config/weights.yaml         — Layer 6 weight profiles (from the Excel
                                  'Evidence Weight matrix' sheet, authoritative)
                                  + the internal-type -> profile assignment

Run:  python scripts/build_configs.py     (idempotent; committed output)
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.taxonomy.loader import load_excel_taxonomy          # noqa: E402
from backend.taxonomy.registry import get_registry               # noqa: E402

# --------------------------------------------------------------------------
# Layer 2 evidence matrix. required is per-network; optional / party requests
# shared. Evidence type names match the collector registry & strength config.
# --------------------------------------------------------------------------
M = {}

def entry(code, amex, visa, mc, optional, ch_req, m_req):
    M[code] = {
        "required": {"amex": amex, "visa": visa, "mastercard": mc},
        "optional": optional,
        "cardholder_requested": ch_req,
        "merchant_requested": m_req,
    }

# ---- Non-Receipt & Delivery ----------------------------------------------
entry("NR-01",
      ["shipping_tracking", "delivery_confirmation", "cardholder_address_verification"],
      ["shipping_tracking", "delivery_confirmation", "signed_proof_of_delivery"],
      ["shipping_tracking", "delivery_confirmation", "carrier_damage_claim"],
      ["merchant_fulfillment_status", "gps_delivery_coordinates"],
      ["confirm_delivery_address"],
      ["proof_of_shipment", "carrier_details"])
entry("NR-02",
      ["shipping_tracking", "merchant_fulfillment_status", "receipt_data"],
      ["shipping_tracking", "merchant_fulfillment_status", "receipt_data"],
      ["shipping_tracking", "merchant_fulfillment_status", "receipt_data"],
      ["packaging_photos", "delivery_confirmation"],
      ["list_missing_items"],
      ["pick_pack_records", "shipment_weight"])
entry("NR-03",
      ["service_appointment_records", "communication_thread", "receipt_data"],
      ["service_appointment_records", "attendance_logs", "receipt_data"],
      ["service_appointment_records", "communication_thread", "receipt_data"],
      ["booking_confirmation"],
      ["describe_service_expected"],
      ["service_completion_confirmation", "provider_logs"])
entry("NR-04",
      ["digital_access_logs", "download_delivery_logs", "order_confirmation_email"],
      ["digital_access_logs", "download_delivery_logs", "account_provisioning_records"],
      ["digital_access_logs", "download_delivery_logs", "order_confirmation_email"],
      ["login_ip_device_data"],
      ["confirm_account_email"],
      ["license_key_records", "provisioning_timestamps"])
entry("NR-05",
      ["order_confirmation_email", "shipping_tracking", "merchant_terms_of_service"],
      ["order_confirmation_email", "shipping_tracking", "merchant_terms_of_service"],
      ["order_confirmation_email", "shipping_tracking", "merchant_terms_of_service"],
      ["delay_notification", "delivery_confirmation"],
      ["state_promised_date"],
      ["delivery_guarantee_terms"])
# ---- Quality & Description -----------------------------------------------
entry("QD-01",
      ["product_listing", "cardholder_photos", "merchant_return_policy"],
      ["product_listing", "cardholder_photos", "merchant_inspection_records"],
      ["product_listing", "cardholder_photos", "carrier_damage_claim"],
      ["packaging_photos", "qc_records"],
      ["photos_of_damage", "description_of_defect"],
      ["pre_shipment_inspection", "packaging_standards", "qc_records"])
entry("QD-02",
      ["product_specs", "cardholder_statement", "warranty_records"],
      ["product_specs", "cardholder_statement", "warranty_records"],
      ["product_specs", "cardholder_statement", "warranty_records"],
      ["cardholder_photos", "communication_thread"],
      ["describe_defect", "repair_attempts"],
      ["qc_records", "manufacturer_defect_reports"])
entry("QD-03",
      ["product_listing", "cardholder_photos", "receipt_data"],
      ["product_listing", "cardholder_photos", "receipt_data"],
      ["product_listing", "cardholder_photos", "receipt_data"],
      ["product_specs", "communication_thread"],
      ["photos_of_item", "state_material_difference"],
      ["catalog_specs", "order_line_items"])
entry("QD-04",
      ["cardholder_photos", "brand_authentication", "product_listing"],
      ["cardholder_photos", "brand_authentication", "product_listing"],
      ["cardholder_photos", "brand_authentication", "product_listing"],
      ["packaging_photos"],
      ["photos_of_authenticity_markers"],
      ["sourcing_documentation", "supplier_invoices"])
entry("QD-05",
      ["product_listing", "cardholder_photos", "merchant_fulfillment_status"],
      ["product_listing", "cardholder_photos", "merchant_fulfillment_status"],
      ["product_listing", "cardholder_photos", "merchant_fulfillment_status"],
      ["receipt_data", "packaging_photos"],
      ["photos_of_received_item"],
      ["pick_pack_records", "sku_records"])
entry("QD-06",
      ["product_listing", "cardholder_photos", "cardholder_statement"],
      ["product_listing", "cardholder_photos", "cardholder_statement"],
      ["product_listing", "cardholder_photos", "cardholder_statement"],
      ["communication_thread", "merchant_return_policy"],
      ["photos_of_item", "describe_quality_issue"],
      ["quality_standards", "qc_records"])
# ---- Billing & Amount ----------------------------------------------------
entry("BA-01",
      ["all_transactions_same_merchant_7d", "receipt_data"],
      ["all_transactions_same_merchant_7d", "authorization_log"],
      ["all_transactions_same_merchant_7d", "receipt_data", "pos_terminal_logs"],
      ["payment_gateway_logs"],
      ["confirm_which_charge_valid"],
      ["invoice_per_charge", "refund_records"])
entry("BA-02",
      ["authorization_log", "receipt_data"],
      ["authorization_log", "receipt_data"],
      ["authorization_log", "receipt_data", "pos_terminal_logs"],
      ["payment_gateway_logs"],
      ["state_expected_amount"],
      ["itemized_invoice", "correcting_transactions"])
entry("BA-03",
      ["other_payment_proof", "receipt_data", "payment_gateway_logs"],
      ["other_payment_proof", "receipt_data", "payment_gateway_logs"],
      ["other_payment_proof", "receipt_data", "payment_gateway_logs"],
      ["communication_thread"],
      ["proof_of_other_payment"],
      ["multi_channel_payment_records"])
entry("BA-04",
      ["refund_records", "merchant_return_policy", "communication_thread"],
      ["refund_records", "merchant_return_policy", "communication_thread"],
      ["refund_records", "merchant_return_policy", "communication_thread"],
      ["return_shipping_proof", "refund_promise_email"],
      ["return_proof", "refund_promise"],
      ["refund_processing_logs", "credit_issuance_records"])
entry("BA-05",
      ["payment_gateway_logs", "receipt_data"],
      ["payment_gateway_logs", "receipt_data"],
      ["payment_gateway_logs", "receipt_data"],
      ["authorization_log"],
      ["statement_screenshot"],
      ["presentment_type_logs"])
entry("BA-06",
      ["authorization_log", "receipt_data"],
      ["authorization_log", "receipt_data"],
      ["authorization_log", "receipt_data"],
      ["communication_thread"],
      ["state_authorized_amount"],
      ["incremental_authorization_consent"])
entry("BA-07",
      ["installment_agreement", "payment_gateway_logs", "receipt_data"],
      ["installment_agreement", "payment_gateway_logs", "receipt_data"],
      ["installment_agreement", "payment_gateway_logs", "receipt_data"],
      ["communication_thread"],
      ["state_agreed_schedule"],
      ["billing_schedule_records"])
entry("BA-08",
      ["currency_conversion_record", "dcc_consent_record", "receipt_data"],
      ["currency_conversion_record", "dcc_consent_record", "receipt_data"],
      ["currency_conversion_record", "dcc_consent_record", "receipt_data"],
      ["payment_gateway_logs"],
      ["statement_screenshot"],
      ["exchange_rate_records"])
entry("BA-09",   # Excel-only mapping (Amex 4536 Late Presentment) — preserved
      ["payment_gateway_logs", "receipt_data"],
      ["payment_gateway_logs", "receipt_data"],
      ["payment_gateway_logs", "receipt_data"],
      ["authorization_log"],
      [],
      ["presentment_date_records"])
# ---- Cancellation & Returns ----------------------------------------------
entry("CR-01",
      ["return_shipping_proof", "merchant_return_policy", "refund_records"],
      ["return_shipping_proof", "merchant_return_policy", "refund_records"],
      ["return_shipping_proof", "merchant_return_policy", "refund_records"],
      ["communication_thread"],
      ["return_tracking_number"],
      ["return_receiving_records", "refund_processing_logs"])
entry("CR-02",
      ["cancellation_records", "communication_thread", "merchant_terms_of_service"],
      ["cancellation_records", "communication_thread", "merchant_terms_of_service"],
      ["cancellation_records", "communication_thread", "merchant_terms_of_service"],
      ["cancellation_confirmation"],
      ["cancellation_confirmation_number"],
      ["cancellation_processing_logs"])
entry("CR-03",
      ["cancellation_records", "subscription_history", "merchant_terms_of_service"],
      ["cancellation_records", "subscription_history", "merchant_terms_of_service"],
      ["cancellation_records", "subscription_history", "merchant_terms_of_service"],
      ["cancellation_confirmation", "communication_thread"],
      ["cancellation_date", "cancellation_confirmation_number"],
      ["billing_after_cancellation_logs"])
entry("CR-04",
      ["subscription_history", "promotional_terms", "communication_thread"],
      ["subscription_history", "promotional_terms", "communication_thread"],
      ["subscription_history", "promotional_terms", "communication_thread"],
      ["cancellation_records"],
      ["trial_signup_details"],
      ["consent_records", "trial_terms_disclosure"])
entry("CR-05",
      ["booking_confirmation", "no_show_policy", "cancellation_records"],
      ["booking_confirmation", "no_show_policy", "cancellation_records"],
      ["booking_confirmation", "no_show_policy", "cancellation_records"],
      ["communication_thread"],
      ["cancellation_attempt_details"],
      ["policy_disclosure_proof", "folio_records"])
entry("CR-06",
      ["shipping_tracking", "merchant_return_policy", "refund_records"],
      ["shipping_tracking", "merchant_return_policy", "refund_records"],
      ["shipping_tracking", "merchant_return_policy", "refund_records"],
      ["communication_thread"],
      ["refusal_reason"],
      ["return_receiving_records"])
# ---- Authorization & Recognition -----------------------------------------
entry("AR-01",
      ["receipt_data", "merchant_fulfillment_status", "login_ip_device_data"],
      ["receipt_data", "merchant_fulfillment_status", "login_ip_device_data"],
      ["receipt_data", "merchant_fulfillment_status", "login_ip_device_data"],
      ["order_confirmation_email", "shipping_tracking"],
      ["confirm_descriptor_unfamiliar"],
      ["descriptor_details", "delivery_or_ip_proof"])
entry("AR-02",
      ["authorization_log", "payment_gateway_logs"],
      ["authorization_log", "payment_gateway_logs"],
      ["authorization_log", "payment_gateway_logs"],
      ["receipt_data"],
      [],
      ["authorization_approval_records"])
entry("AR-03",
      ["emv_chip_data", "pos_signed_receipt", "authorization_log"],
      ["emv_chip_data", "pos_signed_receipt", "authorization_log"],
      ["emv_chip_data", "pos_signed_receipt", "authorization_log"],
      ["pos_terminal_logs"],
      ["state_card_possession"],
      ["card_imprint", "terminal_records"])
entry("AR-04",   # Excel-only (Amex 4763 Fraud Full Recourse) — preserved
      ["authorization_log", "payment_gateway_logs"],
      ["authorization_log", "payment_gateway_logs"],
      ["authorization_log", "payment_gateway_logs"],
      ["emv_chip_data"], [], ["fraud_program_records"])
entry("AR-05",   # Excel-only (Amex 4798 Liability Shift Counterfeit) — preserved
      ["emv_chip_data", "authorization_log"],
      ["emv_chip_data", "authorization_log"],
      ["emv_chip_data", "authorization_log"],
      ["pos_terminal_logs"], [], ["chip_capability_records"])
# ---- Special & Industry-Specific -----------------------------------------
entry("SP-01",
      ["rental_agreement", "damage_acknowledgement", "cardholder_photos"],
      ["rental_agreement", "damage_acknowledgement", "cardholder_photos"],
      ["rental_agreement", "damage_acknowledgement", "cardholder_photos"],
      ["insurance_claim_record", "communication_thread"],
      ["state_vehicle_condition", "photos_of_item"],
      ["itemized_damage_bill", "repair_estimates"])
entry("SP-02",
      ["hotel_folio", "booking_confirmation", "receipt_data"],
      ["hotel_folio", "booking_confirmation", "receipt_data"],
      ["hotel_folio", "booking_confirmation", "receipt_data"],
      ["communication_thread"],
      ["state_disputed_incidentals"],
      ["signed_registration", "incidental_consent"])
entry("SP-03",
      ["airline_ticket_records", "travel_disruption_record", "receipt_data"],
      ["airline_ticket_records", "travel_disruption_record", "receipt_data"],
      ["airline_ticket_records", "travel_disruption_record", "receipt_data"],
      ["communication_thread", "booking_confirmation"],
      ["state_travel_issue"],
      ["tariff_rules", "credit_issuance_records"])
entry("SP-04",
      ["merchant_terms_of_service", "communication_thread", "receipt_data"],
      ["merchant_terms_of_service", "communication_thread", "receipt_data"],
      ["merchant_terms_of_service", "communication_thread", "receipt_data"],
      ["promotional_terms"],
      ["contract_copy", "rescission_attempt_details"],
      ["signed_contract", "disclosure_records"])
entry("SP-05",
      ["insurance_claim_record", "receipt_data", "communication_thread"],
      ["insurance_claim_record", "receipt_data", "communication_thread"],
      ["insurance_claim_record", "receipt_data", "communication_thread"],
      ["payment_gateway_logs"],
      ["insurance_policy_details"],
      ["claim_settlement_records"])
entry("SP-06",
      ["promotional_terms", "receipt_data", "communication_thread"],
      ["promotional_terms", "receipt_data", "communication_thread"],
      ["promotional_terms", "receipt_data", "communication_thread"],
      ["order_confirmation_email"],
      ["promo_offer_copy"],
      ["offer_terms_disclosure"])
entry("SP-07",
      ["product_listing", "cardholder_statement", "communication_thread"],
      ["product_listing", "cardholder_statement", "communication_thread"],
      ["product_listing", "cardholder_statement", "communication_thread"],
      ["cardholder_photos", "promotional_terms"],
      ["advertising_copy", "state_misrepresentation"],
      ["advertising_records", "substantiation_docs"])
entry("SP-08",
      ["atm_terminal_logs", "receipt_data"],
      ["atm_terminal_logs", "receipt_data"],
      ["atm_terminal_logs", "receipt_data"],
      ["payment_gateway_logs"],
      ["state_amount_received"],
      ["terminal_balancing_records"])

# --------------------------------------------------------------------------
# Weight profiles — the Excel 'Evidence Weight matrix' sheet is authoritative.
# profile_map assigns each internal type to one of the 10 Excel profiles.
# --------------------------------------------------------------------------
PROFILE_MAP = {
    "NR-01": "NR", "NR-02": "NR", "NR-03": "NR", "NR-05": "NR",
    "NR-04": "SP_DIGITAL",                       # digital goods profile
    "QD-01": "QD", "QD-02": "QD", "QD-03": "QD", "QD-04": "QD",
    "QD-05": "QD", "QD-06": "QD",
    "BA-01": "BA_DUP",
    "BA-02": "BA_AMT", "BA-03": "BA_AMT", "BA-05": "BA_AMT",
    "BA-06": "BA_AMT", "BA-07": "BA_AMT", "BA-08": "BA_AMT",
    "BA-09": "BA_AMT",                           # Excel-only code, closest profile
    "BA-04": "CR_RET",                           # refund-not-processed behaves like returns
    "CR-01": "CR_RET", "CR-02": "CR_RET", "CR-05": "CR_RET", "CR-06": "CR_RET",
    "CR-03": "CR_SUB", "CR-04": "CR_SUB",
    "AR-01": "AR", "AR-02": "AR", "AR-03": "AR",
    "AR-04": "AR", "AR-05": "AR",                # Excel-only codes
    "SP-01": "SP_RENTAL", "SP-02": "SP_RENTAL",
    "SP-03": "SP_TRAVEL",
    "SP-04": "CR_RET", "SP-05": "BA_AMT", "SP-06": "CR_SUB",
    "SP-07": "QD", "SP-08": "BA_AMT",
}


def main():
    excel = load_excel_taxonomy()
    reg = get_registry()

    for code in reg.all_codes():
        assert code in M, f"evidence matrix missing {code}"
        assert code in PROFILE_MAP, f"profile map missing {code}"

    matrix_doc = {
        "_meta": {
            "layer": 2,
            "note": "Network-specific evidence mapping. Editable configuration - "
                    "a Visa rule change is a one-row edit here, no code changes.",
        },
        "categories": M,
    }
    (ROOT / "config" / "evidence_matrix.yaml").write_text(
        yaml.safe_dump(matrix_doc, sort_keys=False, width=100))

    weights_doc = {
        "_meta": {
            "layer": 6,
            "source": "Excel sheet 'Evidence Weight matrix' (authoritative). "
                      "profile_map assigns each internal type to a profile.",
        },
        "profiles": excel["weight_profiles"],
        "profile_map": PROFILE_MAP,
    }
    (ROOT / "config" / "weights.yaml").write_text(
        yaml.safe_dump(weights_doc, sort_keys=False, width=100))

    for pname, dims in excel["weight_profiles"].items():
        s = sum(dims.values())
        assert abs(s - 1.0) < 1e-6, f"profile {pname} weights sum to {s}"
    print("Wrote config/evidence_matrix.yaml "
          f"({len(M)} categories x 3 networks) and config/weights.yaml "
          f"({len(excel['weight_profiles'])} profiles, {len(PROFILE_MAP)} assignments)")


if __name__ == "__main__":
    main()
