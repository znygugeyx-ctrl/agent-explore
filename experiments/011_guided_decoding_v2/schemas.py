"""JSON Schema definitions for each dataset in Experiment 011."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Track 1: GSM8K — minimal integer-only schema
# ---------------------------------------------------------------------------

GSM8K_SCHEMA = {
    "type": "object",
    "required": ["answer"],
    "properties": {
        "answer": {"type": "integer"},
    },
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Track 2: Classification schemas — enum with varying cardinality
# ---------------------------------------------------------------------------

SST5_LABELS = [
    "very_negative", "negative", "neutral", "positive", "very_positive",
]

# GoEmotions: 28 emotion categories (excluding "neutral" duplicates)
GOEMO_LABELS = [
    "admiration", "amusement", "anger", "annoyance", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment",
    "disapproval", "disgust", "embarrassment", "excitement", "fear",
    "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral",
]

# BANKING77: 77 intent categories (from legacy-datasets/banking77 HuggingFace)
BANKING77_LABELS = [
    "activate_my_card",
    "age_limit",
    "apple_pay_or_google_pay",
    "atm_support",
    "automatic_top_up",
    "balance_not_updated_after_bank_transfer",
    "balance_not_updated_after_cheque_or_cash_deposit",
    "beneficiary_not_allowed",
    "cancel_transfer",
    "card_about_to_expire",
    "card_acceptance",
    "card_arrival",
    "card_delivery_estimate",
    "card_linking",
    "card_not_working",
    "card_payment_fee_charged",
    "card_payment_not_recognised",
    "card_payment_wrong_exchange_rate",
    "card_swallowed",
    "cash_withdrawal_charge",
    "cash_withdrawal_not_recognised",
    "change_pin",
    "compromised_card",
    "contactless_not_working",
    "country_support",
    "declined_card_payment",
    "declined_cash_withdrawal",
    "declined_transfer",
    "direct_debit_payment_not_recognised",
    "disposable_card_limits",
    "edit_personal_details",
    "exchange_charge",
    "exchange_rate",
    "exchange_via_app",
    "extra_charge_on_statement",
    "failed_transfer",
    "fiat_currency_support",
    "get_disposable_virtual_card",
    "get_physical_card",
    "getting_spare_card",
    "getting_virtual_card",
    "lost_or_stolen_card",
    "lost_or_stolen_phone",
    "order_physical_card",
    "passcode_forgotten",
    "pending_card_payment",
    "pending_cash_withdrawal",
    "pending_top_up",
    "pending_transfer",
    "pin_blocked",
    "receiving_money",
    "Refund_not_showing_up",
    "request_refund",
    "reverted_card_payment?",
    "supported_cards_and_currencies",
    "terminate_account",
    "top_up_by_bank_transfer_charge",
    "top_up_by_card_charge",
    "top_up_by_cash_or_cheque",
    "top_up_failed",
    "top_up_limits",
    "top_up_reverted",
    "topping_up_by_card",
    "transaction_charged_twice",
    "transfer_fee_charged",
    "transfer_into_account",
    "transfer_not_received_by_recipient",
    "transfer_timing",
    "unable_to_verify_identity",
    "verify_my_identity",
    "verify_source_of_funds",
    "verify_top_up",
    "virtual_card_not_working",
    "visa_or_mastercard",
    "why_verify_identity",
    "wrong_amount_of_cash_received",
    "wrong_exchange_rate_for_cash_withdrawal",
]


def get_classification_schema(labels: list[str]) -> dict:
    """Build a JSON Schema for classification with the given enum labels."""
    return {
        "type": "object",
        "required": ["label"],
        "properties": {
            "label": {"type": "string", "enum": labels},
        },
        "additionalProperties": False,
    }


# Pre-built schemas
SST5_SCHEMA = get_classification_schema(SST5_LABELS)
GOEMO_SCHEMA = get_classification_schema(GOEMO_LABELS)
BANKING77_SCHEMA = get_classification_schema(BANKING77_LABELS)

# ---------------------------------------------------------------------------
# Track 3: NER — array of objects with enum (complex structure)
# ---------------------------------------------------------------------------

FEWNERD_LABELS = [
    "person", "organization", "location", "building",
    "event", "art", "product", "other",
]

FEWNERD_SCHEMA = {
    "type": "object",
    "required": ["entities"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "type"],
                "properties": {
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": FEWNERD_LABELS},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Track 4: Recipe — deeply nested multi-field schema
# ---------------------------------------------------------------------------

RECIPE_SCHEMA = {
    "type": "object",
    "required": ["recipe_name", "servings", "ingredients", "cuisine_type", "diet_labels"],
    "properties": {
        "recipe_name": {"type": "string"},
        "servings": {"type": "integer"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["food", "quantity", "unit"],
                "properties": {
                    "food": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "cuisine_type": {"type": "string"},
        "diet_labels": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "additionalProperties": False,
}

# Registry for easy lookup
SCHEMAS = {
    "gsm8k": GSM8K_SCHEMA,
    "sst5": SST5_SCHEMA,
    "goemo": GOEMO_SCHEMA,
    "banking77": BANKING77_SCHEMA,
    "fewnerd": FEWNERD_SCHEMA,
    "recipe": RECIPE_SCHEMA,
}

LABELS = {
    "sst5": SST5_LABELS,
    "goemo": GOEMO_LABELS,
    "banking77": BANKING77_LABELS,
    "fewnerd": FEWNERD_LABELS,
}
