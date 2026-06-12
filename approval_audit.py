import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from payment_mapping import build_narrative, format_amount, resolve_payment_template


EXPECTED_TO_BIC_BY_TEMPLATE = {
    "APAUDPACS": "NATAAU3302S",
    "APCHFPACS": "BOFACH2XXXX",
    "EURPMTAP2PACS": "BBRUBEBB010",
    "APHKDPACS": "BOFAHKHXXXX",
    "APJPYPACS": "IRVTUS3NXXX",
    "APGBPPACS": "BARCGB22XXX",
    "APGBPPACS2": "BARCGB22XXX",
    "APUSDPACS": "IRVTUS3NXXX",
    "APCADPACS": "BOFMCAM2XXX",
    "APNZDPACS": "BOFAAUSXXXX",
    "APSGDPACS": "BOFASG2XXXX",
    "APFUNDINGCZK": "CEKOCZPPXXX",
    "APPLNPACS": "BARCGB22XXX",
}

EXPECTED_TO_BIC_BY_SOURCE = {
    "USDBNYCHKINC": "IRVTUS3NXXX",
}

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass(frozen=True)
class ApprovalReference:
    template: str
    reference: str


@dataclass
class ParsedPaymentDetails:
    unit: str = ""
    to_bic: str = ""
    message_id: str = ""
    instruction_id: str = ""
    end_to_end_id: str = ""
    interbank_ccy: str = ""
    interbank_amount: str = ""
    settlement_date: str = ""
    instructed_ccy: str = ""
    instructed_amount: str = ""
    unstructured: str = ""


@dataclass
class AuditResult:
    status: str
    issues: list[str] = field(default_factory=list)
    parsed: ParsedPaymentDetails = field(default_factory=ParsedPaymentDetails)


def parse_reference_lines(text):
    references = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^([^:]+):\s*([A-Z0-9]{10,})\s*$", line)
        if not match:
            continue

        references.append(
            ApprovalReference(
                template=match.group(1).strip(),
                reference=match.group(2).strip(),
            )
        )
    return references


def format_payment_copy(template, gtx_reference, details_text):
    details = str(details_text or "").strip()
    return (
        f"{template} - {gtx_reference}\n"
        f"Payment copy\n"
        f"{'-' * 72}\n"
        f"{details}\n"
    )


