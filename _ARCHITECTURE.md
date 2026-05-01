# Premises Web — Архитектура

Система управления недвижимостью и генерации договоров аренды.

## Серверное окружение

| Параметр | Значение |
|---|---|
| ОС | Ubuntu 24.04, Linux 6.8 |
| RAM | 2 ГБ (+ 9 ГБ swap) |
| Диск | 58 ГБ (19 занято) |
| База данных | PostgreSQL 16 |
| Reverse proxy | Caddy (порты 80/443) |
| Python | 3.12.3 |
| WSGI-сервер | Gunicorn (порт 3000) |

---

## Стек технологий

| Слой | Технология | Обоснование |
|---|---|---|
| Фреймворк | **Flask 3 + Jinja2** | SSR, простота, отсутствие build-степа |
| База данных | **PostgreSQL 16** | Уже установлен, отражение через SQLAlchemy Core |
| ORM | **SQLAlchemy Core (reflect)** | Работа с существующей БД без миграций на Python-стороне |
| Аутентификация | **Flask-Login** | Сессии через signed cookies |
| Стилизация | **Vanilla CSS** | ~500 строк, никаких сборщиков |
| PDF-генерация | **WeasyPrint** | HTML → PDF, поддержка CSS для печати |
| Шаблоны договоров | **Markdown + Jinja2** | Редактирование в EasyMDE, рендер через Python-markdown |
| Хеширование | **bcrypt** | Для паролей |
| Загрузка файлов | **Flask + Pillow** | Мультизагрузка фото/документов, авто-генерация thumbnail |
| Редактор Markdown | **EasyMDE (CDN)** | Без сборки, без npm |

---

## Модель данных

### Users (пользователи системы)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID | Первичный ключ |
| email | String (unique) | Email для входа |
| name | String | Имя пользователя |
| passwordHash | String | Хеш пароля (bcrypt) |
| role | Enum: ADMIN, OWNER, ACCOUNTANT, VIEWER | Роль в системе |
| createdAt | DateTime | Дата создания |
| updatedAt | DateTime | Дата обновления |

Роли:
- **ADMIN** — полный доступ ко всему
- **OWNER** — управление своей недвижимостью и договорами
- **ACCOUNTANT** — просмотр финансовых данных, ограниченный доступ к недвижимости
- **VIEWER** — только чтение

### Properties (помещения)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID | Первичный ключ |
| name | String | Краткое название |
| type | Enum: OFFICE, APARTMENT, COMMERCIAL, WAREHOUSE, OTHER | Тип помещения |
| cadastralNumber | String? | Кадастровый номер |
| address | String | Полный адрес |
| area | Float | Площадь в м² |
| floor | Int? | Этаж |
| rosreestrData | JSONB | Данные из Росреестра |
| ownerId | UUID → Users | Собственник |
| isPersonal | Boolean | true = личная недвижимость (не видна бухгалтеру) |
| photoUrls | Text? | JSON-массив URL загруженных фото |
| documentUrls | Text? | JSON-массив URL загруженных документов |
| createdAt | DateTime | |
| updatedAt | DateTime | |

**Загрузка файлов:**
- Файлы сохраняются в `public/uploads/properties/{propertyId}/{photos|documents}/`
- При загрузке изображений автоматически генерируется thumbnail (300×200, `_thumb` суффикс)
- Документы: PDF, JPG, PNG (фильтрация по расширению)

### Tenants (арендаторы)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID | |
| type | Enum: LEGAL_ENTITY, ENTREPRENEUR, INDIVIDUAL | Тип арендатора |
| name | String | Наименование / ФИО |
| inn | String? | ИНН |
| kpp | String? | КПП (для ЮЛ) |
| ogrn | String? | ОГРН / ОГРНИП |
| legalAddress | String? | Юридический адрес |
| passportSeries | String? | Серия паспорта |
| passportNumber | String? | Номер паспорта |
| passportIssuedBy | String? | Кем выдан |
| passportIssuedDate | Date? | Дата выдачи |
| registrationAddress | String? | Адрес регистрации |
| phone | String? | Телефон |
| email | String? | Email |
| bankName | String? | Банк |
| bankBik | String? | БИК |
| bankAccount | String? | Расчётный счёт |
| bankCorrAccount | String? | Корреспондентский счёт |
| createdAt | DateTime | |
| updatedAt | DateTime | |

