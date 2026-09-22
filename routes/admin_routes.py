from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import (
    db, User, Patient, HealthcareProvider, HealthcareFacility, Service,
    Speciality, Appointment, Notification, Announcement, AuditLog,
    ROLE_PATIENT, ROLE_PROVIDER, ROLE_ADMIN,
    APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED,
    APPT_CANCELLED, APPT_RESCHEDULED, DAYS,
)
from helpers import (
    admin_required, send_notification, record_audit, generate_booking_code,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def restrict():
    if current_user.role != ROLE_ADMIN:
        abort(403)


@admin_bp.route("/")
@admin_bp.route("/dashboard")
def dashboard():
    total_patients = Patient.query.count()
    total_providers = HealthcareProvider.query.count()
    total_facilities = HealthcareFacility.query.count()
    total_services = Service.query.count()
    counts = {}
    for status in [APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED]:
        counts[status] = Appointment.query.filter_by(status=status).count()

    recent_appts = Appointment.query.order_by(Appointment.created_at.desc()).limit(8).all()
    recent_audits = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(8).all()

    return render_template(
        "admin/dashboard.html",
        stats={
            "patients": total_patients,
            "providers": total_providers,
            "facilities": total_facilities,
            "services": total_services,
            "appointments": sum(counts.values()),
        },
        counts=counts,
        recent_appts=recent_appts,
        recent_audits=recent_audits,
        APPT_STATUSES=[APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED],
    )


# ---------------------------- USERS / PATIENTS / PROVIDERS ----------------------------

@admin_bp.route("/users")
def users():
    filter_role = request.args.get("role", "").strip()
    q = User.query
    if filter_role in (ROLE_PATIENT, ROLE_PROVIDER, ROLE_ADMIN):
        q = q.filter(User.role == filter_role)
    users = q.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users, filter_role=filter_role)


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
def toggle_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    state = "deactivated" if not user.is_active else "activated"
    record_audit(f"User {state}", f"{user.email}")
    db.session.commit()
    flash(f"User {user.email} {state}.", "success")
    return redirect(url_for("admin.users", role=user.role))


@admin_bp.route("/patients")
def patients():
    patients = Patient.query.order_by(Patient.created_at.desc()).all()
    return render_template("admin/patients.html", patients=patients)


@admin_bp.route("/providers", methods=["GET", "POST"])
def providers():
    specialties = Speciality.query.order_by(Speciality.name).all()
    facilities = HealthcareFacility.query.order_by(HealthcareFacility.name).all()
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "")
            title = request.form.get("title", "").strip() or "Dr."
            specialty_id = request.form.get("specialty_id", type=int)
            qualifications = request.form.get("qualifications", "").strip()
            exp_years = request.form.get("experience_years", type=int) or 0
            bio = request.form.get("bio", "").strip()
            license_no = request.form.get("license_number", "").strip()

            if not full_name or not email or len(password) < 6:
                flash("Provider requires full name, valid email and password (6+ chars).", "error")
                return redirect(url_for("admin.providers"))
            if User.query.filter_by(email=email).first():
                flash("A user with that email already exists.", "error")
                return redirect(url_for("admin.providers"))

            username = email.split("@")[0]
            base = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base}{counter}"
                counter += 1

            user = User(username=username, email=email, phone=phone, role=ROLE_PROVIDER)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            provider = HealthcareProvider(
                user_id=user.id, full_name=full_name, title=title,
                specialty_id=specialty_id, qualifications=qualifications,
                experience_years=exp_years, bio=bio, license_number=license_no,
            )
            db.session.add(provider)
            db.session.flush()

            sel_facilities = request.form.getlist("facilities")
            sel_services = request.form.getlist("services")
            if sel_facilities:
                provider.facilities = HealthcareFacility.query.filter(
                    HealthcareFacility.id.in_([int(x) for x in sel_facilities])).all()
            if sel_services:
                provider.services = Service.query.filter(
                    Service.id.in_([int(x) for x in sel_services])).all()

            send_notification(
                user.id,
                "Provider account created",
                f"Welcome Dr. {full_name}! Your healthcare provider account has been created "
                "by the administrator. You can now log in and manage appointments.",
                "welcome",
            )
            record_audit("Provider created", f"{email}")
            db.session.commit()
            flash(f"Provider {full_name} created. Configure their facilities, services and availability below.", "success")
            return redirect(url_for("admin.edit_provider", provider_id=provider.id))

        elif action == "export":
            pass

    return render_template(
        "admin/providers.html",
        providers=HealthcareProvider.query.order_by(HealthcareProvider.created_at.desc()).all(),
        specialties=specialties,
        facilities=facilities,
        services=services,
        DAYS=DAYS,
    )