def _strip_unsafe_print_html(raw_html):
    cleaned = str(raw_html or "")
    cleaned = re.sub(r"<script\b.*?</script>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<input\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<a\b[^>]*>\s*</a>", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def extract_gtexchange_print_view_html(raw_html, gtx_reference="", fallback_text=""):
    cleaned = _strip_unsafe_print_html(raw_html)

    header_match = re.search(
        r'<div\b[^>]*class="[^"]*\bheaderPrintView\b[^"]*"[^>]*>.*?</div>',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body_match = re.search(
        r'<pre>\s*<span\b[^>]*class="[^"]*\bcompleteDataDisplay\b[^"]*"[^>]*>.*?</span>\s*</pre>',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if header_match or body_match:
        return (
            '<div class="gtexchange-copy">'
            f'{header_match.group(0) if header_match else ""}'
            '<div class="messageBody">'
            f'{body_match.group(0) if body_match else ""}'
            "</div>"
            "</div>"
        )

    reference = html.escape(str(gtx_reference or ""))
    fallback = html.escape(str(fallback_text or "").strip())
    return (
        '<div class="gtexchange-copy">'
        f'<div class="headerPrintView"><table><tr><td><pre><span style="FONT-WEIGHT: bold;">Reference</span></pre></td>'
        f"<td><pre>{reference}</pre></td></tr></table></div>"
        f'<div class="messageBody"><pre><span class="bodyStdLabelTrueType completeDataDisplay">{fallback}</span></pre></div>'
        "</div>"
    )


def build_approval_audit_html(results, excel_file="", run_date=""):
    matched_results = [result for result in (results or []) if result.get("status") == "Match"]
    copy_sections = []
    for result in matched_results:
        copy_sections.append(
            '<section class="payment-section">'
            + extract_gtexchange_print_view_html(
                result.get("payment_copy_html", ""),
                result.get("reference", ""),
                result.get("payment_copy", ""),
            )
            + "</section>"
        )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ background: #ffffff; color: #333333; font-family: Arial, Helvetica, sans-serif; font-size: 10pt; margin: 0; }}
    .payment-section {{ page-break-after: always; margin: 0 0 18px; }}
    .payment-section:last-child {{ page-break-after: auto; }}
    .gtexchange-copy {{ width: 100%; }}
    .headerPrintView {{ background: #ffffff; border: 0; margin: 0 0 10px; }}
    .headerPrintView table {{ border-collapse: collapse; width: 100%; }}
    .headerPrintView td {{ padding: 2px 10px 2px 0; vertical-align: top; }}
    .headerPrintViewSep {{ border-left: 1px solid #b7b7b7; width: 12px; }}
    .bodyStdLabelTrueType, pre {{ font-family: "Courier New", Consolas, monospace; font-size: 9pt; line-height: 1.2; }}
    pre {{ margin: 0; white-space: pre-wrap; }}
    .messageBody {{ margin: 5px; }}
    .bodyStdListElt {{ color: #333333; }}
  </style>
</head>
<body>
  {''.join(copy_sections)}
</body>
</html>"""


def _first_match(pattern, text, flags=re.IGNORECASE):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _section_match(pattern, text):
    return _first_match(pattern, text, re.IGNORECASE | re.DOTALL)


def normalize_amount(value):
    try:
        return Decimal(str(value).replace(",", "").replace(" ", "").strip())
    except InvalidOperation:
        return None


def normalize_date(value):
    text = str(value or "").strip()
    if not text:
        return ""

    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y")
        except ValueError:
            pass

    match = re.match(r"^(\d{1,2})\.([A-Za-z]{3}),?(\d{2,4})$", text)
    if match:
        day = int(match.group(1))
        month = MONTHS.get(match.group(2).lower())
        year = int(match.group(3))
        if year < 100:
            year += 2000
        if month:
            return datetime(year, month, day).strftime("%d.%m.%Y")

    return text


def compact_text(value):
    return re.sub(r"\s+", "", str(value or "")).upper()


def expected_currency(payment):
    source_code = str(payment.get("source_code") or "")
    if len(source_code) >= 3 and source_code[:3].isalpha():
        return source_code[:3].upper()

    template = str(payment.get("template") or "")
    match = re.match(r"AP([A-Z]{3})", template)
    return match.group(1) if match else ""


def approval_template_name(payment):
    template = str(payment.get("template") or "").strip()
    resolved = resolve_payment_template(template)
    if resolved:
        return resolved.template

    source_code = str(payment.get("source_code") or "").strip()
    resolved = resolve_payment_template(source_code)
    if resolved:
        return resolved.template

    return template


def expected_to_bic(payment):
    template = approval_template_name(payment)
    source_code = str(payment.get("source_code") or "").strip()
    return EXPECTED_TO_BIC_BY_TEMPLATE.get(template) or EXPECTED_TO_BIC_BY_SOURCE.get(source_code)


def parse_payment_details(text):
    details_text = str(text or "")

    interbank_ccy = ""
    interbank_amount = ""
    interbank_match = re.search(
        r"Interbank Settlement Amount\s+Ccy\s+([A-Z]{3})\s+Value\s+([0-9,.\s]+?)\s+Interbank Settlement Date",
        details_text,
        re.IGNORECASE | re.DOTALL,
    )
    if interbank_match:
        interbank_ccy = interbank_match.group(1).strip()
        interbank_amount = interbank_match.group(2).strip()

    instructed_match = re.search(
        r"Instructed Amount\s+Ccy\s+([A-Z]{3})\s+Value\s+([0-9,.\s]+?)\s+Charge Bearer",
        details_text,
        re.IGNORECASE | re.DOTALL,
    )
    instructed_ccy = ""
    instructed_amount = ""
    if instructed_match:
        instructed_ccy = instructed_match.group(1).strip()
        instructed_amount = instructed_match.group(2).strip()

    return ParsedPaymentDetails(
        unit=_first_match(r"\bUnit\s+([A-Z_]+)", details_text),
        to_bic=_first_match(r"\bTo\s*:\s*([A-Z0-9]{8,11})", details_text),
        message_id=_first_match(r"Message Identification\s+([A-Z0-9]+)", details_text),
        instruction_id=_first_match(r"Instruction Identification\s+([A-Z0-9]+)", details_text),
        end_to_end_id=_first_match(r"End To End Identification\s+([A-Z0-9]+)", details_text),
        interbank_ccy=interbank_ccy,
        interbank_amount=interbank_amount,
        settlement_date=_first_match(r"Interbank Settlement Date\s+([0-9]{1,2}\.[A-Za-z]{3},?\d{2,4})", details_text),
        instructed_ccy=instructed_ccy,
        instructed_amount=instructed_amount,
        unstructured=_section_match(r"Unstructured\s+(.+)$", details_text),
    )


def parse_legacy_payment_details(text):
    details_text = str(text or "")
    amount_match = re.search(
        r"Currency Transaction Amount\s+([A-Z]{3})\s+([0-9,.\s]+)",
        details_text,
        re.IGNORECASE,
    )
    currency = amount_match.group(1).strip() if amount_match else ""
    amount = amount_match.group(2).strip() if amount_match else ""

    remittance = _section_match(
        r"Remittance Information\s+(.+?)\s+\(71A\)\s+Details of Charges",
        details_text,
    )

    sender_reference = _first_match(r"Sender's Reference\s+([A-Z0-9]+)", details_text)
    transaction_reference = _first_match(r"Transaction Reference\s+([A-Z0-9]+)", details_text)

    return ParsedPaymentDetails(
        unit=_first_match(r"\bUnit\s+([A-Z_]+)", details_text),
        to_bic=_first_match(r"\bTo\s*:\s*([A-Z0-9]{8,11})", details_text),
        message_id=sender_reference,
        instruction_id=transaction_reference,
        end_to_end_id=transaction_reference,
        interbank_ccy=currency,
        interbank_amount=amount,
        settlement_date=_first_match(r"Requested Execution Date\s+([0-9]{1,2}\.[A-Za-z]{3},?\d{2,4})", details_text),
        instructed_ccy=currency,
        instructed_amount=amount,
        unstructured=remittance,
    )


def compare_parsed_details(payment, gtx_reference, parsed, expected_amount, expected_date, currency, expected_narrative):
    issues = []

    required_fields = {
        "unit": parsed.unit,
        "to_bic": parsed.to_bic,
        "message_id": parsed.message_id,
        "instruction_id": parsed.instruction_id,
        "end_to_end_id": parsed.end_to_end_id,
        "interbank_ccy": parsed.interbank_ccy,
        "interbank_amount": parsed.interbank_amount,
        "settlement_date": parsed.settlement_date,
        "instructed_ccy": parsed.instructed_ccy,
        "instructed_amount": parsed.instructed_amount,
        "unstructured": parsed.unstructured,
    }
    for field_name, value in required_fields.items():
        if not value:
            issues.append(f"Missing {field_name}")

    if parsed.unit and parsed.unit != payment.get("unit"):
        issues.append(f"Unit mismatch: expected {payment.get('unit')}, found {parsed.unit}")

    expected_bic = expected_to_bic(payment)
    if expected_bic:
        if parsed.to_bic and parsed.to_bic != expected_bic:
            issues.append(f"To BIC mismatch: expected {expected_bic}, found {parsed.to_bic}")
    elif parsed.to_bic:
        issues.append(f"No expected To BIC mapping for {payment.get('source_code')}")

    for field_name, found in (
        ("Message ID", parsed.message_id),
        ("Instruction ID", parsed.instruction_id),
        ("End To End ID", parsed.end_to_end_id),
    ):
        if found and found != gtx_reference:
            issues.append(f"{field_name} mismatch: expected {gtx_reference}, found {found}")

    for field_name, found_currency in (
        ("Interbank currency", parsed.interbank_ccy),
        ("Instructed currency", parsed.instructed_ccy),
    ):
        if found_currency and currency and found_currency != currency:
            issues.append(f"{field_name} mismatch: expected {currency}, found {found_currency}")

    for field_name, found_amount in (
        ("Interbank amount", parsed.interbank_amount),
        ("Instructed amount", parsed.instructed_amount),
    ):
        normalized_found = normalize_amount(found_amount)
        if normalized_found is not None and expected_amount is not None and normalized_found != expected_amount:
            issues.append(f"{field_name} mismatch: expected {expected_amount}, found {normalized_found}")

    found_date = normalize_date(parsed.settlement_date)
    if found_date and expected_date and found_date != expected_date:
        issues.append(f"Settlement date mismatch: expected {expected_date}, found {found_date}")

    if parsed.unstructured:
        expected_compact = compact_text(expected_narrative)
        found_compact = compact_text(parsed.unstructured)
        if expected_compact and not found_compact.startswith(expected_compact):
            issues.append("Unstructured remittance mismatch")

    return AuditResult(
        status="Match" if not issues else "Needs manual review",
        issues=issues,
        parsed=parsed,
    )


def compare_payment_details(payment, gtx_reference, details_text):
    expected_amount = normalize_amount(format_amount(payment.get("amount"), payment.get("source_code")))
    expected_date = normalize_date(payment.get("value_date"))
    currency = expected_currency(payment)
    expected_narrative = build_narrative(payment.get("reference", "CO5590"), payment.get("otr_number", ""))
    if not payment.get("uses_pacs_flow", True):
        return compare_parsed_details(
            payment,
            gtx_reference,
            parse_legacy_payment_details(details_text),
            expected_amount,
            expected_date,
            currency,
            expected_narrative,
        )

    return compare_parsed_details(
        payment,
        gtx_reference,
        parse_payment_details(details_text),
        expected_amount,
        expected_date,
        currency,
        expected_narrative,
    )