### ContractTemplates (шаблоны договоров)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID | |
| name | String | Название шаблона |
| description | String? | Описание |
| htmlContent | Text | Markdown с Jinja2-плейсхолдерами |
| version | Int | Версия |
| isActive | Boolean | Активен ли |
| createdAt | DateTime | |
| updatedAt | DateTime | |

### Contracts (договоры)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID | |
| number | String | Номер договора |
| templateId | UUID → ContractTemplates | Шаблон |
| propertyId | UUID → Properties | Помещение |
| tenantId | UUID → Tenants | Арендатор |
| ownerId | UUID → Users | Собственник |
| startDate | Date | Дата начала |
| endDate | Date | Дата окончания |
| rentAmount | Decimal | Сумма аренды |
| depositAmount | Decimal? | Залог |
| paymentDay | Int? | День оплаты |
| terms | JSONB | Условия: кто платит за свет, воду, уборку |
| status | Enum: DRAFT, ACTIVE, EXPIRED, TERMINATED | Статус |
| pdfUrl | String? | Путь к сгенерированному PDF |
| signedAt | DateTime? | Дата подписания |
| createdAt | DateTime | |
| updatedAt | DateTime | |

Структура `terms` JSONB:
```json
{
  "electricityPayer": "TENANT",
  "waterPayer": "OWNER",
  "heatingPayer": "OWNER",
  "cleaningPayer": "TENANT"
}
```

### MeterReadings (показания счётчиков — не используются)

### Expenses (расходы — не используются)

---

## Структура проекта

```
premises-web/
├── app/
│   ├── __init__.py          # create_app(), Flask-Login, фильтры Jinja2, роуты раздачи файлов
│   ├── models.py            # SQLAlchemy reflect(), scoped_session
│   ├── auth.py              # hash_password, verify_password, role_required
│   ├── routes.py            # ВСЕ роуты: dashboard, CRUD properties/tenants/contracts/templates, settings
│   └── pdf.py               # render_contract_html(), render_preview(), generate_pdf()
├── templates/
│   ├── base.html            # Навигация + flash-сообщения
│   ├── login.html
│   ├── dashboard.html
│   ├── properties.html      # Список помещений (карточки с thumbnail)
│   ├── property_form.html   # Форма CRUD + загрузка файлов + Ctrl+V вставка
│   ├── tenants.html, tenant_form.html
│   ├── contracts.html, contract_form.html, contract_created.html
│   ├── contract_templates.html, template_form.html
│   └── settings.html
├── static/
│   └── style.css            # Вся стилизация
├── public/
│   ├── contracts/           # Сгенерированные PDF
│   └── uploads/properties/  # Загруженные фото и документы
├── seed.py                  # Сидирование БД
├── run.py                   # Dev-сервер (Flask debug)
├── .env                     # DATABASE_URL, NEXTAUTH_SECRET
├── premises-web-flask.service  # systemd unit для gunicorn
└── ARCHITECTURE.md
```

---

## Pipeline генерации договора

1. **Шаблон из БД** — Markdown с Jinja2-плейсхолдерами (`{{ contract.number }}`, `{% if terms.depositAmount %}...`)
2. **Jinja2.render(data)** → Markdown с подставленными значениями
3. **Python-markdown** → HTML (extensions: tables, fenced_code, nl2br)
4. **WeasyPrint.HTML(string=html).write_pdf()** → PDF-байты
5. **Сохранение** в `public/contracts/` + запись `pdfUrl` в БД

---

## Плейсхолдеры в шаблонах

