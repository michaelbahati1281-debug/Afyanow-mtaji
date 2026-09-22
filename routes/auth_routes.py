from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from models import (
    db, User, Patient, Speciality, Service,
    ROLE_PATIENT, ROLE_PROVIDER, ROLE_ADMIN, ROLES,
)
from helpers import send_notification, record_audit

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect("/dashboard")

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        if not identifier or not password:
            flash("Please enter your email/username/phone and password.", "error")

        elif not current_app_has(identifier):
            flash("No account found with those details.", "error")
        else:
            user = get_user_by_identifier(identifier)
            if not user.check_password(password):
                flash("Incorrect password. Please try again.", "error")
            elif not user.is_active:
                flash("This account has been deactivated. Contact an administrator.", "error")
            else:
                login_user(user)
                record_audit(f"Login: {user.role}")
                db.session.commit()
                if user.role == ROLE_ADMIN:
                    return redirect(url_for("admin.dashboard"))
                if user.role == ROLE_PROVIDER:
                    return redirect(url_for("provider.dashboard"))
                return redirect(url_for("patient.dashboard"))

    return render_template("login.html")


def current_app_has(identifier):
    return get_user_by_identifier(identifier) is not None


def get_user_by_identifier(identifier):
    return (
        User.query.filter(
            (User.email == identifier.lower())
            | (User.username == identifier)
            | (User.phone == identifier)
        ).first()
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect("/dashboard")

    if request.method == "POST":
        form = request.form
        full_name = form.get("full_name", "").strip()
        email = form.get("email", "").strip().lower()
        phone = form.get("phone", "").strip()
        password = form.get("password", "")
        confirm = form.get("confirm_password", "")
        gender = form.get("gender", "").strip()
        dob = form.get("date_of_birth", "").strip()

        errors = []
        if not full_name or len(full_name.split()) < 2:
            errors.append("Please enter your full name (first and last name).")
        if not email or "@" not in email or "." not in email:
            errors.append("Please enter a valid email address.")
        if not phone:
            errors.append("Please enter a phone number.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")
        if User.query.filter_by(phone=phone).first():
            errors.append("An account with that phone number already exists.")

        if errors:
            for msg in errors:
                flash(msg, "error")
            return render_template("register.html", form=form)

        username = email.split("@")[0]
        base = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base}{counter}"
            counter += 1

        user = User(username=username, email=email, phone=phone, role=ROLE_PATIENT)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        try:
            parsed_dob = datetime.strptime(dob, "%Y-%m-%d").date() if dob else None
        except ValueError:
            parsed_dob = None

        patient = Patient(
            user_id=user.id,
            full_name=full_name,
            gender=gender,
            date_of_birth=parsed_dob,
        )
        db.session.add(patient)
        db.session.flush()

        send_notification(
            user.id,
            "Welcome to AfyaNow",
            f"Welcome {full_name}! Your patient account has been created. You can now book "
            "appointments with specialized healthcare providers.",
            "welcome",
        )
        record_audit("Patient registration", f"New patient account: {email}")
        db.session.commit()

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect("/dashboard")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        flash(
            "If an account exists for that email, a password reset link has been sent. "
            "(Demo mode: reset links are simulated.)",
            "info",
        )
        if user:
            record_audit("Password reset requested", email)
            db.session.commit()
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


@auth_bp.route("/logout")
@login_required
def logout():
    role = current_user.role
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == ROLE_ADMIN:
        return redirect(url_for("admin.dashboard"))
    if current_user.role == ROLE_PROVIDER:
        return redirect(url_for("provider.dashboard"))
    return redirect(url_for("patient.dashboard"))