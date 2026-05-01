import os
import json
import uuid
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session as flask_session,
)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import select, insert, update, delete, func, and_, or_
from app.models import (
    SessionLocal,
    users,
    properties,
    tenants,
    contracts,
    contract_templates,
)
from app.auth import hash_password, verify_password, role_required
from app.pdf import render_contract_html, generate_pdf, build_template_data
from app.ocr import extract_text, parse_fields
from flask_login import UserMixin

routes_bp = Blueprint("routes", __name__)


class UserProxy(UserMixin):
    def __init__(self, row):
        self.id = row.id
        self.email = row.email
        self.name = row.name
        self.role = row.role


# ── helpers ──────────────────────────────────────────────


def db():
    return SessionLocal()


def roles_for(*roles):
    """Role-based access decorator that redirects on failure."""
    from functools import wraps
    from flask_login import current_user

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("routes.login_page"))
            if current_user.role not in roles:
                flash("Доступ запрещён", "error")
                return redirect(url_for("routes.dashboard"))
            return f(*args, **kwargs)

        return wrapped

    return decorator


def roles_for_form(*roles):
    """For POST routes that need role check and return to referrer."""
    from functools import wraps
    from flask_login import current_user

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("routes.login_page"))
            if current_user.role not in roles:
                flash("Доступ запрещён", "error")
                return redirect(url_for("routes.dashboard"))
            return f(*args, **kwargs)

        return wrapped

    return decorator


# ── auth ──────────────────────────────────────────────────


@routes_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("routes.dashboard"))
    return redirect(url_for("routes.login_page"))


@routes_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("routes.dashboard"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        d = db()
        try:
            row = d.execute(
                select(users).where(func.lower(users.c.email) == email.lower())
            ).first()

            if row and verify_password(password, row.passwordHash):
                login_user(UserProxy(row))
                flash("Добро пожаловать!", "success")
                return redirect(url_for("routes.dashboard"))
            else:
                error = "Неверный email или пароль"
        finally:
            d.close()

    return render_template("login.html", error=error)


@routes_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("routes.login_page"))


# ── dashboard ─────────────────────────────────────────────


@routes_bp.route("/dashboard")
@login_required
def dashboard():
    d = db()
    try:
        property_count = d.execute(select(func.count()).select_from(properties)).scalar()
        tenant_count = d.execute(select(func.count()).select_from(tenants)).scalar()
        contract_count = d.execute(select(func.count()).select_from(contracts)).scalar()
        active_count = d.execute(
            select(func.count())
            .select_from(contracts)
            .where(contracts.c.status == "ACTIVE")
        ).scalar()
        template_count = d.execute(
            select(func.count())
            .select_from(contract_templates)
            .where(contract_templates.c.isActive == True)
        ).scalar()

        recent = d.execute(
            select(contracts)
            .order_by(contracts.c.createdAt.desc())
            .limit(5)
        ).fetchall()

        # Resolve tenant/property names for recent contracts
        recent_data = []
        for c in recent:
            t = d.execute(select(tenants).where(tenants.c.id == c.tenantId)).first()
            p = d.execute(select(properties).where(properties.c.id == c.propertyId)).first()
            recent_data.append(
                {
                    "id": c.id,
                    "number": c.number,
                    "createdAt": c.createdAt,
                    "tenant": t.name if t else "—",
                    "property": p.name if p else "—",
                }
            )

    finally:
        d.close()

    stats = [
        {"title": "Помещений", "value": property_count},
        {"title": "Арендаторов", "value": tenant_count},
        {"title": "Договоров", "value": contract_count},
        {"title": "Активных договоров", "value": active_count},
        {"title": "Шаблонов", "value": template_count},
    ]

    return render_template(
        "dashboard.html", stats=stats, recent_contracts=recent_data
    )


# ── properties ────────────────────────────────────────────


