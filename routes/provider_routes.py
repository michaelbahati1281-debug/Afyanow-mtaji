from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import (
    db, HealthcareProvider, Appointment, Notification, DAYS,
    ROLE_PROVIDER,
    APPT_PENDING, APPT_ACCEPTED, APPT_COMPLETED, APPT_DECLINED,
    APPT_CANCELLED, APPT_RESCHEDULED, AppointmentStatusHistory,
)
from helpers import (
    provider_required, send_notification, record_audit, slot_conflict_exists,
)

provider_bp = Blueprint("provider", __name__, url_prefix="/provider")


@provider_bp.before_request
@login_required
def restrict():
    if current_user.role != ROLE_PROVIDER:
        abort(403)


def provider_or_abort():
    provider = current_user.provider
    if not provider:
        abort(403)
    return provider


@provider_bp.route("/")
@provider_bp.route("/dashboard")
def dashboard():
    provider = provider_or_abort()
    today = date.today()
    todays_appts = (
        Appointment.query.filter_by(provider_id=provider.id, appointment_date=today)
        .order_by(Appointment.appointment_time)
        .all()
    )
    pending = (
        Appointment.query.filter_by(provider_id=provider.id, status=APPT_PENDING)
        .order_by(Appointment.appointment_date)
        .limit(5)
        .all()
    )
    upcoming = (
        Appointment.query.filter(
            Appointment.provider_id == provider.id,
            Appointment.status == APPT_ACCEPTED,
            Appointment.appointment_date >= today,
        )
        .order_by(Appointment.appointment_date)
        .limit(5)
        .all()
    )
    history = (
        Appointment.query.filter_by(provider_id=provider.id, status=APPT_COMPLETED)
        .order_by(Appointment.appointment_date.desc())
        .limit(5)
        .all()
    )
    recent_notifs = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "provider/dashboard.html",
        provider=provider,
        today=today,
        todays_appts=todays_appts,
        pending=pending,
        upcoming=upcoming,
        history=history,
        recent_notifs=recent_notifs,
        APPT_STATUSES=[APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED],
    )


@provider_bp.route("/appointments")
def appointments():
    provider = provider_or_abort()
    status = request.args.get("status", "").strip()
    today = date.today()
    view = request.args.get("view", "all")
    q = Appointment.query.filter_by(provider_id=provider.id)
    if view == "upcoming":
        q = q.filter(
            Appointment.status.in_([APPT_PENDING, APPT_ACCEPTED]),
            Appointment.appointment_date >= today,
        )
    elif view == "history":
        q = q.filter(
            Appointment.status.in_([APPT_COMPLETED, APPT_DECLINED, APPT_CANCELLED])
        )
    if status:
        q = q.filter(Appointment.status == status)
    appointments = q.order_by(Appointment.appointment_date.desc()).all()
    return render_template(
        "provider/appointments.html",
        appointments=appointments,
        status=status,
        view=view,
        APPT_STATUSES=[APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED],
    )


@provider_bp.route("/appointments/<int:appointment_id>")
def appointment_detail(appointment_id):
    provider = provider_or_abort()
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.provider_id != provider.id:
        abort(403)
    return render_template(
        "provider/appointment_detail.html",
        appointment=appt,
        APPT_STATUSES=[APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED, APPT_CANCELLED, APPT_RESCHEDULED],
    )


@provider_bp.route("/appointments/<int:appointment_id>/accept", methods=["POST"])
def accept_appointment(appointment_id):
    provider = provider_or_abort()
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.provider_id != provider.id:
        abort(403)
    if appt.status != APPT_PENDING:
        flash("Only pending requests can be accepted.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    if slot_conflict_exists(appt.provider_id, appt.appointment_date, appt.appointment_time,
                            exclude_appointment_id=appt.id):
        flash("You already have another appointment in that time slot. "
              "Reschedule or decline this request instead.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    appt.status = APPT_ACCEPTED
    appt.provider_response = request.form.get("note", "").strip() or "Appointment accepted"
    db.session.add(
        AppointmentStatusHistory(appointment_id=appt.id, status=APPT_ACCEPTED,
                                 changed_by_role="provider", note="Appointment accepted")
    )
    send_notification(
        appt.patient.user_id,
        "Appointment accepted",
        f"Your appointment {appt.booking_code} ({appt.service.name}) with "
        f"{provider.title} {provider.full_name} on {appt.appointment_date.strftime('%d %b %Y')} "
        f"at {appt.appointment_time} has been ACCEPTED. See you soon!",
        "appointment",
    )
    record_audit("Appointment accepted", f"{appt.booking_code} by provider")
    db.session.commit()
    flash("Appointment accepted. The patient has been notified.", "success")
    return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))


@provider_bp.route("/appointments/<int:appointment_id>/decline", methods=["POST"])
def decline_appointment(appointment_id):
    provider = provider_or_abort()
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.provider_id != provider.id:
        abort(403)
    if appt.status not in (APPT_PENDING, APPT_RESCHEDULED):
        flash("This appointment can no longer be declined.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Please provide a reason for declining.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    appt.status = APPT_DECLINED
    appt.provider_response = reason
    db.session.add(
        AppointmentStatusHistory(appointment_id=appt.id, status=APPT_DECLINED,
                                 changed_by_role="provider", note=reason)
    )
    send_notification(
        appt.patient.user_id,
        "Appointment declined",
        f"Your appointment {appt.booking_code} ({appt.service.name}) was declined by "
        f"{provider.title} {provider.full_name}. Reason: {reason}",
        "appointment",
    )
    record_audit("Appointment declined", f"{appt.booking_code} by provider")
    db.session.commit()
    flash("Appointment declined. The patient has been notified.", "success")
    return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))


