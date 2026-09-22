from datetime import date, timedelta, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import (
    db, Patient, Service, HealthcareFacility, HealthcareProvider,
    Appointment, Notification, Speciality, ROLE_PATIENT,
    APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED,
    APPT_CANCELLED, APPT_RESCHEDULED, DAYS,
)
from helpers import (
    patient_required, send_notification, record_audit,
    slot_conflict_exists, generate_booking_code, time_in_slot,
)

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")


@patient_bp.before_request
@login_required
def restrict():
    if current_user.role != ROLE_PATIENT:
        abort(403)


@patient_bp.route("/")
@patient_bp.route("/dashboard")
def dashboard():
    patient = current_user.patient
    upcoming = (
        Appointment.query.filter_by(patient_id=patient.id, status=APPT_ACCEPTED)
        .order_by(Appointment.appointment_date)
        .limit(5)
        .all()
    )
    pending = (
        Appointment.query.filter_by(patient_id=patient.id, status=APPT_PENDING)
        .order_by(Appointment.appointment_date)
        .limit(5)
        .all()
    )
    history = (
        Appointment.query.filter_by(patient_id=patient.id)
        .order_by(Appointment.created_at.desc())
        .limit(5)
        .all()
    )
    recent_notifs = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template(
        "patient/dashboard.html",
        patient=patient,
        upcoming=upcoming,
        pending=pending,
        history=history,
        recent_notifs=recent_notifs,
        unread=unread,
    )


@patient_bp.route("/services")
def services():
    q = request.args.get("q", "").strip()
    query = Service.query.filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(Service.name.ilike(like) | Service.description.ilike(like))
    services = query.all()
    return render_template("patient/services.html", services=services, q=q)


@patient_bp.route("/service/<int:service_id>")
def service_detail(service_id):
    service = db.session.get(Service, service_id) or abort(404)
    providers = service.providers
    facilities = []
    seen = set()
    for p in providers:
        for f in p.facilities:
            if f.is_active and f.id not in seen:
                seen.add(f.id)
                count = len(
                    [pp for pp in providers if any(x.id == f.id for x in pp.facilities)]
                )
                facilities.append({"facility": f, "providers": count, "services": len(service.providers)})
    return render_template(
        "patient/service_detail.html", service=service, facilities=facilities, providers=providers
    )


@patient_bp.route("/facility/<int:facility_id>/service/<int:service_id>")
def facility_detail(facility_id, service_id):
    facility = db.session.get(HealthcareFacility, facility_id) or abort(404)
    service = db.session.get(Service, service_id) or abort(404)
    providers = [
        p
        for p in service.providers
        if any(f.id == facility.id for f in p.facilities)
    ]
    return render_template(
        "patient/facility_detail.html", facility=facility, service=service, providers=providers, DAYS=DAYS
    )


@patient_bp.route("/specialist/<int:provider_id>")
def specialist_detail(provider_id):
    provider = db.session.get(HealthcareProvider, provider_id) or abort(404)
    return render_template("patient/specialist_detail.html", provider=provider, DAYS=DAYS)


@patient_bp.route("/book")
def book():
    service_id = request.args.get("service_id", type=int)
    facility_id = request.args.get("facility_id", type=int)
    provider_id = request.args.get("provider_id", type=int)

    service = db.session.get(Service, service_id) if service_id else None
    facility = db.session.get(HealthcareFacility, facility_id) if facility_id else None
    provider = db.session.get(HealthcareProvider, provider_id) if provider_id else None

    if provider:
        available = [
            a
            for a in provider.availability
            if service is None or service in provider.services
        ]
        if service and service not in provider.services:
            flash("This specialist does not offer the selected service.", "error")
            return redirect(url_for("patient.service_detail", service_id=service.id))
        if facility and not any(f.id == facility.id for f in provider.facilities):
            flash("This specialist is not assigned to the selected facility.", "error")
            return redirect(url_for("patient.facility_detail", facility_id=facility.id, service_id=service.id))

        today = date.today()
        dates = []
        for offset in range(1, 15):
            d = today + timedelta(days=offset)
            if any(a in provider.availability for a in provider.availability if d.weekday() == a.day_week):
                dates.append(d)
        return render_template(
            "patient/book_appointment.html",
            service=service,
            facility=facility,
            provider=provider,
            dates=dates,
            DAYS=DAYS,
        )

    flash("Please select a service, facility and specialist first.", "info")
    return redirect(url_for("patient.services"))


@patient_bp.route("/availability/<int:provider_id>")
def provider_time_slots(provider_id):
    provider = db.session.get(HealthcareProvider, provider_id) or abort(404)
    date_str = request.args.get("date", "")
    try:
        chosen = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date"}, 400

    slots = []
    for a in provider.availability:
        if chosen.weekday() == a.day_week:
            start_h, start_m = map(int, a.start_time.split(":"))
            end_h, end_m = map(int, a.end_time.split(":"))
            t = start_h * 60 + start_m
            end = end_h * 60 + end_m
            step = 30
            while t + step <= end:
                hh, mm = divmod(t, 60)
                slot = f"{hh:02d}:{mm:02d}"
                if not slot_conflict_exists(provider.id, chosen, slot):
                    slots.append(slot)
                t += step
    return {"date": date_str, "slots": slots}