@routes_bp.route("/properties")
@login_required
def properties_list():
    d = db()
    try:
        rows = d.execute(
            select(properties).order_by(properties.c.createdAt.desc())
        ).fetchall()

        # join owners and contracts
        prop_data = []
        for p in rows:
            owner = d.execute(select(users).where(users.c.id == p.ownerId)).first()
            photo_urls = json.loads(p.photoUrls) if p.photoUrls else []
            thumbnail_url = None
            if photo_urls:
                first = photo_urls[0]
                base, ext = os.path.splitext(first)
                thumb = f"{base}_thumb{ext}"
                thumbnail_url = thumb if os.path.isfile(os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "public", thumb.lstrip("/")
                )) else first
            
            # Fetch contracts for this property
            prop_contracts = d.execute(
                select(contracts).where(contracts.c.propertyId == p.id).order_by(contracts.c.createdAt.desc())
            ).fetchall()
            
            contract_data = []
            for c in prop_contracts:
                tenant = d.execute(select(tenants).where(tenants.c.id == c.tenantId)).first()
                contract_data.append({
                    "id": c.id,
                    "number": c.number,
                    "status": c.status,
                    "startDate": c.startDate,
                    "endDate": c.endDate,
                    "rentAmount": float(c.rentAmount) if c.rentAmount else 0,
                    "tenant": tenant.name if tenant else "—",
                })
            
            prop_data.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "type": p.type,
                    "address": p.address,
                    "area": p.area,
                    "floor": p.floor,
                    "cadastralNumber": p.cadastralNumber,
                    "isPersonal": p.isPersonal,
                    "ownerId": p.ownerId,
                    "owner": owner.name if owner else "—",
                    "photoUrls": photo_urls,
                    "documentUrls": json.loads(p.documentUrls) if p.documentUrls else [],
                    "thumbnailUrl": thumbnail_url,
                    "contracts": contract_data,
                }
            )

        # group by owner, sort by area desc within each group
        groups = {}
        for p in prop_data:
            key = p["owner"] or "Без собственника"
            groups.setdefault(key, []).append(p)
        for g in groups.values():
            g.sort(key=lambda x: x["area"], reverse=True)
        # sort groups alphabetically by owner name
        groups_sorted = sorted(groups.items(), key=lambda x: x[0])
    finally:
        d.close()

    type_labels = {
        "OFFICE": "Офис",
        "APARTMENT": "Квартира",
        "COMMERCIAL": "Коммерческое",
        "WAREHOUSE": "Склад",
        "OTHER": "Прочее",
    }
    return render_template(
        "properties.html", groups=groups_sorted, type_labels=type_labels
    )


@routes_bp.route("/properties/new", methods=["GET", "POST"])
@login_required
@roles_for("ADMIN", "OWNER")
def property_create():
    if request.method == "POST":
        d = db()
        try:
            pid = str(uuid.uuid4())
            area_str = request.form.get("area", "0")
            floor_str = request.form.get("floor", "")

            photo_urls = _save_uploads(request.files.getlist("photos"), pid, "photos")
            document_urls = _save_uploads(request.files.getlist("documents"), pid, "documents")

            d.execute(
                insert(properties).values(
                    id=pid,
                    name=request.form.get("name", ""),
                    type=request.form.get("type", "OFFICE"),
                    address=request.form.get("address", ""),
                    area=float(area_str) if area_str else 0,
                    floor=int(floor_str) if floor_str else None,
                    cadastralNumber=request.form.get("cadastralNumber") or None,
                    isPersonal=request.form.get("isPersonal") == "on",
                    ownerId=request.form.get("ownerId") or current_user.id,
                    photoUrls=json.dumps(photo_urls) if photo_urls else None,
                    documentUrls=json.dumps(document_urls) if document_urls else None,
                    createdAt=datetime.now(),
                    updatedAt=datetime.now(),
                )
            )
            d.commit()
            flash("Помещение добавлено", "success")
        except Exception as e:
            d.rollback()
            flash(f"Ошибка: {e}", "error")
        finally:
            d.close()
        return redirect(url_for("routes.properties_list"))

    owners = _get_users(db())
    return render_template("property_form.html", property=None, owners=owners, type_labels={
        "OFFICE": "Офис", "APARTMENT": "Квартира", "COMMERCIAL": "Коммерческое",
        "WAREHOUSE": "Склад", "OTHER": "Прочее",
    })


