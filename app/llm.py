import os
import json
import logging
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def _call_deepseek(system_prompt: str, user_text: str) -> str:
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]


TENANT_SYSTEM_PROMPT = (
    "Ты — помощник для извлечения данных арендатора из распознанного текста документа. "
    "Извлеки все найденные поля и верни JSON. Если поле не найдено — опусти его.\n\n"
    "Доступные поля:\n"
    '- "type": один из "LEGAL_ENTITY", "ENTREPRENEUR", "INDIVIDUAL"\n'
    '- "name": наименование организации или ФИО\n'
    '- "inn": ИНН (цифры без пробелов)\n'
    '- "kpp": КПП (цифры без пробелов)\n'
    '- "ogrn": ОГРН или ОГРНИП (цифры без пробелов)\n'
    '- "legalAddress": юридический адрес\n'
    '- "phone": телефон\n'
    '- "email": email\n'
    '- "bankName": наименование банка\n'
    '- "bankBik": БИК (цифры без пробелов)\n'
    '- "bankAccount": расчётный счёт (20 цифр без пробелов)\n'
    '- "bankCorrAccount": корреспондентский счёт (20 цифр без пробелов)\n'
    '- "passportSeries": серия паспорта (4 цифры)\n'
    '- "passportNumber": номер паспорта (6 цифр)\n'
    '- "registrationAddress": адрес регистрации\n\n'
    "Верни ТОЛЬКО валидный JSON без markdown-обёрток."
)

PROPERTY_SYSTEM_PROMPT = (
    "Ты — помощник для извлечения данных помещения из распознанного текста документа. "
    "Извлеки все найденные поля и верни JSON. Если поле не найдено — опусти его.\n\n"
    "Доступные поля:\n"
    '- "name": название помещения\n'
    '- "type": один из "OFFICE", "APARTMENT", "COMMERCIAL", "WAREHOUSE", "OTHER"\n'
    '- "address": адрес\n'
    '- "area": площадь (число)\n'
    '- "floor": этаж (число)\n'
    '- "cadastralNumber": кадастровый номер\n\n'
    "Верни ТОЛЬКО валидный JSON без markdown-обёрток."
)


def is_available() -> bool:
    return bool(API_KEY)


def extract_tenant_fields(text: str) -> dict:
    raw = _call_deepseek(TENANT_SYSTEM_PROMPT, text[:4000])
    result = json.loads(raw)
    for key in ("inn", "kpp", "ogrn", "bankBik", "bankAccount", "bankCorrAccount"):
        if key in result and isinstance(result[key], str):
            result[key] = result[key].replace(" ", "").replace("-", "")
    return result


def extract_property_fields(text: str) -> dict:
    raw = _call_deepseek(PROPERTY_SYSTEM_PROMPT, text[:4000])
    result = json.loads(raw)
    if "area" in result and isinstance(result["area"], str):
        result["area"] = float(result["area"].replace(",", ".").replace(" ", ""))
    if "floor" in result and isinstance(result["floor"], str):
        result["floor"] = int(result["floor"])
    return result
