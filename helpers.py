import functools
from datetime import datetime

from flask import flash, abort, redirect, url_for
from flask_login import current_user, LoginManager

from models import (
    db,
    User,
    Notification,
    Appointment,
    AuditLog,
    APPT_PENDING,
    APPT_ACCEPTED,
)


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def send_notification(user_id, title, message, ntype="info"):
    note = Notification(user_id=user_id, title=title, message=message, ntype=ntype)
    db.session.add(note)
    return note


def record_audit(action, details=None):
    log = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        details=details,
    )
    db.session.add(log)


def role_required(*roles):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in first.", "warning")
                return redirect(url_for("auth.login", next=fn.__name__))
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper

    return decorator


def patient_required(fn):
    return role_required("patient")(fn)


def provider_required(fn):
    return role_required("provider")(fn)


def admin_required(fn):
    return role_required("admin")(fn)


def slot_conflict_exists(provider_id, appt_date, appt_time, exclude_appointment_id=None):
    """Business rule 6: a provider cannot have two appointments in the same time slot."""
    q = Appointment.query.filter(
        Appointment.provider_id == provider_id,
        Appointment.appointment_date == appt_date,
        Appointment.appointment_time == appt_time,
        Appointment.status.in_([APPT_PENDING, APPT_ACCEPTED]),
    )
    if exclude_appointment_id:
        q = q.filter(Appointment.id != exclude_appointment_id)
    return db.session.query(q.exists()).scalar()


def time_in_slot(day_week, start_time, end_time, date_obj, time_str):
    """Check if (date, time) falls inside a provider's availability window."""
    from datetime import date as date_type
    if date_obj.weekday() != day_week:
        return False
    return start_time <= time_str < end_time or start_time <= time_str <= end_time


def generate_booking_code():
    from random import choices
    from string import ascii_uppercase, digits
    n = datetime.now()
    prefix = f"AP-{n.strftime('%Y%m%d')}-"
    return prefix + "".join(choices(ascii_uppercase + digits, k=5))


def dashboard_redirect():
    """Redirect authenticated users to their role dashboard."""
    if current_user.role == "admin":
        return url_for("admin.dashboard")
    if current_user.role == "provider":
        return url_for("provider.dashboard")
    return url_for("patient.dashboard")