@routes_bp.route("/properties/<pid>/edit", methods=["GET", "POST"])
@login_required
@roles_for("ADMIN", "OWNER")
def property_edit(pid):
    d = db()
    try:
        prop = d.execute(select(properties).where(properties.c.id == pid)).first()
        if not prop:
            flash("Помещение не найдено", "error")
            return redirect(url_for("routes.properties_list"))

        if request.method == "POST":
            area_str = request.form.get("area", "0")
            floor_str = request.form.get("floor", "")

            existing_photos = json.loads(prop.photoUrls) if prop.photoUrls else []
            existing_docs = json.loads(prop.documentUrls) if prop.documentUrls else []
            new_photos = _save_uploads(request.files.getlist("photos"), pid, "photos")
            new_docs = _save_uploads(request.files.getlist("documents"), pid, "documents")

            d.execute(
                update(properties)
                .where(properties.c.id == pid)
                .values(
                    name=request.form.get("name", ""),
                    type=request.form.get("type", "OFFICE"),
                    address=request.form.get("address", ""),
                    area=float(area_str) if area_str else 0,
                    floor=int(floor_str) if floor_str else None,
                    cadastralNumber=request.form.get("cadastralNumber") or None,
                    isPersonal=request.form.get("isPersonal") == "on",
                    ownerId=request.form.get("ownerId") or current_user.id,
                    photoUrls=json.dumps(existing_photos + new_photos) if (existing_photos or new_photos) else None,
                    documentUrls=json.dumps(existing_docs + new_docs) if (existing_docs or new_docs) else None,
                    updatedAt=datetime.now(),
                )
            )
            d.commit()
            flash("Помещение обновлено", "success")
            d.close()
            return redirect(url_for("routes.properties_list"))

        owners = _get_users(d)
        return render_template("property_form.html", property=prop, owners=owners, type_labels={
            "OFFICE": "Офис", "APARTMENT": "Квартира", "COMMERCIAL": "Коммерческое",
            "WAREHOUSE": "Склад", "OTHER": "Прочее",
        })
    finally:
        d.close()


@routes_bp.route("/properties/<pid>/delete", methods=["POST"])
@login_required
@roles_for_form("ADMIN", "OWNER")
def property_delete(pid):
    d = db()
    try:
        d.execute(delete(properties).where(properties.c.id == pid))
        d.commit()
        flash("Помещение удалено", "success")
    except Exception as e:
        d.rollback()
        flash(f"Ошибка: {e}", "error")
    finally:
        d.close()
    return redirect(url_for("routes.properties_list"))


@routes_bp.route("/properties/<pid>/delete-photo", methods=["POST"])
@login_required
@roles_for_form("ADMIN", "OWNER")
def property_delete_photo(pid):
    url = request.form.get("url", "")
    d = db()
    try:
        prop = d.execute(select(properties).where(properties.c.id == pid)).first()
        if not prop or not prop.photoUrls:
            flash("Фото не найдено", "error")
            return redirect(url_for("routes.property_edit", pid=pid))
        photos = json.loads(prop.photoUrls) if prop.photoUrls else []
        if url in photos:
            photos.remove(url)
            # Delete file
            try:
                filepath = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "public", url.lstrip("/")
                )
                if os.path.exists(filepath):
                    os.remove(filepath)
                # Also delete thumbnail if exists
                base, ext = os.path.splitext(filepath)
                thumb_path = f"{base}_thumb{ext}"
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
            except Exception:
                pass
            d.execute(
                update(properties)
                .where(properties.c.id == pid)
                .values(photoUrls=json.dumps(photos) if photos else None, updatedAt=datetime.now())
            )
            d.commit()
            flash("Фото удалено", "success")
        else:
            flash("Фото не найдено в списке", "error")
    except Exception as e:
        d.rollback()
        flash(f"Ошибка: {e}", "error")
    finally:
        d.close()
    return redirect(url_for("routes.property_edit", pid=pid))


@routes_bp.route("/properties/<pid>/delete-document", methods=["POST"])
@login_required
@roles_for_form("ADMIN", "OWNER")
def property_delete_document(pid):
    url = request.form.get("url", "")
    d = db()
    try:
        prop = d.execute(select(properties).where(properties.c.id == pid)).first()
        if not prop or not prop.documentUrls:
            flash("Документ не найден", "error")
            return redirect(url_for("routes.property_edit", pid=pid))
        docs = json.loads(prop.documentUrls) if prop.documentUrls else []
        if url in docs:
            docs.remove(url)
            # Delete file
            try:
                filepath = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "public", url.lstrip("/")
                )
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            d.execute(
                update(properties)
                .where(properties.c.id == pid)
                .values(documentUrls=json.dumps(docs) if docs else None, updatedAt=datetime.now())
            )
            d.commit()
            flash("Документ удалён", "success")
        else:
            flash("Документ не найден в списке", "error")
    except Exception as e:
        d.rollback()
        flash(f"Ошибка: {e}", "error")
    finally:
        d.close()
    return redirect(url_for("routes.property_edit", pid=pid))