@admin_bp.route("/providers/<int:provider_id>/edit", methods=["GET", "POST"])
def edit_provider(provider_id):
    provider = db.session.get(HealthcareProvider, provider_id) or abort(404)
    specialties = Speciality.query.order_by(Speciality.name).all()
    facilities = HealthcareFacility.query.order_by(HealthcareFacility.name).all()
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()

    if request.method == "POST":
        action = request.form.get("action", "")
        provider.full_name = request.form.get("full_name", provider.full_name).strip()
        provider.title = request.form.get("title", provider.title).strip() or "Dr."
        provider.specialty_id = request.form.get("specialty_id", type=int)
        provider.qualifications = request.form.get("qualifications", provider.qualifications).strip()
        provider.experience_years = request.form.get("experience_years", type=int) or 0
        provider.bio = request.form.get("bio", provider.bio).strip()
        provider.license_number = request.form.get("license_number", provider.license_number).strip()
        provider.user.phone = request.form.get("phone", provider.user.phone).strip()

        sel_facilities = request.form.getlist("facilities")
        sel_services = request.form.getlist("services")
        provider.facilities = HealthcareFacility.query.filter(
            HealthcareFacility.id.in_([int(x) for x in sel_facilities])).all() if sel_facilities else []
        provider.services = Service.query.filter(
            Service.id.in_([int(x) for x in sel_services])).all() if sel_services else []

        record_audit("Provider updated", provider.user.email)
        db.session.commit()
        flash("Provider details updated.", "success")
        return redirect(url_for("admin.edit_provider", provider_id=provider.id))

    return render_template(
        "admin/edit_provider.html",
        provider=provider,
        specialties=specialties,
        facilities=facilities,
        services=services,
        DAYS=DAYS,
    )


@admin_bp.route("/providers/<int:provider_id>/availability", methods=["POST"])
def manage_availability(provider_id):
    provider = db.session.get(HealthcareProvider, provider_id) or abort(404)
    action = request.form.get("action", "")
    if action == "add":
        day = request.form.get("day", type=int)
        start = request.form.get("start_time", "")
        end = request.form.get("end_time", "")
        if day is None or not (0 <= day <= 6) or not start or not end or start >= end:
            flash("Invalid availability input.", "error")
        else:
            from models import ProviderAvailability
            dup = any(
                a.day_week == day and a.start_time == start and a.end_time == end
                for a in provider.availability
            )
            if dup:
                flash("That availability window already exists.", "error")
            else:
                db.session.add(ProviderAvailability(
                    provider_id=provider.id, day_week=day, start_time=start, end_time=end))
                record_audit("Availability added", provider.user.email)
                db.session.commit()
                flash("Availability added.", "success")
    elif action == "delete":
        slot_id = request.form.get("slot_id", type=int)
        from models import ProviderAvailability
        slot = db.session.get(ProviderAvailability, slot_id)
        if slot and slot.provider_id == provider.id:
            db.session.delete(slot)
            record_audit("Availability removed", provider.user.email)
            db.session.commit()
            flash("Availability slot removed.", "success")
    return redirect(url_for("admin.edit_provider", provider_id=provider.id))


@admin_bp.route("/providers/<int:provider_id>/delete", methods=["POST"])
def delete_provider(provider_id):
    provider = db.session.get(HealthcareProvider, provider_id) or abort(404)
    email = provider.user.email
    db.session.delete(provider.user)
    db.session.delete(provider)
    record_audit("Provider deleted", email)
    db.session.commit()
    flash(f"Provider {email} and their account were deleted.", "success")
    return redirect(url_for("admin.providers"))


# ---------------------------- FACILITIES ----------------------------