| Плейсхолдер | Значение |
|---|---|
| `{{ contract.number }}` | Номер договора |
| `{{ contract.date }}` | Дата договора |
| `{{ contract.startDate }}` | Дата начала |
| `{{ contract.endDate }}` | Дата окончания |
| `{{ owner.fullName }}` | ФИО собственника |
| `{{ owner.inn }}` | ИНН собственника |
| `{{ owner.passport }}` | Паспорт собственника |
| `{{ tenant.name }}` | Арендатор |
| `{{ tenant.inn }}` | ИНН арендатора |
| `{{ tenant.kpp }}` | КПП |
| `{{ tenant.ogrn }}` | ОГРН |
| `{{ tenant.legalAddress }}` | Юр. адрес |
| `{{ tenant.passport }}` | Паспортные данные |
| `{{ tenant.bankName }}` | Банк |
| `{{ tenant.bankAccount }}` | Расчётный счёт |
| `{{ tenant.bankBik }}` | БИК |
| `{{ tenant.bankCorrAccount }}` | Корр. счёт |
| `{{ tenant.phone }}` | Телефон |
| `{{ tenant.email }}` | Email |
| `{{ property.address }}` | Адрес помещения |
| `{{ property.cadastralNumber }}` | Кадастровый номер |
| `{{ property.area }}` | Площадь |
| `{{ property.floor }}` | Этаж |
| `{{ terms.rentAmount }}` | Сумма аренды |
| `{{ terms.depositAmount }}` | Залог |
| `{{ terms.paymentDay }}` | День оплаты |
| `{{ terms.electricityPayer }}` | Кто платит за электричество |
| `{{ terms.waterPayer }}` | Кто платит за воду |
| `{{ terms.heatingPayer }}` | Кто платит за отопление |
| `{{ terms.cleaningPayer }}` | Кто платит за уборку |

---

## Загрузка файлов

### Фотографии

- Поле `photos` (multiple, accept="image/*")
- Зона вставки `Ctrl+V` — vanilla JS через `DataTransfer`
- При сохранении: Pillow генерирует thumbnail 300×200 (`_thumb` суффикс)
- В списке properties: `<img src="{{ url|thumb_url }}">`
- При клике: открывается оригинал в новой вкладке

### Документы

- Поле `documents` (multiple, accept=".pdf,.jpg,.jpeg,.png")
- Без thumbnail
- Отображаются как ссылки с именем файла

### Хранение

```
public/uploads/properties/
├── {propertyId}/
│   ├── photos/
│   │   ├── {uuid}.jpg           # оригинал
│   │   └── {uuid}_thumb.jpg     # thumbnail
│   └── documents/
│       └── {uuid}.pdf
```

---

## Развёртывание

### Dev-сервер

```bash
systemctl stop premises-web
.venv/bin/python run.py    # порт 3000, автоперезагрузка
```

### Продакшен

```bash
systemctl start premises-web   # gunicorn, 2 workers
```

systemd unit (`/etc/systemd/system/premises-web.service`):
```ini
[Unit]
Description=Premises Web App (Flask)
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/srv/premises-web
ExecStart=/srv/premises-web/.venv/bin/gunicorn --bind 0.0.0.0:3000 --workers 2 --timeout 120 "app:create_app()"
Environment=PATH=/srv/premises-web/.venv/bin:/usr/bin
Environment=DATABASE_URL=postgresql://...
Environment=NEXTAUTH_SECRET=...
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Caddy:
```
premises.example.com {
    reverse_proxy localhost:3000
}
```

---

## Jinja2 фильтры

| Фильтр | Описание |
|---|---|
| `from_json` | Парсит JSON-строку в объект (для photoUrls/documentUrls) |
| `thumb_url` | Добавляет `_thumb` перед расширением URL (для thumbnail) |

---

## Фазы реализации

### Фаза 1: MVP — Генерация договоров ✅
- [x] Flask + SQLAlchemy + Jinja2
- [x] Схема БД: Users, Properties, Tenants, Contracts, ContractTemplates
- [x] Flask-Login с ролями
- [x] CRUD помещений, арендаторов, шаблонов
- [x] Двухпанельный редактор договоров (live preview)
- [x] Генерация PDF из Markdown-шаблонов
- [x] Загрузка фото и документов к помещениям

### Фаза 2: Мультипользовательская система
- [x] RBAC (роли: ADMIN, OWNER, ACCOUNTANT, VIEWER)
- [x] Фильтрация isPersonal для бухгалтера
- [ ] Скрытие кнопок по ролям в UI

### Фаза 3: Учёт расходов и показаний
- [ ] MeterReadings, Expenses — CRUD
- [ ] Дашборд с графиками

### Фаза 4: Telegram-бот
- [ ] Команда `/meter` для подачи показаний
- [ ] Уведомления о сроках договоров
