from datetime import datetime, date

from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user

from models import (
    db, User, Patient, HealthcareProvider, Speciality, Service,
    HealthcareFacility, Appointment, Notification, AppointmentStatusHistory,
    ROLE_PATIENT, ROLE_PROVIDER, ROLE_ADMIN,
    APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED,
    APPT_CANCELLED, APPT_RESCHEDULED,
)
from helpers import slot_conflict_exists, generate_booking_code, send_notification, record_audit

api_bp = Blueprint("api", __name__, url_prefix="/api")


def user_payload(user):
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "phone": user.phone, "role": user.role, "is_active": user.is_active,
    }


def service_payload(s):
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "is_active": s.is_active,
        "specialty": s.specialty.name if s.specialty else None,
        "provider_count": len(s.providers),
    }


def provider_payload(p):
    return {
        "id": p.id, "name": f"{p.title} {p.full_name}".strip(),
        "title": p.title, "qualifications": p.qualifications,
        "experience_years": p.experience_years, "bio": p.bio,
        "specialty": p.speciality.name if p.speciality else None,
        "services": [s.name for s in p.services],
        "facilities": [f.name for f in p.facilities],
    }


def facility_payload(f):
    return {
        "id": f.id, "name": f.name, "city": f.city, "address": f.address,
        "phone": f.phone, "is_active": f.is_active,
        "provider_count": len(f.providers),
    }


def appointment_payload(a):
    return {
        "id": a.id, "booking_code": a.booking_code,
        "patient": a.patient.full_name,
        "patient_id": a.patient.user_id,
        "provider": f"{a.provider.title} {a.provider.full_name}".strip(),
        "facility": a.facility.name,
        "service": a.service.name,
        "date": a.appointment_date.strftime("%Y-%m-%d"),
        "time": a.appointment_time,
        "reason": a.reason_for_visit,
        "status": a.status,
        "provider_response": a.provider_response,
        "created": a.created_at.isoformat() if a.created_at else None,
        "updated": a.updated_at.isoformat() if a.updated_at else None,
    }


# ---------------------------- AUTH ----------------------------