@patient_bp.route("/appointments/create", methods=["POST"])
def create_appointment():
    service_id = request.form.get("service_id", type=int)
    facility_id = request.form.get("facility_id", type=int)
    provider_id = request.form.get("provider_id", type=int)
    appt_date_str = request.form.get("appointment_date", "")
    appt_time = request.form.get("appointment_time", "")
    reason = request.form.get("reason_for_visit", "").strip()

    service = db.session.get(Service, service_id)
    facility = db.session.get(HealthcareFacility, facility_id)
    provider = db.session.get(HealthcareProvider, provider_id)
    patient = current_user.patient
    if not (service and facility and provider):
        flash("Invalid booking details.", "error")
        return redirect(url_for("patient.services"))

    try:
        appt_date = datetime.strptime(appt_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid appointment date.", "error")
        return redirect(url_for("patient.book",
                                service_id=service.id, facility_id=facility.id, provider_id=provider.id))

    if appt_date <= date.today():
        flash("Appointment date must be in the future.", "error")
        return redirect(url_for("patient.book",
                                service_id=service.id, facility_id=facility.id, provider_id=provider.id))

    available_ok = any(
        appt_date.weekday() == a.day_week
        and a.start_time <= appt_time <= a.end_time
        for a in provider.availability
    )
    if not available_ok:
        flash("Selected time is outside the specialist's availability window.", "error")
        return redirect(url_for("patient.book",
                                service_id=service.id, facility_id=facility.id, provider_id=provider.id))

    if service not in provider.services:
        flash("This specialist does not offer the selected service.", "error")
        return redirect(url_for("patient.service_detail", service_id=service.id))

    if any(f.id == facility.id for f in provider.facilities) is False:
        flash("This specialist is not assigned to the selected facility.", "error")
        return redirect(url_for("patient.facility_detail", facility_id=facility.id, service_id=service.id))

    if slot_conflict_exists(provider.id, appt_date, appt_time):
        flash("That time slot is no longer available. Please choose another.", "error")
        return redirect(url_for("patient.book",
                                service_id=service.id, facility_id=facility.id, provider_id=provider.id))

    code = generate_booking_code()
    appt = Appointment(
        booking_code=code,
        patient_id=patient.id,
        provider_id=provider.id,
        facility_id=facility.id,
        service_id=service.id,
        appointment_date=appt_date,
        appointment_time=appt_time,
        reason_for_visit=reason,
        status=APPT_PENDING,
    )
    db.session.add(appt)
    db.session.flush()

    from models import AppointmentStatusHistory
    db.session.add(
        AppointmentStatusHistory(
            appointment_id=appt.id, status=APPT_PENDING, changed_by_role="patient",
            note="Appointment request submitted",
        )
    )
    send_notification(
        patient.user_id,
        "Appointment request submitted",
        f"Your appointment request {code} for {service.name} with "
        f"{provider.title} {provider.full_name} on {appt_date.strftime('%d %b %Y')} "
        f"at {appt_time} has been submitted and is awaiting review.",
        "appointment",
    )
    send_notification(
        provider.user_id,
        "New appointment request",
        f"Patient {patient.full_name} has requested an appointment for {service.name} "
        f"at {facility.name} on {appt_date.strftime('%d %b %Y')} at {appt_time}.",
        "appointment",
    )
    record_audit("Appointment created", f"{code} by {patient.full_name}")
    db.session.commit()

    flash("Appointment request submitted successfully!", "success")
    return redirect(url_for("patient.confirmation", appointment_id=appt.id))


@patient_bp.route("/appointments")
def my_appointments():
    patient = current_user.patient
    status = request.args.get("status", "").strip()
    q = Appointment.query.filter_by(patient_id=patient.id)
    if status:
        q = q.filter(Appointment.status == status)
    appointments = q.order_by(Appointment.created_at.desc()).all()
    return render_template("patient/appointments.html", appointments=appointments, status=status, APPT_STATUSES=[
        APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED
    ])


@patient_bp.route("/appointments/<int:appointment_id>")
def appointment_detail(appointment_id):
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.patient_id != current_user.patient.id:
        abort(403)
    return render_template("patient/appointment_detail.html", appointment=appt, APPT_STATUSES=[
        APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED
    ])


@patient_bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
def cancel_appointment(appointment_id):
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.patient_id != current_user.patient.id:
        abort(403)
    if appt.status not in (APPT_PENDING, APPT_ACCEPTED):
        flash("This appointment cannot be cancelled in its current state.", "error")
        return redirect(url_for("patient.appointment_detail", appointment_id=appt.id))

    reason = request.form.get("reason", "").strip() or "Cancelled by patient"
    appt.status = APPT_CANCELLED
    appt.provider_response = reason
    from models import AppointmentStatusHistory
    db.session.add(
        AppointmentStatusHistory(appointment_id=appt.id, status=APPT_CANCELLED,
                                 changed_by_role="patient", note=reason)
    )
    send_notification(
        appt.provider.user_id,
        "Appointment cancelled",
        f"Patient {appt.patient.full_name} cancelled appointment {appt.booking_code} "
        f"({appt.service.name}) on {appt.appointment_date.strftime('%d %b %Y')} at {appt.appointment_time}.",
        "appointment",
    )
    send_notification(
        appt.patient.user_id,
        "Appointment cancelled",
        f"Your appointment {appt.booking_code} has been cancelled.",
        "appointment",
    )
    record_audit("Appointment cancelled", f"{appt.booking_code} by patient")
    db.session.commit()
    flash("Appointment cancelled.", "success")
    return redirect(url_for("patient.appointment_detail", appointment_id=appt.id))


@patient_bp.route("/appointments/<int:appointment_id>/reschedule", methods=["POST"])
def reschedule_appointment(appointment_id):
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.patient_id != current_user.patient.id:
        abort(403)
    if appt.status != APPT_ACCEPTED:
        flash("Only accepted appointments can be rescheduled.", "error")
        return redirect(url_for("patient.appointment_detail", appointment_id=appt.id))

    new_date_str = request.form.get("new_date", "")
    new_time = request.form.get("new_time", "")
    try:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid new date.", "error")
        return redirect(url_for("patient.appointment_detail", appointment_id=appt.id))

    valid_window = any(
        new_date.weekday() == a.day_week and a.start_time <= new_time <= a.end_time
        for a in appt.provider.availability
    )
    if not valid_window:
        flash("The new time is outside the specialist's availability.", "error")
        return redirect(url_for("patient.appointment_detail", appointment_id=appt.id))
    if slot_conflict_exists(appt.provider_id, new_date, new_time, exclude_appointment_id=appt.id):
        flash("That time slot is already booked.", "error")
        return redirect(url_for("patient.appointment_detail", appointment_id=appt.id))

    if not appt.original_date:
        appt.original_date = appt.appointment_date
        appt.original_time = appt.appointment_time
    appt.appointment_date = new_date
    appt.appointment_time = new_time
    appt.status = APPT_RESCHEDULED
    from models import AppointmentStatusHistory
    db.session.add(
        AppointmentStatusHistory(appointment_id=appt.id, status=APPT_RESCHEDULED,
                                 changed_by_role="patient",
                                 note=f"Rescheduled to {new_date} {new_time}")
    )
    send_notification(
        appt.provider.user_id,
        "Appointment rescheduled",
        f"Patient {appt.patient.full_name} rescheduled {appt.booking_code} "
        f"to {new_date.strftime('%d %b %Y')} at {new_time}. Please confirm the new time.",
        "appointment",
    )
    record_audit("Appointment rescheduled", f"{appt.booking_code} by patient")
    db.session.commit()
    flash("Reschedule request sent. The provider will confirm the new time.", "success")
    return redirect(url_for("patient.appointment_detail", appointment_id=appt.id))


@patient_bp.route("/appointments/<int:appointment_id>/confirmation")
def confirmation(appointment_id):
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.patient_id != current_user.patient.id:
        abort(403)
    return render_template("patient/confirmation.html", appointment=appt)


@patient_bp.route("/notifications")
def notifications():
    notes = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template("patient/notifications.html", notifications=notes)


@patient_bp.route("/notifications/mark-all-read", methods=["POST"])
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(url_for("patient.notifications"))


@patient_bp.route("/notifications/<int:note_id>/read", methods=["POST"])
def mark_note_read(note_id):
    note = Notification.query.filter_by(id=note_id, user_id=current_user.id).first()
    if note:
        note.is_read = True
        db.session.commit()
    return redirect(url_for("patient.notifications"))


@patient_bp.route("/profile", methods=["GET", "POST"])
def profile():
    patient = current_user.patient
    if request.method == "POST":
        patient.full_name = request.form.get("full_name", patient.full_name).strip()
        patient.gender = request.form.get("gender", patient.gender).strip()
        patient.address = request.form.get("address", patient.address).strip()
        patient.emergency_contact = request.form.get("emergency_contact", patient.emergency_contact).strip()
        dob = request.form.get("date_of_birth", "").strip()
        if dob:
            try:
                patient.date_of_birth = datetime.strptime(dob, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date of birth.", "error")
        current_user.username = request.form.get("username", current_user.username).strip()
        current_user.phone = request.form.get("phone", current_user.phone).strip()
        record_audit("Profile updated", current_user.email)
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("patient.profile"))
    return render_template("patient/profile.html", patient=patient)