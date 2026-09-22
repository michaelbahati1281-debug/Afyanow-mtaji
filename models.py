from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

ROLE_PATIENT = "patient"
ROLE_PROVIDER = "provider"
ROLE_ADMIN = "admin"
ROLES = [ROLE_PATIENT, ROLE_PROVIDER, ROLE_ADMIN]

APPT_PENDING = "pending"
APPT_ACCEPTED = "accepted"
APPT_DECLINED = "declined"
APPT_COMPLETED = "completed"
APPT_CANCELLED = "cancelled"
APPT_RESCHEDULED = "rescheduled"
APPT_STATUSES = [
    APPT_PENDING,
    APPT_ACCEPTED,
    APPT_DECLINED,
    APPT_COMPLETED,
    APPT_CANCELLED,
    APPT_RESCHEDULED,
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


association_provider_facility = db.Table(
    "provider_facilities",
    db.Column("provider_id", db.Integer, db.ForeignKey("healthcare_providers.id"), primary_key=True),
    db.Column("facility_id", db.Integer, db.ForeignKey("healthcare_facilities.id"), primary_key=True),
)

association_provider_service = db.Table(
    "provider_services",
    db.Column("provider_id", db.Integer, db.ForeignKey("healthcare_providers.id"), primary_key=True),
    db.Column("service_id", db.Integer, db.ForeignKey("services.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship("Patient", back_populates="user", uselist=False)
    provider = db.relationship("HealthcareProvider", back_populates="user", uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def display_name(self):
        if self.patient:
            return self.patient.full_name
        if self.provider:
            return self.provider.full_name
        return self.username

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    emergency_contact = db.Column(db.String(60), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="patient")
    appointments = db.relationship("Appointment", back_populates="patient")


class Speciality(db.Model):
    __tablename__ = "specialties"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    providers = db.relationship("HealthcareProvider", back_populates="speciality")


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    specialty = db.relationship("Speciality")
    providers = db.relationship(
        "HealthcareProvider", secondary=association_provider_service, back_populates="services"
    )

    def provider_count(self):
        return len(self.providers)


class HealthcareFacility(db.Model):
    __tablename__ = "healthcare_facilities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    providers = db.relationship(
        "HealthcareProvider", secondary=association_provider_facility, back_populates="facilities"
    )

    def provider_count(self):
        return len(self.providers)


class HealthcareProvider(db.Model):
    __tablename__ = "healthcare_providers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(30), default="Dr.")
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=True)
    qualifications = db.Column(db.Text, nullable=True)
    experience_years = db.Column(db.Integer, default=0)
    bio = db.Column(db.Text, nullable=True)
    license_number = db.Column(db.String(60), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="provider")
    speciality = db.relationship("Speciality", back_populates="providers")
    facilities = db.relationship(
        "HealthcareFacility", secondary=association_provider_facility, back_populates="providers"
    )
    services = db.relationship(
        "Service", secondary=association_provider_service, back_populates="providers"
    )
    availability = db.relationship(
        "ProviderAvailability", back_populates="provider", cascade="all, delete-orphan"
    )
    appointments = db.relationship("Appointment", back_populates="provider")

    def service_names(self):
        return ", ".join(s.name for s in self.services)

    def facility_names(self):
        return ", ".join(f.name for f in self.facilities)

    def working_days(self):
        return [a.day_week for a in self.availability]


class ProviderAvailability(db.Model):
    __tablename__ = "provider_availability"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("healthcare_providers.id"), nullable=False)
    day_week = db.Column(db.Integer, nullable=False)  # 0 = Monday ... 6 = Sunday
    start_time = db.Column(db.String(5), nullable=False)  # "09:00"
    end_time = db.Column(db.String(5), nullable=False)  # "17:00"

    provider = db.relationship("HealthcareProvider", back_populates="availability")


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    booking_code = db.Column(db.String(20), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey("healthcare_providers.id"), nullable=False)
    facility_id = db.Column(db.Integer, db.ForeignKey("healthcare_facilities.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.String(5), nullable=False)
    reason_for_visit = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=APPT_PENDING, nullable=False)
    provider_response = db.Column(db.Text, nullable=True)
    original_date = db.Column(db.Date, nullable=True)
    original_time = db.Column(db.String(5), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = db.relationship("Patient", back_populates="appointments")
    provider = db.relationship("HealthcareProvider", back_populates="appointments")
    facility = db.relationship("HealthcareFacility")
    service = db.relationship("Service")
    status_history = db.relationship(
        "AppointmentStatusHistory",
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentStatusHistory.created_at",
    )

    def label(self):
        return f"{self.booking_code} - {self.service.name}"


class AppointmentStatusHistory(db.Model):
    __tablename__ = "appointment_status_history"

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    changed_by_role = db.Column(db.String(20), nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointment = db.relationship("Appointment", back_populates="status_history")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    ntype = db.Column(db.String(30), default="info")
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(150), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    audience = db.Column(db.String(20), nullable=False)  # patient / provider / all
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)