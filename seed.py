#!/usr/bin/env python3
"""Seed the database with initial data using Jinja2 template syntax."""
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.models import engine, users, properties, tenants, contract_templates
from app.auth import hash_password
from sqlalchemy import select, insert
from sqlalchemy.orm import Session


JINJA2_TEMPLATE = """# ДОГОВОР АРЕНДЫ НЕЖИЛОГО ПОМЕЩЕНИЯ №{{ contract.number }}

г. Москва, {{ contract.date }} г.

---

**{{ owner.fullName }}**, далее именуемый «Арендодатель», с одной стороны, и
**{{ tenant.name }}** в лице Генерального директора, действующего на основании Устава,
далее именуемый «Арендатор», с другой стороны, заключили настоящий Договор о нижеследующем:

---

## 1. Предмет договора

1.1. Арендодатель обязуется предоставить Арендатору за плату во временное пользование нежилое помещение,
расположенное по адресу: **{{ property.address }}**,
кадастровый номер: **{{ property.cadastralNumber }}**,
общей площадью **{{ property.area }} м²**{% if property.floor %}, этаж {{ property.floor }}{% endif %}.

## 2. Арендная плата и порядок расчётов

2.1. Ежемесячная арендная плата составляет **{{ terms.rentAmount }} рублей**.

2.2. Арендная плата вносится Арендатором ежемесячно до {{ terms.paymentDay }}-го числа текущего месяца.

{% if terms.depositAmount %}
2.3. Обеспечительный взнос (залог) составляет **{{ terms.depositAmount }} рублей**.
{% endif %}

## 3. Коммунальные платежи

| Услуга | Плательщик |
|--------|-----------|
| Электроэнергия | {{ terms.electricityPayer }} |
| Водоснабжение | {{ terms.waterPayer }} |
| Отопление | {{ terms.heatingPayer }} |
| Уборка | {{ terms.cleaningPayer }} |

## 4. Срок договора

4.1. Настоящий Договор вступает в силу с {{ contract.startDate }} и действует по {{ contract.endDate }}.

## 5. Реквизиты сторон

| Арендодатель | Арендатор |
|-------------|----------|
| {{ owner.fullName }} | **{{ tenant.name }}** |
| | ИНН: {{ tenant.inn }} |
| | {% if tenant.kpp %}КПП: {{ tenant.kpp }}{% endif %} |
| | ОГРН: {{ tenant.ogrn }} |
| | {% if tenant.legalAddress %}Юр. адрес: {{ tenant.legalAddress }}{% endif %} |
| | {% if tenant.bankName %}Банк: {{ tenant.bankName }}{% endif %} |
| | {% if tenant.bankBik %}БИК: {{ tenant.bankBik }}{% endif %} |
| | {% if tenant.bankAccount %}Р/с: {{ tenant.bankAccount }}{% endif %} |
| | {% if tenant.phone %}Тел: {{ tenant.phone }}{% endif %} |

---

| Арендодатель: | Арендатор: |
|-------------|----------|
| _______________ | _______________ |
| {{ owner.fullName }} | {{ tenant.name }} |
"""


def main():
    password_hash = hash_password("admin123")
    now = datetime.now()

    with Session(engine) as db:
        # Admin user
        existing = db.execute(
            select(users).where(users.c.email == "admin@premises.local")
        ).first()
        if not existing:
            db.execute(
                insert(users).values(
                    id=str(uuid.uuid4()),
                    email="admin@premises.local",
                    name="Администратор",
                    passwordHash=password_hash,
                    role="ADMIN",
                    createdAt=now,
                    updatedAt=now,
                )
            )
            print("Admin user created: admin@premises.local")

        # Owner user
        existing = db.execute(
            select(users).where(users.c.email == "owner@premises.local")
        ).first()
        owner_id = existing.id if existing else str(uuid.uuid4())
        if not existing:
            db.execute(
                insert(users).values(
                    id=owner_id,
                    email="owner@premises.local",
                    name="Собственник",
                    passwordHash=password_hash,
                    role="OWNER",
                    createdAt=now,
                    updatedAt=now,
                )
            )
            print("Owner user created: owner@premises.local")

        # Property
        existing_prop = db.execute(
            select(properties).where(properties.c.name == "Офис на Ленина")
        ).first()
        if not existing_prop:
            db.execute(
                insert(properties).values(
                    id=str(uuid.uuid4()),
                    name="Офис на Ленина",
                    type="OFFICE",
                    address="г. Москва, ул. Ленина, д. 15, офис 301",
                    area=45.5,
                    floor=3,
                    cadastralNumber="77:01:0001075:1234",
                    ownerId=owner_id,
                    createdAt=now,
                    updatedAt=now,
                )
            )
            print("Property created: Офис на Ленина")

        # Tenant
        existing_tenant = db.execute(
            select(tenants).where(tenants.c.name == 'ООО "Ромашка"')
        ).first()
        if not existing_tenant:
            db.execute(
                insert(tenants).values(
                    id=str(uuid.uuid4()),
                    type="LEGAL_ENTITY",
                    name='ООО "Ромашка"',
                    inn="7701234567",
                    kpp="770101001",
                    ogrn="1234567890123",
                    legalAddress="г. Москва, ул. Садовая, д. 10",
                    phone="+7 (495) 123-45-67",
                    email="info@romashka.ru",
                    bankName="ПАО Сбербанк",
                    bankBik="044525225",
                    bankAccount="40702810123450123456",
                    bankCorrAccount="30101810400000000225",
                    createdAt=now,
                    updatedAt=now,
                )
            )
            print('Tenant created: ООО "Ромашка"')

        # Contract template (always update to ensure Jinja2 syntax)
        existing_tmpl = db.execute(
            select(contract_templates).where(
                contract_templates.c.name == "Договор аренды офиса (стандартный)"
            )
        ).first()
        if existing_tmpl:
            from sqlalchemy import update
            db.execute(
                update(contract_templates)
                .where(contract_templates.c.id == existing_tmpl.id)
                .values(htmlContent=JINJA2_TEMPLATE, updatedAt=now)
            )
            print("Template updated with Jinja2 syntax")
        else:
            db.execute(
                insert(contract_templates).values(
                    id=str(uuid.uuid4()),
                    name="Договор аренды офиса (стандартный)",
                    description="Стандартный договор аренды офисного помещения",
                    htmlContent=JINJA2_TEMPLATE,
                    version=1,
                    isActive=True,
                    createdAt=now,
                    updatedAt=now,
                )
            )
            print("Template created: Договор аренды офиса (стандартный)")

        db.commit()
        print("\nSeed complete!")


if __name__ == "__main__":
    main()