@routes_bp.route("/properties/ocr", methods=["POST"])
@login_required
@roles_for_form("ADMIN", "OWNER")
def property_ocr():
    file = request.files.get("file")
    if not file or not file.filename:
        return {"error": "Файл не выбран"}, 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "docx", "jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif"):
        return {"error": f"Неподдерживаемый формат: .{ext}"}, 400

    try:
        file_bytes = file.read()
        raw_text = extract_text(file_bytes, file.filename)
        if not raw_text or len(raw_text.strip()) < 5:
            return {"error": "Не удалось извлечь текст из файла"}, 422

        fields = parse_fields(raw_text)
        return {
            "raw_text": raw_text[:3000],
            "fields": fields,
        }
    except Exception as e:
        log = __import__("logging").getLogger(__name__)
        log.exception("OCR failed")
        return {"error": f"Ошибка распознавания: {e}"}, 500


# ── tenants ───────────────────────────────────────────────


@routes_bp.route("/tenants")
@login_required
def tenants_list():
    d = db()
    try:
        rows = d.execute(
            select(tenants).order_by(tenants.c.createdAt.desc())
        ).fetchall()
    finally:
        d.close()

    type_labels = {
        "LEGAL_ENTITY": "Юрлицо",
        "ENTREPRENEUR": "ИП",
        "INDIVIDUAL": "Физлицо",
    }
    return render_template("tenants.html", tenants=rows, type_labels=type_labels)


@routes_bp.route("/tenants/new", methods=["GET", "POST"])
@login_required
@roles_for("ADMIN", "OWNER")
def tenant_create():
    if request.method == "POST":
        d = db()
        try:
            d.execute(
                insert(tenants).values(
                    id=str(uuid.uuid4()),
                    type=request.form.get("type", "LEGAL_ENTITY"),
                    name=request.form.get("name", ""),
                    inn=request.form.get("inn") or None,
                    kpp=request.form.get("kpp") or None,
                    ogrn=request.form.get("ogrn") or None,
                    legalAddress=request.form.get("legalAddress") or None,
                    passportSeries=request.form.get("passportSeries") or None,
                    passportNumber=request.form.get("passportNumber") or None,
                    passportIssuedBy=request.form.get("passportIssuedBy") or None,
                    passportIssuedDate=_parse_date(request.form.get("passportIssuedDate")),
                    registrationAddress=request.form.get("registrationAddress") or None,
                    phone=request.form.get("phone") or None,
                    email=request.form.get("email") or None,
                    bankName=request.form.get("bankName") or None,
                    bankBik=request.form.get("bankBik") or None,
                    bankAccount=request.form.get("bankAccount") or None,
                    bankCorrAccount=request.form.get("bankCorrAccount") or None,
                    createdAt=datetime.now(),
                    updatedAt=datetime.now(),
                )
            )
            d.commit()
            flash("Арендатор добавлен", "success")
        except Exception as e:
            d.rollback()
            flash(f"Ошибка: {e}", "error")
        finally:
            d.close()
        return redirect(url_for("routes.tenants_list"))

    return render_template("tenant_form.html", tenant=None)


@routes_bp.route("/tenants/<tid>/edit", methods=["GET", "POST"])
@login_required
@roles_for("ADMIN", "OWNER")
def tenant_edit(tid):
    d = db()
    try:
        t = d.execute(select(tenants).where(tenants.c.id == tid)).first()
        if not t:
            flash("Арендатор не найден", "error")
            return redirect(url_for("routes.tenants_list"))

        if request.method == "POST":
            d.execute(
                update(tenants)
                .where(tenants.c.id == tid)
                .values(
                    type=request.form.get("type", "LEGAL_ENTITY"),
                    name=request.form.get("name", ""),
                    inn=request.form.get("inn") or None,
                    kpp=request.form.get("kpp") or None,
                    ogrn=request.form.get("ogrn") or None,
                    legalAddress=request.form.get("legalAddress") or None,
                    passportSeries=request.form.get("passportSeries") or None,
                    passportNumber=request.form.get("passportNumber") or None,
                    passportIssuedBy=request.form.get("passportIssuedBy") or None,
                    passportIssuedDate=_parse_date(request.form.get("passportIssuedDate")),
                    registrationAddress=request.form.get("registrationAddress") or None,
                    phone=request.form.get("phone") or None,
                    email=request.form.get("email") or None,
                    bankName=request.form.get("bankName") or None,
                    bankBik=request.form.get("bankBik") or None,
                    bankAccount=request.form.get("bankAccount") or None,
                    bankCorrAccount=request.form.get("bankCorrAccount") or None,
                    updatedAt=datetime.now(),
                )
            )
            d.commit()
            flash("Арендатор обновлён", "success")
            d.close()
            return redirect(url_for("routes.tenants_list"))

        return render_template("tenant_form.html", tenant=t)
    finally:
        d.close()