@admin_bp.route("/facilities", methods=["GET", "POST"])
def facilities():
    if request.method == "POST":
        action = request.form.get("action", "")
        from models import HealthcareFacility
        if action == "create":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Facility name is required.", "error")
            elif HealthcareFacility.query.filter_by(name=name).first():
                flash("A facility with that name already exists.", "error")
            else:
                f = HealthcareFacility(
                    name=name,
                    address=request.form.get("address", "").strip(),
                    city=request.form.get("city", "").strip(),
                    phone=request.form.get("phone", "").strip(),
                    email=request.form.get("email", "").strip(),
                    description=request.form.get("description", "").strip(),
                )
                db.session.add(f)
                record_audit("Facility created", name)
                db.session.commit()
                flash(f"Facility {name} created.", "success")
        return redirect(url_for("admin.facilities"))

    facilities = HealthcareFacility.query.order_by(HealthcareFacility.name).all()
    return render_template("admin/facilities.html", facilities=facilities)


@admin_bp.route("/facilities/<int:facility_id>/toggle", methods=["POST"])
def toggle_facility(facility_id):
    f = db.session.get(HealthcareFacility, facility_id) or abort(404)
    f.is_active = not f.is_active
    state = "deactivated" if not f.is_active else "activated"
    record_audit(f"Facility {state}", f.name)
    db.session.commit()
    flash(f"Facility {f.name} {state}.", "success")
    return redirect(url_for("admin.facilities"))


@admin_bp.route("/facilities/<int:facility_id>/edit", methods=["GET", "POST"])
def edit_facility(facility_id):
    f = db.session.get(HealthcareFacility, facility_id) or abort(404)
    if request.method == "POST":
        f.name = request.form.get("name", f.name).strip()
        f.address = request.form.get("address", "").strip()
        f.city = request.form.get("city", "").strip()
        f.phone = request.form.get("phone", "").strip()
        f.email = request.form.get("email", "").strip()
        f.description = request.form.get("description", "").strip()
        record_audit("Facility updated", f.name)
        db.session.commit()
        flash("Facility updated.", "success")
        return redirect(url_for("admin.facilities"))
    return render_template("admin/edit_facility.html", facility=f)


@admin_bp.route("/facilities/<int:facility_id>/delete", methods=["POST"])
def delete_facility(facility_id):
    f = db.session.get(HealthcareFacility, facility_id) or abort(404)
    name = f.name
    db.session.delete(f)
    record_audit("Facility deleted", name)
    db.session.commit()
    flash(f"Facility {name} deleted.", "success")
    return redirect(url_for("admin.facilities"))


# ---------------------------- SERVICES ----------------------------

@admin_bp.route("/services", methods=["GET", "POST"])
def services():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            name = request.form.get("name", "").strip()
            desc = request.form.get("description", "").strip()
            specialty_id = request.form.get("specialty_id", type=int)
            if not name:
                flash("Service name is required.", "error")
            elif Service.query.filter_by(name=name).first():
                flash("A service with that name already exists.", "error")
            else:
                s = Service(name=name, description=desc, specialty_id=specialty_id)
                db.session.add(s)
                record_audit("Service created", name)
                db.session.commit()
                flash(f"Service {name} created.", "success")
        return redirect(url_for("admin.services"))

    services = Service.query.order_by(Service.name).all()
    specialties = Speciality.query.order_by(Speciality.name).all()
    return render_template("admin/services.html", services=services, specialties=specialties)


@admin_bp.route("/services/<int:service_id>/toggle", methods=["POST"])
def toggle_service(service_id):
    s = db.session.get(Service, service_id) or abort(404)
    s.is_active = not s.is_active
    state = "deactivated" if not s.is_active else "activated"
    record_audit(f"Service {state}", s.name)
    db.session.commit()
    flash(f"Service {s.name} {state}.", "success")
    return redirect(url_for("admin.services"))


@admin_bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
def edit_service(service_id):
    s = db.session.get(Service, service_id) or abort(404)
    if request.method == "POST":
        s.name = request.form.get("name", s.name).strip()
        s.description = request.form.get("description", "").strip()
        s.specialty_id = request.form.get("specialty_id", type=int)
        record_audit("Service updated", s.name)
        db.session.commit()
        flash("Service updated.", "success")
        return redirect(url_for("admin.services"))
    specialties = Speciality.query.order_by(Speciality.name).all()
    return render_template("admin/edit_service.html", service=s, specialties=specialties)


