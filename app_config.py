import copy
import json
import os


DEFAULT_FUNDING_REFERENCE = "CO5590"
APP_CONFIG_DIR = ".ap_funding_payment_automation"
APP_CONFIG_FILE = "settings.json"

DEFAULT_APPROVAL_RULES = [
    {"template": "APAUDPACS", "to_bic": "NATAAU3302S", "flow": "PACS", "owning_unit": "TGBP"},
    {"template": "APCHFPACS", "to_bic": "BOFACH2XXXX", "flow": "PACS", "owning_unit": "TGBP"},
    {"template": "EURPMTAP2PACS", "to_bic": "BBRUBEBB010", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APHKDPACS", "to_bic": "BOFAHKHXXXX", "flow": "PACS", "owning_unit": "TGBP"},
    {"template": "APJPYPACS", "to_bic": "IRVTUS3NXXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APGBPPACS", "to_bic": "BARCGB22XXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APGBPPACS2", "to_bic": "BARCGB22XXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APUSDPACS", "to_bic": "IRVTUS3NXXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APCADPACS", "to_bic": "BOFMCAM2XXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APNZDPACS", "to_bic": "BOFAAUSXXXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APSGDPACS", "to_bic": "BOFASG2XXXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
    {"template": "APFUNDINGCZK", "to_bic": "CEKOCZPPXXX", "flow": "MT101", "owning_unit": "CCT_CHUK"},
    {"template": "APPLNPACS", "to_bic": "BARCGB22XXX", "flow": "PACS", "owning_unit": "CCT_CHUK"},
]


def parse_funding_reference(value):
    text = str(value or "").strip()
    if text.lower().startswith("funding "):
        text = text[8:].strip()
    return text or DEFAULT_FUNDING_REFERENCE


def display_funding_reference(value):
    return f"Funding {parse_funding_reference(value)}"


def config_dir(home_dir=None):
    return os.path.join(home_dir or os.path.expanduser("~"), APP_CONFIG_DIR)


def settings_path(home_dir=None):
    return os.path.join(config_dir(home_dir), APP_CONFIG_FILE)


def default_settings(home_dir=None):
    home = home_dir or os.path.expanduser("~")
    return {
        "browser_path": "",
        "output_folder": os.path.join(home, "Downloads"),
        "funding_reference": DEFAULT_FUNDING_REFERENCE,
        "approval_rules": copy.deepcopy(DEFAULT_APPROVAL_RULES),
    }


def _normalized_approval_rules(value):
    defaults_by_template = {
        rule["template"]: rule for rule in copy.deepcopy(DEFAULT_APPROVAL_RULES)
    }
    rules = []
    if isinstance(value, list):
        for raw_rule in value:
            if not isinstance(raw_rule, dict):
                continue
            template = str(raw_rule.get("template") or "").strip().upper()
            if not template:
                continue
            default_rule = defaults_by_template.get(template, {})
            rules.append({
                "template": template,
                "to_bic": str(raw_rule.get("to_bic") or "").strip().upper(),
                "flow": str(raw_rule.get("flow") or "").strip().upper(),
                "owning_unit": str(
                    raw_rule.get("owning_unit") or default_rule.get("owning_unit") or ""
                ).strip().upper(),
            })
            defaults_by_template.pop(template, None)

    rules.extend(defaults_by_template.values())
    return rules


def normalize_settings(raw_settings=None, home_dir=None):
    settings = default_settings(home_dir)
    raw = raw_settings if isinstance(raw_settings, dict) else {}

    for key in ("browser_path", "output_folder", "funding_reference"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            settings[key] = value.strip()

    settings["approval_rules"] = _normalized_approval_rules(raw.get("approval_rules"))
    return settings


def load_settings(path=None, home_dir=None):
    target_path = path or settings_path(home_dir)
    try:
        with open(target_path, "r", encoding="utf-8") as settings_file:
            raw_settings = json.load(settings_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw_settings = {}
    return normalize_settings(raw_settings, home_dir)


def save_settings(settings, path=None, home_dir=None):
    normalized = normalize_settings(settings, home_dir)
    target_path = path or settings_path(home_dir)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as settings_file:
        json.dump(normalized, settings_file, indent=2)
    return normalized


def approval_bic_mapping(settings):
    normalized = normalize_settings(settings)
    return {
        rule["template"]: rule["to_bic"]
        for rule in normalized["approval_rules"]
        if rule.get("template") and rule.get("to_bic")
    }
