import io
import re
import logging

log = logging.getLogger(__name__)


def detect_format(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("pdf",):
        return "pdf"
    if ext in ("docx",):
        return "docx"
    if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif"):
        return "image"
    return "unknown"


def extract_text(file_bytes: bytes, filename: str) -> str:
    fmt = detect_format(filename)
    if fmt == "pdf":
        return _pdf(file_bytes)
    if fmt == "docx":
        return _docx(file_bytes)
    if fmt == "image":
        return _ocr(file_bytes)
    return ""


def _pdf(file_bytes: bytes) -> str:
    import fitz

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = ""
    try:
        for page in doc:
            text += page.get_text()
        if len(text.strip()) < 30:
            text = ""
            for page in doc:
                pix = page.get_pixmap(dpi=250)
                img_data = pix.tobytes("png")
                text += _ocr(img_data) + "\n"
    finally:
        doc.close()
    return text


def _docx(file_bytes: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    parts = []
    for p in doc.paragraphs:
        parts.append(p.text)
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text for cell in row.cells)
            parts.append(row_text)
    return "\n".join(parts)


def _ocr(file_bytes: bytes) -> str:
    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(img, lang="rus+eng")


# ── field extraction ────────────────────────────────────────


def parse_fields(raw_text: str) -> dict:
    result = {}
    t = _clean(raw_text)

    result.update(_extract_cadastral(t))
    result.update(_extract_area(t))
    result.update(_extract_floor(t))
    result.update(_extract_address(t, raw_text))
    result.update(_extract_type(t))
    result.update(_extract_name(t, result))
    result.update(_extract_owner_info(t))

    return result


def _clean(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


# ── individual extractors ───────────────────────────────────

_CAD_PATTERNS = [
    re.compile(
        r"(?:кад(?:астровый|астров|\.)\s+(?:номер|№|н\.|знак)|КН)\s*[:]?\s*(\d{1,3}:\d{1,3}:\d{4,12}:\d{1,10})",
        re.I,
    ),
    re.compile(r"(\d{2}:\d{2}:\d{6,10}:\d{1,6})"),
]


def _extract_cadastral(text: str) -> dict:
    for pat in _CAD_PATTERNS:
        m = pat.search(text)
        if m:
            return {"cadastralNumber": m.group(1).strip()}
    return {}


_AREA_PATTERNS = [
    re.compile(
        r"площад[ьи]+\s*(?:помещения|объекта|здания|застройки)?\s*[:]?\s*"
        r"(\d+[.,]?\d*)\s*(?:кв[.]?\s*м[.]?|м[²2]|㎡|квм)?",
        re.I,
    ),
    re.compile(r"общ[ая]+\s*площад[ьи]*\s*[:]?\s*(\d+[.,]?\d*)", re.I),
]


def _extract_area(text: str) -> dict:
    for pat in _AREA_PATTERNS:
        m = pat.search(text)
        if m:
            area_str = m.group(1).replace(",", ".")
            try:
                return {"area": float(area_str)}
            except ValueError:
                pass
    return {}


_FLOOR_PATTERNS = [
    re.compile(r"этаж\s*(?:ность|№|номер)?\s*[:]?\s*(\d+)", re.I),
    re.compile(r"(?:расположен[ао]?\s+на|находится\s+на)\s+(\d+)\s*(?:-?м|ом)?\s*этаж", re.I),
]


def _extract_floor(text: str) -> dict:
    for pat in _FLOOR_PATTERNS:
        m = pat.search(text)
        if m:
            return {"floor": int(m.group(1))}
    return {}


_ADDR_PATTERNS = [
    re.compile(r"адрес\s*(?:\(местоположение\))?\s*[:]?\s*(.*?)(?:\n|Кадастровый|Площадь|Назначение|$)", re.I | re.S),
    re.compile(r"местоположение\s*[:]?\s*(.*?)(?:\n|Кадастровый|Площадь|$)", re.I | re.S),
    re.compile(r"местонахождение\s*[:]?\s*(.*?)(?:\n|Кадастровый|Площадь|$)", re.I | re.S),
]


def _extract_address(text: str, raw: str) -> dict:
    for pat in _ADDR_PATTERNS:
        m = pat.search(text)
        if m:
            addr = m.group(1).strip().rstrip(".,;: ")
            addr = re.sub(r"\s+", " ", addr)
            if len(addr) > 5:
                return {"address": addr}
    # Fallback: search for typical Russian address patterns
    city = re.search(r"г[.]\s*([А-ЯЁ][а-яё\s\-]+?)(?:[,]|\s+ул|\s+пр|\s+пер|\s+ш\.)", text)
    if city:
        idx = text.lower().find(city.group(0).lower())
        addr = text[idx:].split("\n")[0].strip().rstrip(".,;: ")
        if len(addr) > 5:
            return {"address": addr}
    return {}


_TYPE_MAP = [
    ("OFFICE", [r"офис", r"офисн", r"административн", r"контор", r"кабинет"]),
    ("APARTMENT", [r"квартир", r"апартамент", r"жилое\s*помещение", r"жилое\s*здание"]),
    ("COMMERCIAL", [r"коммерч", r"торгов", r"магазин", r"нежилое\s*помещение", r"нежилое\s*здание",
                    r"общепит", r"кафе", r"ресторан", r"гостиниц"]),
    ("WAREHOUSE", [r"склад", r"складск", r"ангар", r"бокс", r"гараж"]),
]


def _extract_type(text: str) -> dict:
    t = text.lower()
    for ptype, keywords in _TYPE_MAP:
        for kw in keywords:
            if re.search(kw, t):
                return {"type": ptype}
    # Default from assignment/naznachenie
    naz_match = re.search(r"назначение\s*[:]?\s*(.*?)(?:\n|$)", text, re.I)
    if naz_match:
        nazn = naz_match.group(1).strip().lower()
        for ptype, keywords in _TYPE_MAP:
            for kw in keywords:
                if re.search(kw, nazn):
                    return {"type": ptype}
    return {}


_NAME_PATTERNS = [
    re.compile(r"(?:наименование|название)\s*(?:объекта|помещения|здания)?\s*[:]?\s*(.*?)(?:\n|$)", re.I),
    re.compile(r"вид\s*объекта\s*(?:недвижимости)?\s*[:]?\s*(.*?)(?:\n|$)", re.I),
]


def _extract_name(text: str, existing: dict) -> dict:
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip().rstrip(".,;: ")
            if len(name) > 1:
                return {"name": name}
    # Generate fallback name from type + address
    if "name" not in existing:
        type_names = {
            "OFFICE": "Офис",
            "APARTMENT": "Квартира",
            "COMMERCIAL": "Коммерческое помещение",
            "WAREHOUSE": "Склад",
        }
        prefix = type_names.get(existing.get("type", ""), "Помещение")
        addr = existing.get("address", "")
        if addr:
            return {"name": f"{prefix}, {addr[:60]}"}
    return {}


def _extract_owner_info(text: str) -> dict:
    # Some documents contain ownership info that might help set isPersonal
    owner_pat = re.compile(
        r"(?:собственник|правообладатель|владелец)\s*[:]?\s*(.*?)(?:\n|$)", re.I
    )
    m = owner_pat.search(text)
    if m:
        owner_name = m.group(1).strip().rstrip(".,;: ")
        # If it looks like an individual (contains name), suggest personal
        # but we don't auto-set checkbox
        pass
    return {}
