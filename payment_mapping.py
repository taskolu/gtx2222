from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentTemplate:
    source_code: str
    template: str
    unit: str
    uses_pacs_flow: bool = True


PACS_TEMPLATE_MAP = {
    "AUDCUKBOA": PaymentTemplate("AUDCUKBOA", "APAUDPACS", "TGBP"),
    "CHFCUKCSB": PaymentTemplate("CHFCUKCSB", "APCHFPACS", "TGBP"),
    "EURCHKING": PaymentTemplate("EURCHKING", "EURPMTAP2PACS", "CCT_CHUK"),
    "HKDCUKBOA": PaymentTemplate("HKDCUKBOA", "APHKDPACS", "TGBP"),
    "JPYCUKCIT": PaymentTemplate("JPYCUKCIT", "APJPYPACS", "CCT_CHUK"),
    "GBPCHBARX": PaymentTemplate("GBPCHBARX", "APGBPPACS", "CCT_CHUK"),
    "GBPCVBAROPS": PaymentTemplate("GBPCVBAROPS", "APGBPPACS2", "CCT_CHUK"),
    "USDBNYCHKINC": PaymentTemplate("USDBNYCHKINC", "APUSDPACS", "CCT_CHUK"),
    "CADCHKRBC": PaymentTemplate("CADCHKRBC", "APCADPACS", "CCT_CHUK"),
    "CADBMOIN": PaymentTemplate("CADBMOIN", "APCADPACS", "CCT_CHUK"),
    "NZDCUKCIT": PaymentTemplate("NZDCUKCIT", "APNZDPACS", "CCT_CHUK"),
    "SGDCHKBNY": PaymentTemplate("SGDCHKBNY", "APSGDPACS", "CCT_CHUK"),
    "PLNCUKING": PaymentTemplate("PLNCUKING", "APPLNPACS", "CCT_CHUK"),
}

LEGACY_TEMPLATE_MAP = {
    "CZKCUKKOM": PaymentTemplate("CZKCUKKOM", "APFUNDINGCZK", "CCT_CHUK", uses_pacs_flow=False),
}

SKIPPED_CODES = {"EURMALAP", "BOV Platform (EUR)"}
ZERO_DECIMAL_CODES = {"JPYCUKCIT", "APJPYPACS"}
PACS_FIRST_AMOUNT_FIELD_IDS = {
    "APAUDPACS": "rightTreeForm:Value-348",
    "APGBPPACS2": "rightTreeForm:Value-327",
}


def _normalize_code(code):
    return str(code or "").strip()


def resolve_payment_template(code):
    normalized = _normalize_code(code)
    if not normalized or normalized in SKIPPED_CODES:
        return None

    if normalized in PACS_TEMPLATE_MAP:
        return PACS_TEMPLATE_MAP[normalized]

    if normalized in LEGACY_TEMPLATE_MAP:
        return LEGACY_TEMPLATE_MAP[normalized]

    for template in PACS_TEMPLATE_MAP.values():
        if normalized == template.template:
            return template

    for template in LEGACY_TEMPLATE_MAP.values():
        if normalized == template.template:
            return template

    return None


def is_valid_payment_code(code):
    return resolve_payment_template(code) is not None


def get_pacs_first_amount_field_id(template):
    return PACS_FIRST_AMOUNT_FIELD_IDS.get(_normalize_code(template))


def format_amount(amount, code=None):
    cleaned = str(amount).replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
    decimals = 0 if _normalize_code(code) in ZERO_DECIMAL_CODES else 2
    return f"{round(float(cleaned), decimals):.{decimals}f}"


def build_narrative(reference, otr_number):
    base_text = f"Funding {str(reference or 'CO5590').strip()}"
    full_text = f"{base_text} {str(otr_number).strip()}" if otr_number else base_text
    return full_text[:140]