@routes_bp.route("/tenants/<tid>/delete", methods=["POST"])
@login_required
@roles_for_form("ADMIN", "OWNER")
def tenant_delete(tid):
    d = db()
    try:
        d.execute(delete(tenants).where(tenants.c.id == tid))
        d.commit()
        flash("Арендатор удалён", "success")
    except Exception as e:
        d.rollback()
        flash(f"Ошибка: {e}", "error")
    finally:
        d.close()
    return redirect(url_for("routes.tenants_list"))


# ── contracts ─────────────────────────────────────────────


@routes_bp.route("/contracts")
@login_required
def contracts_list():
    d = db()
    try:
        rows = d.execute(
            select(contracts).order_by(contracts.c.createdAt.desc())
        ).fetchall()

        contract_data = []
        for c in rows:
            t = d.execute(select(tenants).where(tenants.c.id == c.tenantId)).first()
            p = d.execute(select(properties).where(properties.c.id == c.propertyId)).first()
            o = d.execute(select(users).where(users.c.id == c.ownerId)).first()
            contract_data.append(
                {
                    "id": c.id,
                    "number": c.number,
                    "status": c.status,
                    "rentAmount": float(c.rentAmount),
                    "startDate": c.startDate,
                    "endDate": c.endDate,
                    "pdfUrl": c.pdfUrl,
                    "createdAt": c.createdAt,
                    "tenant": t.name if t else "—",
                    "property": p.name if p else "—",
                    "owner": o.name if o else "—",
                }
            )
    finally:
        d.close()

    status_labels = {
        "DRAFT": "Черновик",
        "ACTIVE": "Действует",
        "EXPIRED": "Истёк",
        "TERMINATED": "Расторгнут",
    }
    return render_template(
        "contracts.html", contracts=contract_data, status_labels=status_labels
    )