@admin_bp.route("/services/<int:service_id>/delete", methods=["POST"])
def delete_service(service_id):
    s = db.session.get(Service, service_id) or abort(404)
    name = s.name
    db.session.delete(s)
    record_audit("Service deleted", name)
    db.session.commit()
    flash(f"Service {name} deleted.", "success")
    return redirect(url_for("admin.services"))


@admin_bp.route("/specialties", methods=["GET", "POST"])
def specialties():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            name = request.form.get("name", "").strip()
            desc = request.form.get("description", "").strip()
            if not name:
                flash("Specialty name is required.", "error")
            elif Speciality.query.filter_by(name=name).first():
                flash("That specialty already exists.", "error")
            else:
                db.session.add(Speciality(name=name, description=desc))
                record_audit("Specialty created", name)
                db.session.commit()
                flash("Specialty created.", "success")
        return redirect(url_for("admin.specialties"))
    return render_template("admin/specialties.html",
                           specialties=Speciality.query.order_by(Speciality.name).all())


# ---------------------------- APPOINTMENTS ----------------------------

@admin_bp.route("/appointments")
def appointments():
    status = request.args.get("status", "").strip()
    q = Appointment.query
    if status:
        q = q.filter(Appointment.status == status)
    appts = q.order_by(Appointment.created_at.desc()).all()
    return render_template(
        "admin/appointments.html",
        appointments=appts,
        status=status,
        APPT_STATUSES=[APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED],
    )


@admin_bp.route("/appointments/<int:appointment_id>")
def appointment_detail(appointment_id):
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    return render_template(
        "admin/appointment_detail.html",
        appointment=appt,
        APPT_STATUSES=[APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED],
    )


# ---------------------------- NOTIFICATIONS ----------------------------

@admin_bp.route("/notifications", methods=["GET", "POST"])
def notifications():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "send":
            audience = request.form.get("audience", "")
            title = request.form.get("title", "").strip()
            message = request.form.get("message", "").strip()
            if not title or not message:
                flash("Title and message are required.", "error")
            else:
                recipients = []
                if audience in (ROLE_PATIENT, "all"):
                    recipients += [u.id for u in User.query.filter_by(role=ROLE_PATIENT)]
                if audience in (ROLE_PROVIDER, "all"):
                    recipients += [u.id for u in User.query.filter_by(role=ROLE_PROVIDER)]
                for uid in recipients:
                    send_notification(uid, title, message, "announcement")
                if recipients:
                    db.session.add(Announcement(
                        title=title, message=message,
                        audience=audience, created_by=current_user.id))
                    record_audit("Notification sent", f"To {audience}: {title}")
                    db.session.commit()
                    flash(f"Notification sent to {len(recipients)} user(s).", "success")
                else:
                    flash("No recipients matched that audience.", "error")
        return redirect(url_for("admin.notifications"))

    notes = Notification.query.order_by(Notification.created_at.desc()).limit(100).all()
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/notifications.html", notifications=notes, announcements=announcements)


# ---------------------------- REPORTS / AUDIT / SUPPORT ----------------------------

@admin_bp.route("/reports")
def reports():
    appts = Appointment.query.order_by(Appointment.appointment_date).all()
    status_counts = {}
    for s in [APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED]:
        status_counts[s] = Appointment.query.filter_by(status=s).count()
    by_service = []
    for svc in Service.query.all():
        by_service.append({
            "service": svc.name,
            "count": Appointment.query.filter_by(service_id=svc.id).count(),
        })
    by_facility = []
    for f in HealthcareFacility.query.all():
        by_facility.append({
            "facility": f.name,
            "count": Appointment.query.filter_by(facility_id=f.id).count(),
        })
    return render_template(
        "admin/reports.html",
        appointments=appts,
        status_counts=status_counts,
        by_service=by_service,
        by_facility=by_facility,
    )


@admin_bp.route("/audit-logs")
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).all()
    return render_template("admin/audit_logs.html", logs=logs)


@admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        from flask import current_app
        current_app.config["SECRET_KEY"] = request.form.get("app_name", "AfyaNow")
        flash("Demo settings saved. (In production these map to environment configuration.)", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html")