@provider_bp.route("/appointments/<int:appointment_id>/complete", methods=["POST"])
def complete_appointment(appointment_id):
    provider = provider_or_abort()
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.provider_id != provider.id:
        abort(403)
    if appt.status not in (APPT_ACCEPTED, APPT_RESCHEDULED):
        flash("Only accepted appointments can be marked completed.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    appt.status = APPT_COMPLETED
    appt.provider_response = request.form.get("note", "").strip() or "Patient attended"
    db.session.add(
        AppointmentStatusHistory(appointment_id=appt.id, status=APPT_COMPLETED,
                                 changed_by_role="provider", note="Appointment completed")
    )
    send_notification(
        appt.patient.user_id,
        "Appointment completed",
        f"Your appointment {appt.booking_code} ({appt.service.name}) has been marked completed.",
        "appointment",
    )
    record_audit("Appointment completed", f"{appt.booking_code} by provider")
    db.session.commit()
    flash("Appointment marked as completed.", "success")
    return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))


@provider_bp.route("/appointments/<int:appointment_id>/reschedule", methods=["POST"])
def reschedule_appointment(appointment_id):
    provider = provider_or_abort()
    appt = db.session.get(Appointment, appointment_id) or abort(404)
    if appt.provider_id != provider.id:
        abort(403)
    if appt.status not in (APPT_PENDING, APPT_ACCEPTED, APPT_RESCHEDULED):
        flash("This appointment cannot be rescheduled in its current state.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    new_date_str = request.form.get("new_date", "")
    new_time = request.form.get("new_time", "")
    try:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid new date.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    valid_window = any(
        new_date.weekday() == a.day_week and a.start_time <= new_time <= a.end_time
        for a in provider.availability
    )
    if not valid_window:
        flash("The new time falls outside your configured availability.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))
    if slot_conflict_exists(appt.provider_id, new_date, new_time, exclude_appointment_id=appt.id):
        flash("You already have another appointment in that time slot.", "error")
        return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))

    if not appt.original_date:
        appt.original_date = appt.appointment_date
        appt.original_time = appt.appointment_time
    appt.appointment_date = new_date
    appt.appointment_time = new_time
    appt.status = APPT_RESCHEDULED
    db.session.add(
        AppointmentStatusHistory(appointment_id=appt.id, status=APPT_RESCHEDULED,
                                 changed_by_role="provider",
                                 note=f"Rescheduled to {new_date} {new_time}")
    )
    send_notification(
        appt.patient.user_id,
        "Appointment rescheduled",
        f"Dr. {provider.full_name} rescheduled your appointment {appt.booking_code} "
        f"to {new_date.strftime('%d %b %Y')} at {new_time}.",
        "appointment",
    )
    record_audit("Appointment rescheduled", f"{appt.booking_code} by provider")
    db.session.commit()
    flash("Appointment rescheduled and the patient has been notified.", "success")
    return redirect(url_for("provider.appointment_detail", appointment_id=appt.id))


@provider_bp.route("/availability", methods=["GET", "POST"])
def availability():
    provider = provider_or_abort()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "add":
            day = request.form.get("day", type=int)
            start = request.form.get("start_time", "")
            end = request.form.get("end_time", "")
            if day is None or not (0 <= day <= 6):
                flash("Please select a valid day.", "error")
            elif not start or not end:
                flash("Please enter start and end times.", "error")
            elif start >= end:
                flash("Start time must be before end time.", "error")
            else:
                dup = any(
                    a.day_week == day and a.start_time == start and a.end_time == end
                    for a in provider.availability
                )
                if dup:
                    flash("That window already exists.", "error")
                else:
                    from models import ProviderAvailability
                    db.session.add(
                        ProviderAvailability(provider_id=provider.id, day_week=day,
                                             start_time=start, end_time=end)
                    )
                    record_audit("Availability added", f"Provider {provider.full_name}")
                    db.session.commit()
                    flash("Availability added.", "success")
        elif action == "delete":
            slot_id = request.form.get("slot_id", type=int)
            from models import ProviderAvailability
            slot = db.session.get(ProviderAvailability, slot_id)
            if slot and slot.provider_id == provider.id:
                db.session.delete(slot)
                record_audit("Availability removed", f"Provider {provider.full_name}")
                db.session.commit()
                flash("Availability slot removed.", "success")
        return redirect(url_for("provider.availability"))

    return render_template("provider/availability.html", provider=provider, DAYS=DAYS)


@provider_bp.route("/profile", methods=["GET", "POST"])
def profile():
    provider = provider_or_abort()
    if request.method == "POST":
        provider.full_name = request.form.get("full_name", provider.full_name).strip()
        current_user.phone = request.form.get("phone", current_user.phone).strip()
        record_audit("Profile updated", current_user.email)
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("provider.profile"))
    return render_template("provider/profile.html", provider=provider)


@provider_bp.route("/notifications")
def notifications():
    notes = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template("provider/notifications.html", notifications=notes)


@provider_bp.route("/notifications/mark-all-read", methods=["POST"])
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(url_for("provider.notifications"))


@provider_bp.route("/notifications/<int:note_id>/read", methods=["POST"])
def mark_note_read(note_id):
    note = Notification.query.filter_by(id=note_id, user_id=current_user.id).first()
    if note:
        note.is_read = True
        db.session.commit()
    return redirect(url_for("provider.notifications"))