@routes_bp.route("/contracts/new", methods=["GET", "POST"])
@login_required
@roles_for("ADMIN", "OWNER")
def contract_create():
    d = db()
    try:
        templates = d.execute(
            select(contract_templates).where(contract_templates.c.isActive == True)
        ).fetchall()
        props = d.execute(select(properties)).fetchall()
        all_tenants = d.execute(select(tenants)).fetchall()
        all_users = d.execute(select(users)).fetchall()
    finally:
        d.close()

    if request.method == "POST":
        number = request.form.get("number", "")
        template_id = request.form.get("templateId", "")
        property_id = request.form.get("propertyId", "")
        tenant_id = request.form.get("tenantId", "")
        owner_id = request.form.get("ownerId") or current_user.id
        start_date_str = request.form.get("startDate", "")
        end_date_str = request.form.get("endDate", "")
        rent_amount_str = request.form.get("rentAmount", "0")
        deposit_str = request.form.get("depositAmount", "")
        payment_day_str = request.form.get("paymentDay", "")

        terms = {
            "electricityPayer": request.form.get("electricityPayer", "TENANT"),
            "waterPayer": request.form.get("waterPayer", "OWNER"),
            "heatingPayer": request.form.get("heatingPayer", "OWNER"),
            "cleaningPayer": request.form.get("cleaningPayer", "TENANT"),
        }

        d = db()
        try:
            template = d.execute(
                select(contract_templates).where(contract_templates.c.id == template_id)
            ).first()
            prop = d.execute(
                select(properties).where(properties.c.id == property_id)
            ).first()
            tenant = d.execute(
                select(tenants).where(tenants.c.id == tenant_id)
            ).first()
            owner = d.execute(
                select(users).where(users.c.id == owner_id)
            ).first()

            if not all([template, prop, tenant, owner]):
                flash("Не все данные заполнены", "error")
                return redirect(url_for("routes.contract_create"))

            contract_data = {
                "number": number,
                "startDate": start_date_str,
                "endDate": end_date_str or None,
                "rentAmount": float(rent_amount_str) if rent_amount_str else 0,
                "depositAmount": float(deposit_str) if deposit_str else None,
                "paymentDay": int(payment_day_str) if payment_day_str else None,
                "terms": terms,
            }

            template_data = build_template_data(contract_data, template, prop, tenant, owner)

            html = render_contract_html(template.htmlContent, template_data)
            pdf_bytes = generate_pdf(html)

            pdf_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "public",
                "contracts",
            )
            os.makedirs(pdf_dir, exist_ok=True)
            safe_number = contract_data["number"].replace("/", "-").replace("\\", "-").replace(" ", "_")
            file_name = f"{safe_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf_path = os.path.join(pdf_dir, file_name)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            start_date = datetime.fromisoformat(start_date_str) if start_date_str else datetime.now()
            end_date = (
                datetime.fromisoformat(end_date_str)
                if end_date_str
                else start_date + timedelta(days=365)
            )

            cid = str(uuid.uuid4())
            d.execute(
                insert(contracts).values(
                    id=cid,
                    number=number,
                    templateId=template_id,
                    propertyId=property_id,
                    tenantId=tenant_id,
                    ownerId=owner_id,
                    startDate=start_date,
                    endDate=end_date,
                    rentAmount=float(rent_amount_str) if rent_amount_str else 0,
                    depositAmount=float(deposit_str) if deposit_str else None,
                    paymentDay=int(payment_day_str) if payment_day_str else None,
                    terms=terms,
                    pdfUrl=f"/contracts/{file_name}",
                    status="DRAFT",
                    createdAt=datetime.now(),
                    updatedAt=datetime.now(),
                )
            )
            d.commit()
            flash("Договор создан!", "success")
            return render_template(
                "contract_created.html",
                number=number,
                pdf_url=f"/contracts/{file_name}",
            )
        except Exception as e:
            d.rollback()
            flash(f"Ошибка: {e}", "error")
        finally:
            d.close()

    return render_template(
        "contract_form.html",
        templates=templates,
        properties=props,
        tenants=all_tenants,
        users=all_users,
    )


@routes_bp.route("/contracts/<cid>/delete", methods=["POST"])
@login_required
@roles_for_form("ADMIN", "OWNER")
def contract_delete(cid):
    d = db()
    try:
        d.execute(delete(contracts).where(contracts.c.id == cid))
        d.commit()
        flash("Договор удалён", "success")
    except Exception as e:
        d.rollback()
        flash(f"Ошибка: {e}", "error")
    finally:
        d.close()
    return redirect(url_for("routes.contracts_list"))


@routes_bp.route("/contracts/preview", methods=["POST"])
@login_required
def contract_preview():
    """Live preview: render template with current form data, return HTML fragment."""
    template_id = request.form.get("templateId", "")
    property_id = request.form.get("propertyId", "")
    tenant_id = request.form.get("tenantId", "")
    owner_id = request.form.get("ownerId", "") or current_user.id

    d = db()
    try:
        template = d.execute(
            select(contract_templates).where(contract_templates.c.id == template_id)
        ).first()
        prop = d.execute(select(properties).where(properties.c.id == property_id)).first()
        tenant = d.execute(select(tenants).where(tenants.c.id == tenant_id)).first()
        owner = d.execute(select(users).where(users.c.id == owner_id)).first()

        contract_data = {
            "number": request.form.get("number", ""),
            "startDate": request.form.get("startDate", ""),
            "endDate": request.form.get("endDate", ""),
            "rentAmount": float(request.form.get("rentAmount") or 0),
            "depositAmount": float(request.form.get("depositAmount") or 0) or None,
            "paymentDay": request.form.get("paymentDay", ""),
            "terms": {
                "electricityPayer": request.form.get("electricityPayer", "TENANT"),
                "waterPayer": request.form.get("waterPayer", "OWNER"),
                "heatingPayer": request.form.get("heatingPayer", "OWNER"),
                "cleaningPayer": request.form.get("cleaningPayer", "TENANT"),
            },
        }

        if template:
            td = build_template_data(contract_data, template, prop, tenant, owner)
            from app.pdf import render_preview
            html = render_preview(template.htmlContent, td)
            return html
        return "<p class='text-muted'>Выберите шаблон</p>"
    finally:
        d.close()


# ── templates ──────────────────────────────────────────────