@api_bp.route("/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""
    if not identifier or not password:
        return jsonify({"error": "Identifier and password are required."}), 400
    user = (
        User.query.filter(
            (User.email == identifier.lower()) | (User.username == identifier) | (User.phone == identifier)
        ).first()
    )
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials."}), 401
    if not user.is_active:
        return jsonify({"error": "Account deactivated."}), 403
    from flask_login import login_user
    login_user(user)
    record_audit(f"API login: {user.role}")
    db.session.commit()
    return jsonify({"message": "Login successful.", "user": user_payload(user)})


@api_bp.route("/auth/me")
@login_required
def api_me():
    return jsonify({"user": user_payload(current_user)})


@api_bp.route("/auth/logout", methods=["POST"])
@login_required
def api_logout():
    from flask_login import logout_user
    logout_user()
    return jsonify({"message": "Logged out."})


# ---------------------------- SHARED / PUBLIC ----------------------------

@api_bp.route("/services")
def api_services():
    services = Service.query.filter_by(is_active=True).all()
    return jsonify({"services": [service_payload(s) for s in services]})


@api_bp.route("/services/<int:service_id>")
def api_service(service_id):
    s = db.session.get(Service, service_id) or abort(404)
    return jsonify({"service": service_payload(s)})


@api_bp.route("/services/<int:service_id>/facilities")
def api_service_facilities(service_id):
    s = db.session.get(Service, service_id) or abort(404)
    seen = {}
    for p in s.providers:
        for f in p.facilities:
            if f.is_active:
                seen.setdefault(f.id, {"facility": f, "count": 0})
                seen[f.id]["count"] += 1
    results = [{"facility": facility_payload(v["facility"]), "providers": v["count"]}
               for v in seen.values()]
    return jsonify({"facilities": results})


@api_bp.route("/services/<int:service_id>/providers")
def api_service_providers(service_id):
    s = db.session.get(Service, service_id) or abort(404)
    return jsonify({"providers": [provider_payload(p) for p in s.providers]})


@api_bp.route("/providers/<int:provider_id>")
def api_provider(provider_id):
    p = db.session.get(HealthcareProvider, provider_id) or abort(404)
    return jsonify({"provider": provider_payload(p)})


@api_bp.route("/providers/<int:provider_id>/availability")
def api_provider_availability(provider_id):
    p = db.session.get(HealthcareProvider, provider_id) or abort(404)
    from models import DAYS
    availability = [{"day_week": a.day_week, "day": DAYS[a.day_week],
                     "start_time": a.start_time, "end_time": a.end_time}
                    for a in p.availability]
    return jsonify({"availability": availability})


@api_bp.route("/facilities")
def api_facilities():
    facilities = HealthcareFacility.query.filter_by(is_active=True).all()
    return jsonify({"facilities": [facility_payload(f) for f in facilities]})


# ---------------------------- PATIENT (OWN DATA ONLY) ----------------------------

@api_bp.route("/appointments", methods=["GET", "POST"])
@login_required
def api_appointments():
    if request.method == "POST":
        if current_user.role != ROLE_PATIENT:
            return jsonify({"error": "Only patients can book appointments."}), 403
        data = request.get_json(silent=True) or {}
        service_id = data.get("service_id")
        facility_id = data.get("facility_id")
        provider_id = data.get("provider_id")
        appt_date_str = data.get("date")
        appt_time = data.get("time")
        reason = data.get("reason", "").strip()

        service = db.session.get(Service, service_id)
        facility = db.session.get(HealthcareFacility, facility_id)
        provider = db.session.get(HealthcareProvider, provider_id)
        if not (service and facility and provider):
            return jsonify({"error": "Invalid service, facility or provider."}), 400
        try:
            appt_date = datetime.strptime(appt_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid date."}), 400
        if appt_date <= date.today():
            return jsonify({"error": "Date must be in the future."}), 400
        if service not in provider.services:
            return jsonify({"error": "Provider does not offer that service."}), 400
        if not any(f.id == facility.id for f in provider.facilities):
            return jsonify({"error": "Provider is not assigned to that facility."}), 400
        if not any(appt_date.weekday() == a.day_week and a.start_time <= appt_time <= a.end_time
                   for a in provider.availability):
            return jsonify({"error": "Time outside provider availability."}), 400
        if slot_conflict_exists(provider.id, appt_date, appt_time):
            return jsonify({"error": "That time slot is already booked."}), 409

        appt = Appointment(
            booking_code=generate_booking_code(),
            patient_id=current_user.patient.id,
            provider_id=provider.id, facility_id=facility.id, service_id=service.id,
            appointment_date=appt_date, appointment_time=appt_time,
            reason_for_visit=reason, status=APPT_PENDING,
        )
        db.session.add(appt)
        db.session.flush()
        db.session.add(AppointmentStatusHistory(
            appointment_id=appt.id, status=APPT_PENDING,
            changed_by_role="patient", note="API booking submitted"))
        send_notification(provider.user_id, "New appointment request",
                          f"Patient {current_user.patient.full_name} booked {service.name} "
                          f"on {appt_date} at {appt_time}.")
        send_notification(current_user.id, "Appointment submitted",
                          f"Your appointment {appt.booking_code} was submitted.")
        record_audit("Appointment created (API)", appt.booking_code)
        db.session.commit()
        return jsonify({"message": "Appointment booked.", "appointment": appointment_payload(appt)}), 201

    if current_user.role == ROLE_PATIENT:
        q = Appointment.query.filter_by(patient_id=current_user.patient.id)
    elif current_user.role == ROLE_PROVIDER:
        q = Appointment.query.filter_by(provider_id=current_user.provider.id)
    else:
        q = Appointment.query
    return jsonify({"appointments": [appointment_payload(a) for a in q.all()]})


@api_bp.route("/appointments/<int:appointment_id>")
@login_required
def api_appointment(appointment_id):
    a = db.session.get(Appointment, appointment_id) or abort(404)
    if current_user.role == ROLE_PATIENT and a.patient_id != current_user.patient.id:
        return jsonify({"error": "Forbidden."}), 403
    if current_user.role == ROLE_PROVIDER and a.provider_id != current_user.provider.id:
        return jsonify({"error": "Forbidden."}), 403
    return jsonify({"appointment": appointment_payload(a)})


def _transition(appointment_id, to_status, require_provider=True, note=None, reason=None):
    a = db.session.get(Appointment, appointment_id) or abort(404)
    if current_user.role == ROLE_PATIENT and a.patient_id != current_user.patient.id:
        return jsonify({"error": "Forbidden."}), 403
    if current_user.role == ROLE_PROVIDER and a.provider_id != current_user.provider.id:
        return jsonify({"error": "Forbidden."}), 403

    allowed = {
        "accept": (APPT_ACCEPTED, [APPT_PENDING]),
        "decline": (APPT_DECLINED, [APPT_PENDING, APPT_RESCHEDULED]),
        "complete": (APPT_COMPLETED, [APPT_ACCEPTED, APPT_RESCHEDULED]),
        "cancel": (APPT_CANCELLED, [APPT_PENDING, APPT_ACCEPTED]),
        "reschedule": (APPT_RESCHEDULED, [APPT_PENDING, APPT_ACCEPTED, APPT_RESCHEDULED]),
    }[to_status]

    if a.status not in allowed[1]:
        return jsonify({"error": f"Cannot transition from {a.status} to {allowed[0]}."}), 409

    if to_status == "accept" and slot_conflict_exists(a.provider_id, a.appointment_date,
                                                      a.appointment_time, exclude_appointment_id=a.id):
        return jsonify({"error": "Provider already has a conflicting appointment in that slot."}), 409

    data = request.get_json(silent=True) or {}
    if to_status == "decline" and current_user.role == ROLE_PROVIDER:
        reason = (reason or data.get("reason") or "").strip()
        if not reason:
            return jsonify({"error": "A decline reason is required."}), 400
    if to_status == "cancel" and current_user.role == ROLE_PATIENT:
        if not reason:
            reason = data.get("reason") or "Cancelled by patient"

    reschedule_note = None
    if to_status == "reschedule":
        new_date_str = data.get("new_date")
        new_time = data.get("new_time")
        try:
            new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid new date."}), 400
        provider = a.provider
        valid = any(new_date.weekday() == av.day_week and av.start_time <= new_time <= av.end_time
                    for av in provider.availability)
        if not valid:
            return jsonify({"error": "New time outside provider availability."}), 400
        if slot_conflict_exists(provider.id, new_date, new_time, exclude_appointment_id=a.id):
            return jsonify({"error": "New time slot already booked."}), 409
        if not a.original_date:
            a.original_date = a.appointment_date
            a.original_time = a.appointment_time
        a.appointment_date = new_date
        a.appointment_time = new_time
        reschedule_note = f"Rescheduled to {new_date} {new_time}"

    a.status = allowed[0]
    if reason is not None:
        a.provider_response = reason
    db.session.add(AppointmentStatusHistory(
        appointment_id=a.id, status=allowed[0],
        changed_by_role=current_user.role,
        note=reschedule_note or data.get("note") or (reason if reason else None) or ""))
    _notify_transition(a, allowed[0])
    record_audit(f"API appointment {allowed[0]}", a.booking_code)
    db.session.commit()
    return jsonify({"message": f"Appointment {allowed[0]}.", "appointment": appointment_payload(a)})


def _notify_transition(a, status):
    human_map = {
        APPT_ACCEPTED: "accepted", APPT_DECLINED: "declined", APPT_COMPLETED: "completed",
        APPT_CANCELLED: "cancelled", APPT_RESCHEDULED: "rescheduled",
    }
    verb = human_map.get(status, status)
    if current_user.role == ROLE_PROVIDER:
        send_notification(a.patient.user_id, f"Appointment {verb}",
                          f"Your appointment {a.booking_code} was {verb} by "
                          f"{a.provider.title} {a.provider.full_name}.")
    elif current_user.role == ROLE_PATIENT:
        send_notification(a.provider.user_id, f"Appointment {verb}",
                          f"Patient {a.patient.full_name} {verb} appointment {a.booking_code}.")


@api_bp.route("/appointments/<int:appointment_id>/accept", methods=["PATCH"])
@login_required
def api_accept(appointment_id):
    return _transition(appointment_id, "accept")


@api_bp.route("/appointments/<int:appointment_id>/decline", methods=["PATCH"])
@login_required
def api_decline(appointment_id):
    reason = (request.get_json(silent=True) or {}).get("reason")
    return _transition(appointment_id, "decline", reason=reason)


@api_bp.route("/appointments/<int:appointment_id>/complete", methods=["PATCH"])
@login_required
def api_complete(appointment_id):
    return _transition(appointment_id, "complete")


@api_bp.route("/appointments/<int:appointment_id>/cancel", methods=["PATCH"])
@login_required
def api_cancel(appointment_id):
    return _transition(appointment_id, "cancel")


@api_bp.route("/appointments/<int:appointment_id>/reschedule", methods=["PATCH"])
@login_required
def api_reschedule(appointment_id):
    return _transition(appointment_id, "reschedule")


# ---------------------------- NOTIFICATIONS ----------------------------

@api_bp.route("/notifications")
@login_required
def api_notifications():
    notes = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).all()
    return jsonify({"notifications": [{
        "id": n.id, "title": n.title, "message": n.message, "type": n.ntype,
        "is_read": n.is_read, "created": n.created_at.isoformat() if n.created_at else None,
    } for n in notes]})


@api_bp.route("/notifications/<int:note_id>/read", methods=["PATCH"])
@login_required
def api_mark_read(note_id):
    n = Notification.query.filter_by(id=note_id, user_id=current_user.id).first()
    if not n:
        return jsonify({"error": "Not found."}), 404
    n.is_read = True
    db.session.commit()
    return jsonify({"message": "Marked read."})


# ---------------------------- ADMIN ----------------------------

@api_bp.route("/admin/users")
@login_required
def api_admin_users():
    if current_user.role != ROLE_ADMIN:
        return jsonify({"error": "Admin only."}), 403
    return jsonify({"users": [user_payload(u) for u in User.query.all()]})


@api_bp.route("/admin/patients")
@login_required
def api_admin_patients():
    if current_user.role != ROLE_ADMIN:
        return jsonify({"error": "Admin only."}), 403
    patients = [{"id": p.id, "user_id": p.user_id, "full_name": p.full_name,
                 "email": p.user.email, "gender": p.gender, "is_active": p.user.is_active}
                for p in Patient.query.all()]
    return jsonify({"patients": patients})


@api_bp.route("/admin/providers")
@login_required
def api_admin_providers():
    if current_user.role != ROLE_ADMIN:
        return jsonify({"error": "Admin only."}), 403
    return jsonify({"providers": [provider_payload(p) for p in HealthcareProvider.query.all()]})


@api_bp.route("/admin/facilities")
@login_required
def api_admin_facilities():
    if current_user.role != ROLE_ADMIN:
        return jsonify({"error": "Admin only."}), 403
    return jsonify({"facilities": [facility_payload(f) for f in HealthcareFacility.query.all()]})


@api_bp.route("/admin/services")
@login_required
def api_admin_services():
    if current_user.role != ROLE_ADMIN:
        return jsonify({"error": "Admin only."}), 403
    return jsonify({"services": [service_payload(s) for s in Service.query.all()]})