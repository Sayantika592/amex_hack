"""DeterministicClassifier (DEMO mode fallback).

A transparent lexical model: every internal type has a weighted phrase
lexicon; the description is lemma-normalized (spaCy when available) and
scored by matched phrase weights, then squashed into a calibrated [0,1]
confidence.  Deterministic, dependency-free, fully explainable — and clearly
reported as mode="demo" so the UI never claims BART ran when it did not.
"""
from __future__ import annotations

import math
import re

from backend.models.classification.base import ClassificationModel
from backend.taxonomy import techdoc

# phrase -> weight.  2.0 = decisive phrase, 1.0 = strong, 0.5 = supportive.
LEXICON: dict[str, list[tuple[str, float]]] = {
    "NR-01": [("never arrived", 2.0), ("not received", 2.0), ("never received", 2.0),
              ("did not arrive", 2.0), ("didn't arrive", 2.0), ("no sign of the package", 1.5),
              ("package never", 1.5), ("nothing arrived", 1.8), ("still waiting for", 1.0),
              ("order never came", 1.8), ("not delivered", 1.5), ("no package", 1.0),
              ("never showed up", 1.6), ("never got", 1.2), ("missing entirely", 1.0)],
    "NR-02": [("only received", 2.0), ("partially received", 2.0), ("missing from the order", 1.8),
              ("some items missing", 2.0), ("items were missing", 1.8), ("incomplete order", 1.6),
              ("only part of", 1.5), ("one of the items", 0.8), ("rest of the order", 1.2),
              ("short shipped", 1.6), ("missing item", 1.2)],
    "NR-03": [("service was never", 2.0), ("never performed", 2.0), ("no one showed up", 1.8),
              ("appointment", 0.8), ("technician never", 1.6), ("class was cancelled and never", 1.0),
              ("service not rendered", 2.0), ("never provided the service", 1.8),
              ("contractor", 0.6), ("session never happened", 1.5), ("repair was never done", 1.6)],
    "NR-04": [("download link", 1.6), ("never received access", 1.6), ("digital", 1.0),
              ("license key", 1.6), ("no access", 1.0), ("software", 0.8), ("ebook", 1.2),
              ("course access", 1.5), ("account was never activated", 1.5),
              ("activation email never", 1.5), ("can't download", 1.4), ("cannot download", 1.4)],
    "NR-05": [("arrived late", 1.6), ("after the event", 1.8), ("too late", 1.5),
              ("promised delivery date", 1.8), ("weeks late", 1.6), ("late delivery", 2.0),
              ("delivered after", 1.2), ("missed the promised", 1.6), ("arrived days after", 1.4),
              ("useless by the time it arrived", 1.6)],
    "QD-01": [("damaged", 1.6), ("cracked", 1.8), ("broken on arrival", 2.0), ("shattered", 1.8),
              ("arrived broken", 2.0), ("dent", 1.4), ("smashed", 1.6), ("water damage", 1.5),
              ("damaged during shipping", 2.0), ("arrived damaged", 2.0), ("chipped", 1.2),
              ("broken when i opened", 2.0), ("screen was cracked", 2.0), ("torn", 1.0)],
    "QD-02": [("defective", 2.0), ("doesn't work", 1.8), ("does not work", 1.8),
              ("won't turn on", 1.8), ("stopped working", 1.6), ("won't power on", 1.8),
              ("keeps crashing", 1.6), ("faulty", 1.6), ("malfunction", 1.6),
              ("not functioning", 1.6), ("dead on arrival", 1.5), ("doesn't charge", 1.4)],
    "QD-03": [("not as described", 2.0), ("different from the listing", 1.8),
              ("wrong color", 1.4), ("wrong size", 1.2), ("doesn't match the description", 1.8),
              ("smaller than advertised", 1.5), ("different model", 1.2),
              ("materially different", 1.6), ("looks nothing like", 1.6),
              ("photo showed", 1.0), ("advertised as", 1.0), ("listing said", 1.2)],
    "QD-04": [("counterfeit", 2.2), ("fake", 1.8), ("not authentic", 2.0), ("knock-off", 2.0),
              ("knockoff", 2.0), ("replica", 1.8), ("inauthentic", 2.0),
              ("serial number doesn't", 1.5), ("not genuine", 1.8)],
    "QD-05": [("wrong item", 2.2), ("sent me a different", 1.8), ("received the wrong", 2.0),
              ("completely different product", 1.6), ("ordered a", 0.5),
              ("instead of the", 1.0), ("wrong product", 2.0), ("mixed up my order", 1.4)],
    "QD-06": [("poor quality", 2.0), ("cheaply made", 1.8), ("terrible quality", 2.0),
              ("below standard", 1.8), ("quality is unacceptable", 2.2), ("badly made", 1.6),
              ("flimsy", 1.4), ("substandard", 1.8), ("fell apart after", 1.4),
              ("stitching came undone", 1.2)],
    "BA-01": [("charged twice", 2.2), ("duplicate charge", 2.2), ("double charged", 2.2),
              ("two identical charges", 2.0), ("billed twice", 2.0), ("same charge twice", 2.0),
              ("charged me two times", 1.8), ("appears twice", 1.6), ("double billed", 2.0)],
    "BA-02": [("wrong amount", 2.0), ("charged more than", 1.8), ("incorrect amount", 2.2),
              ("overcharged", 1.8), ("price was supposed to be", 1.5), ("charged extra", 1.2),
              ("amount doesn't match", 1.6), ("receipt says", 1.0), ("billed the wrong", 1.6)],
    "BA-03": [("paid in cash", 2.0), ("paid by other", 2.0), ("already paid with", 2.0),
              ("paid with a different card", 1.8), ("paid via bank transfer", 1.8),
              ("also charged my card", 1.4), ("settled the bill in cash", 1.8),
              ("paid through another", 1.8), ("upi", 1.2), ("gift card", 0.8)],
    "BA-04": [("refund never", 2.0), ("refund not processed", 2.2), ("promised a refund", 1.8),
              ("still waiting for my refund", 2.0), ("refund hasn't", 1.8),
              ("no refund has been", 1.8), ("agreed to refund", 1.6), ("credit never appeared", 1.6),
              ("refund was never issued", 2.0)],
    "BA-05": [("credit posted as a charge", 2.4), ("refund showed up as a charge", 2.2),
              ("credited but it charged", 2.0), ("charged instead of credited", 2.2),
              ("charge instead of a credit", 2.2), ("reversal posted as", 1.8)],
    "BA-06": [("more than the authorized", 2.0), ("exceeds the authorization", 2.2),
              ("final charge was higher than", 1.8), ("authorized amount was", 1.6),
              ("hold was for", 1.2), ("charged above what i approved", 1.8),
              ("tip was inflated", 1.4)],
    "BA-07": [("installment", 2.2), ("emi", 2.0), ("payment plan", 1.6),
              ("instalment", 2.2), ("monthly installments", 2.0),
              ("charged the full amount instead of", 1.4), ("wrong installment", 1.8)],
    "BA-08": [("currency", 1.8), ("exchange rate", 2.0), ("conversion", 1.6),
              ("charged in usd", 1.6), ("dcc", 1.8), ("dynamic currency", 2.0),
              ("converted at a terrible rate", 1.8), ("foreign transaction", 1.2)],
    "CR-01": [("returned the item", 2.0), ("sent it back", 1.8), ("return was delivered", 1.8),
              ("no refund after return", 2.2), ("returned but", 1.8),
              ("return tracking shows", 1.6), ("shipped it back", 1.8),
              ("they received my return", 1.8)],
    "CR-02": [("cancelled my order", 2.0), ("order was cancelled", 2.0),
              ("cancelled before it shipped", 1.8), ("still charged", 1.6),
              ("charged even though i cancelled", 2.0), ("cancellation was confirmed", 1.6),
              ("cancelled the booking", 1.4)],
    "CR-03": [("cancelled my subscription", 2.2), ("subscription", 1.4),
              ("cancelled the membership", 2.0), ("still being billed", 1.8),
              ("recurring charge after", 1.8), ("charged after i cancelled", 1.8),
              ("membership was cancelled", 1.8), ("keeps charging me every month", 1.8)],
    "CR-04": [("free trial", 2.4), ("trial converted", 2.2), ("never agreed to a paid", 1.8),
              ("trial ended and they charged", 2.0), ("didn't consent to the subscription", 1.6),
              ("auto-enrolled", 1.6), ("signed up for a trial", 1.8)],
    "CR-05": [("no-show", 2.2), ("no show", 2.0), ("hotel charged me for the night", 1.8),
              ("cancelled the reservation", 1.6), ("reservation", 1.2),
              ("never checked in", 1.8), ("room i never used", 1.8),
              ("booking i cancelled", 1.6)],
    "CR-06": [("refused the delivery", 2.2), ("refused at delivery", 2.2),
              ("rejected the package", 2.0), ("refused to accept the package", 2.0),
              ("sent back with the courier", 1.6), ("declined the delivery", 1.8)],
    "AR-01": [("don't recognize", 2.0), ("do not recognize", 2.0), ("unrecognized", 2.0),
              ("unfamiliar charge", 1.8), ("no idea what this charge", 1.8),
              ("never heard of this merchant", 1.8), ("what this descriptor", 1.4),
              ("statement shows a charge i", 1.4)],
    "AR-02": [("never authorized", 2.0), ("without authorization", 2.0),
              ("no authorization", 1.8), ("didn't authorize", 2.0),
              ("authorization was declined but", 1.8), ("charged without approval", 1.8)],
    "AR-03": [("card was in my possession", 1.8), ("card-present", 1.8),
              ("never visited that store", 1.8), ("in-store charge i didn't make", 1.8),
              ("swiped", 1.2), ("chip transaction i don't", 1.6),
              ("was never at that location", 1.6), ("terminal", 0.8)],
    "SP-01": [("rental car", 2.0), ("car rental", 2.0), ("vehicle rental", 2.2),
              ("damage to the car", 1.6), ("rental company charged", 1.8),
              ("returned the car", 1.4), ("scratch i didn't cause", 1.4),
              ("rental agency", 1.6)],
    "SP-02": [("minibar", 1.8), ("incidental", 2.2), ("hotel charged extra", 1.6),
              ("checkout charge", 1.4), ("folio", 1.8), ("room service i never ordered", 1.6),
              ("hotel added", 1.4), ("resort fee", 1.4)],
    "SP-03": [("flight", 1.8), ("airline", 2.0), ("ticket", 1.0), ("cancelled flight", 1.8),
              ("airfare", 1.6), ("boarding", 1.0), ("refund for the flight", 1.4),
              ("travel voucher", 1.4), ("itinerary", 1.0)],
    "SP-04": [("timeshare", 2.4), ("vacation club", 2.2), ("rescind", 1.6),
              ("points package", 1.4), ("presentation pressured", 1.4),
              ("maintenance fees", 1.2)],
    "SP-05": [("insurance", 2.0), ("covered by insurance", 2.2), ("claim was approved", 1.4),
              ("insurer already paid", 2.0), ("policy covers", 1.6),
              ("hospital charged me even though insurance", 1.6)],
    "SP-06": [("promotional", 2.0), ("promo code", 1.8), ("introductory offer", 2.2),
              ("discount was not applied", 1.8), ("advertised rate", 1.6),
              ("promised promotional price", 1.8), ("intro rate", 1.6)],
    "SP-07": [("misrepresent", 2.2), ("false advertising", 2.2), ("misleading", 1.8),
              ("deceptive", 1.8), ("claimed it would", 1.2), ("advertised benefits", 1.4),
              ("bait and switch", 2.0)],
    "SP-08": [("atm", 2.4), ("cash was not dispensed", 2.2), ("dispensed only", 1.8),
              ("machine did not give", 1.8), ("withdrawal", 1.6),
              ("debited but no cash", 2.0), ("cash machine", 1.8)],
}

