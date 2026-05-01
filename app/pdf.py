import os
from datetime import datetime
from jinja2 import Template
import markdown as md_lib


def render_contract_html(content: str, data: dict) -> str:
    """Render template content (Markdown or HTML) with Jinja2 data."""
    template = Template(content)
    filled = template.render(**data)

    # If content looks like Markdown, convert to HTML
    stripped = content.strip()
    if stripped.startswith("#") or stripped.startswith("**") or "\n#" in stripped[:200]:
        filled = md_lib.markdown(filled, extensions=["tables", "fenced_code", "nl2br"])

    return filled


def render_preview(content: str, data: dict) -> str:
    """For live preview: always render markdown→HTML."""
    template = Template(content)
    filled = template.render(**data)
    return md_lib.markdown(filled, extensions=["tables", "fenced_code", "nl2br"])


def generate_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


def build_template_data(contract_data, template, property_, tenant, owner):
    terms = contract_data.get("terms", {}) or {}

    return {
        "contract": {
            "number": contract_data.get("number", ""),
            "date": datetime.now().strftime("%d.%m.%Y"),
            "startDate": _fmt_date(contract_data.get("startDate")),
            "endDate": _fmt_date(contract_data.get("endDate")),
        },
        "owner": {
            "fullName": owner.name if owner else "",
            "inn": "",
            "passport": "",
        },
        "tenant": {
            "name": tenant.name if tenant else "",
            "inn": tenant.inn or "",
            "kpp": tenant.kpp or "",
            "ogrn": tenant.ogrn or "",
            "legalAddress": tenant.legalAddress or "",
            "passport": _tenant_passport(tenant),
            "registrationAddress": tenant.registrationAddress or "",
            "bankName": tenant.bankName or "",
            "bankBik": tenant.bankBik or "",
            "bankAccount": tenant.bankAccount or "",
            "bankCorrAccount": tenant.bankCorrAccount or "",
            "phone": tenant.phone or "",
            "email": tenant.email or "",
        },
        "property": {
            "address": property_.address if property_ else "",
            "area": str(property_.area) if property_ else "",
            "cadastralNumber": property_.cadastralNumber or "",
            "floor": str(property_.floor) if property_ and property_.floor else "",
        },
        "terms": {
            "rentAmount": _fmt_money(contract_data.get("rentAmount")),
            "depositAmount": _fmt_money(contract_data.get("depositAmount")),
            "paymentDay": contract_data.get("paymentDay", ""),
            "electricityPayer": _payer(terms.get("electricityPayer")),
            "waterPayer": _payer(terms.get("waterPayer")),
            "heatingPayer": _payer(terms.get("heatingPayer")),
            "cleaningPayer": _payer(terms.get("cleaningPayer")),
        },
    }


def _fmt_date(val):
    if not val:
        return ""
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            return val
    if isinstance(val, datetime):
        return val.strftime("%d.%m.%Y")
    return str(val)


def _fmt_money(val):
    if val is None or val == "":
        return ""
    try:
        return f"{float(val):,.0f}".replace(",", " ")
    except (ValueError, TypeError):
        return str(val)


def _payer(val):
    return "Арендатор" if val == "TENANT" else "Арендодатель"


def _tenant_passport(tenant):
    if tenant is None:
        return ""
    parts = [
        tenant.passportSeries,
        tenant.passportNumber,
        tenant.passportIssuedBy,
    ]
    if tenant.passportIssuedDate:
        parts.append(_fmt_date(tenant.passportIssuedDate))
    return " ".join(p for p in parts if p)