@routes_bp.route("/templates")
@login_required
def templates_list():
    d = db()
    try:
        rows = d.execute(
            select(contract_templates).order_by(contract_templates.c.createdAt.desc())
        ).fetchall()
    finally:
        d.close()
    return render_template("contract_templates.html", templates=rows)


@routes_bp.route("/templates/new", methods=["GET", "POST"])
@login_required
@roles_for("ADMIN")
def template_create():
    if request.method == "POST":
        d = db()
        try:
            d.execute(
                insert(contract_templates).values(
                    id=str(uuid.uuid4()),
                    name=request.form.get("name", ""),
                    description=request.form.get("description") or None,
                    htmlContent=request.form.get("htmlContent", ""),
                    version=1,
                    isActive=True,
                    createdAt=datetime.now(),
                    updatedAt=datetime.now(),
                )
            )
            d.commit()
            flash("Шаблон добавлен", "success")
            return redirect(url_for("routes.templates_list"))
        except Exception as e:
            d.rollback()
            flash(f"Ошибка: {e}", "error")
        finally:
            d.close()

    return render_template("template_form.html", template=None)


@routes_bp.route("/templates/<tid>/edit", methods=["GET", "POST"])
@login_required
@roles_for("ADMIN")
def template_edit(tid):
    d = db()
    try:
        t = d.execute(
            select(contract_templates).where(contract_templates.c.id == tid)
        ).first()
        if not t:
            flash("Шаблон не найден", "error")
            return redirect(url_for("routes.templates_list"))

        if request.method == "POST":
            d.execute(
                update(contract_templates)
                .where(contract_templates.c.id == tid)
                .values(
                    name=request.form.get("name", ""),
                    description=request.form.get("description") or None,
                    htmlContent=request.form.get("htmlContent", ""),
                    updatedAt=datetime.now(),
                )
            )
            d.commit()
            flash("Шаблон обновлён", "success")
            return redirect(url_for("routes.templates_list"))

        return render_template("template_form.html", template=t)
    finally:
        d.close()


@routes_bp.route("/templates/<tid>/delete", methods=["POST"])
@login_required
@roles_for_form("ADMIN")
def template_delete(tid):
    d = db()
    try:
        d.execute(delete(contract_templates).where(contract_templates.c.id == tid))
        d.commit()
        flash("Шаблон удалён", "success")
    except Exception as e:
        d.rollback()
        flash(f"Ошибка: {e}", "error")
    finally:
        d.close()
    return redirect(url_for("routes.templates_list"))


# ── settings ───────────────────────────────────────────────


@routes_bp.route("/settings")
@login_required
def settings_page():
    d = db()
    try:
        all_users = d.execute(
            select(users).order_by(users.c.name.asc())
        ).fetchall()
    finally:
        d.close()

    role_labels = {
        "ADMIN": "Администратор",
        "OWNER": "Собственник",
        "ACCOUNTANT": "Бухгалтер",
        "VIEWER": "Наблюдатель",
    }
    return render_template(
        "settings.html",
        current=current_user,
        users=all_users,
        role_labels=role_labels,
    )


# ── internal helpers ──────────────────────────────────────


def _get_users(db_session):
    return db_session.execute(select(users).order_by(users.c.name.asc())).fetchall()


def _parse_date(val):
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _save_uploads(files, property_id: str, subdir: str) -> list:
    """Save uploaded files and return list of relative URL paths.
    For images also generates a thumbnail (300x200, fit)."""
    urls = []
    upload_base = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "public", "uploads", "properties",
        property_id, subdir,
    )
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        filename = f"{uuid.uuid4().hex}{ext}"
        os.makedirs(upload_base, exist_ok=True)
        filepath = os.path.join(upload_base, filename)
        f.save(filepath)
        urls.append(f"/uploads/properties/{property_id}/{subdir}/{filename}")

        if ext in IMAGE_EXTENSIONS:
            _generate_thumbnail(filepath)
    return urls


def _generate_thumbnail(filepath: str, size: tuple = (300, 200)) -> None:
    """Create a _thumb version next to the original image."""
    from PIL import Image

    try:
        base, ext = os.path.splitext(filepath)
        thumb_path = f"{base}_thumb{ext}"
        with Image.open(filepath) as im:
            im.thumbnail(size, Image.LANCZOS)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(thumb_path, "JPEG", quality=85)
    except Exception:
        pass