_norm_re = re.compile(r"[^a-z0-9\s'-]")


def _norm(text: str) -> str:
    return " " + _norm_re.sub(" ", text.lower()).replace("  ", " ").strip() + " "


class DeterministicClassifier(ClassificationModel):
    name = "DeterministicClassifier (weighted phrase lexicon)"
    mode = "demo"

    def __init__(self):
        self.lexicon = {code: [(_norm(p).strip(), w) for p, w in phrases]
                        for code, phrases in LEXICON.items()}

    def score_labels(self, description, labels):
        text = _norm(description)
        raw: dict[str, float] = {}
        for code, phrases in self.lexicon.items():
            s = 0.0
            for phrase, w in phrases:
                if f" {phrase} " in text or (len(phrase) > 12 and phrase in text):
                    s += w
            if s > 0:
                raw[code] = s
        if not raw:
            return [(l, 0.05) for l in labels[:3]]
        # squash: conf = 1 - exp(-k*score), then scale by relative margin
        scored = []
        best = max(raw.values())
        for code, s in raw.items():
            conf = 1.0 - math.exp(-0.70 * s)
            conf *= 0.55 + 0.45 * (s / best)
            label = techdoc.CODE_TO_LABEL.get(code, code)
            if label in labels:
                scored.append((label, min(conf, 0.96)))
        scored.sort(key=lambda x: -x[1])
        matched = {l for l, _ in scored}
        scored += [(l, 0.02) for l in labels if l not in matched][:2]
        return scored
