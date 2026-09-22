"""
AfyaNow demo seed data.

Run with:  python seed.py
It creates demo accounts, services, facilities, providers, availability,
appointments, notifications and audit logs for a full demonstration.

DEMO CREDENTIALS (development only - not for production):
    Admin:    admin@example.com      / Admin@123
    Doctor:   doctor@example.com     / Doctor@123
    Patient:  patient@example.com    / Patient@123
"""
import random
from datetime import datetime, date, timedelta

from app import create_app
from models import (
    db, User, Patient, HealthcareProvider, Speciality, Service,
    HealthcareFacility, ProviderAvailability, Appointment,
    AppointmentStatusHistory, Notification, AuditLog, Announcement,
    ROLE_PATIENT, ROLE_PROVIDER, ROLE_ADMIN,
    APPT_PENDING, APPT_ACCEPTED, APPT_DECLINED, APPT_COMPLETED,
    APPT_CANCELLED, APPT_RESCHEDULED,
)

app = None
ctx = None


def create_user(username, email, phone, role, password, is_active=True):
    u = User(username=username, email=email, phone=phone, role=role, is_active=is_active)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    return u


def main():
    global app, ctx
    app = create_app()
    ctx = app.app_context()
    ctx.push()

    db.drop_all()
    db.create_all()
    print("Database reset.")

    # ---------------- Specialties ----------------
    spec_names = [
        ("Cardiology", "Diagnosis and treatment of heart and blood vessel conditions."),
        ("Neurology", "Treatment of disorders of the nervous system."),
        ("Dermatology", "Care of skin, hair and nails."),
        ("Orthopaedics", "Treatment of bones, joints and muscles."),
        ("Ophthalmology", "Eye and vision care."),
        ("Dentistry", "Oral health and dental care."),
        ("Psychiatry", "Mental health diagnosis and treatment."),
        ("Physiotherapy", "Physical rehabilitation and movement therapy."),
        ("Gynaecology", "Women's reproductive health."),
        ("Paediatrics", "Medical care for infants, children and adolescents."),
        ("ENT", "Ear, nose and throat care."),
        ("Urology", "Urinary tract and male reproductive health."),
        ("General Surgery", "Surgical treatment of a wide range of conditions."),
        ("Radiology", "Medical imaging and diagnostic scans."),
        ("Oncology", "Cancer diagnosis and treatment."),
        ("Laboratory Services", "Diagnostic laboratory testing."),
    ]
    specs = {}
    for name, desc in spec_names:
        s = Speciality(name=name, description=desc)
        db.session.add(s)
        specs[name] = s
    db.session.flush()

    # ---------------- Services ----------------
    service_descriptions = {
        "Cardiology": "Heart check-ups, ECG, echocardiography and management of heart disease.",
        "Neurology": "Migraine, epilepsy, stroke recovery and neurological assessments.",
        "Dermatology": "Skin conditions, acne, eczema, psoriasis and mole screening.",
        "Orthopaedics": "Fracture care, joint replacement and sports injuries.",
        "Ophthalmology": "Eye examinations, cataract care and vision correction.",
        "Dentistry": "Cleanings, fillings, extraction and cosmetic dental care.",
        "Psychiatry": "Anxiety, depression and general mental health consultations.",
        "Physiotherapy": "Rehabilitation, posture correction and pain management.",
        "Gynaecology": "Well-woman checks, antenatal care and reproductive health.",
        "Paediatrics": "Childhood check-ups, vaccinations and growth monitoring.",
        "ENT": "Ear infections, sinusitis and throat care.",
        "Urology": "Kidney stones, prostate care and urinary tract health.",
        "General Surgery": "Surgical consultations and minor procedures.",
        "Radiology": "X-ray, ultrasound, CT and MRI imaging services.",
        "Oncology": "Cancer screening, diagnosis and treatment planning.",
        "Laboratory Services": "Blood tests, urine tests and pathology services.",
    }
    services = {}
    for name, desc in service_descriptions.items():
        svc = Service(name=name, description=desc, specialty_id=specs[name].id)
        db.session.add(svc)
        services[name] = svc
    db.session.flush()

    # ---------------- Facilities ----------------
    facility_data = [
        ("AfyaNow General Hospital", "12 Hospital Road", "Nairobi", "+254 700 111 001", "info@afyanowgeneral.co.ke"),
        ("Meridian Specialists Clinic", "45 Meridian Avenue", "Mombasa", "+254 700 111 002", "care@meridian.co.ke"),
        ("Savanna Medical Centre", "88 Savanna Plaza", "Kisumu", "+254 700 111 003", "hello@savannamed.co.ke"),
        ("Lakeview Health Institute", "23 Lakeview Drive", "Nakuru", "+254 700 111 004", "contact@lakeview.co.ke"),
        ("Highlands Medical Suites", "301 Highlands Road", "Eldoret", "+254 700 111 005", "suites@highlands.co.ke"),
    ]
    facilities = {}
    for name, addr, city, phone, mail in facility_data:
        f = HealthcareFacility(name=name, address=addr, city=city, phone=phone, email=mail,
                               description=f"{name} - a modern, patient-centred healthcare facility "
                                           "offering specialized outpatient and diagnostic services.")
        db.session.add(f)
        facilities[name] = f
    db.session.flush()

    # ---------------- Administrator ----------------
    admin_user = create_user("admin", "admin@example.com", "+254700000001", ROLE_ADMIN, "Admin@123")
    db.session.add(admin_user)
    db.session.flush()

    # ---------------- Providers ----------------
    provider_data = [
        ("Dr. John Michael", "Cardiology", "MBChB, MMed (Cardiology), FESC", 10,
         "Consultant cardiologist passionate about preventive heart care and cardiac rehabilitation.",
         ["AfyaNow General Hospital", "Meridian Specialists Clinic"],
         ["Cardiology", "Radiology"], "KMCR/CARD/00112"),
        ("Dr. Sarah Joseph", "Cardiology", "MBBS, MD (Internal Medicine), DM Cardiology", 7,
         "Specialist in hypertension, arrhythmia and echocardiography.",
         ["AfyaNow General Hospital"],
         ["Cardiology"], "KMCR/CARD/00154"),
        ("Dr. David Otieno", "Neurology", "MBChB, MMed (Neurology)", 12,
         "Neurologist focusing on epilepsy, stroke and movement disorders.",
         ["Savanna Medical Centre", "Lakeview Health Institute"],
         ["Neurology", "Radiology"], "KMCR/NEU/00201"),
        ("Dr. Amina Hassan", "Dermatology", "MBBS, MCPS (Dermatology)", 6,
         "Dermatologist with an interest in paediatric skin conditions.",
         ["Meridian Specialists Clinic"],
         ["Dermatology"], "KMCR/DER/00333"),
        ("Dr. Peter Njoroge", "Orthopaedics", "MD, FCS (Orth) SA", 15,
         "Orthopaedic surgeon specializing in joint replacement and sports injuries.",
         ["AfyaNow General Hospital", "Lakeview Health Institute"],
         ["Orthopaedics", "General Surgery", "Radiology"], "KMCR/ORT/00421"),
        ("Dr. Grace Wanjiku", "Ophthalmology", "MBChB, MMed (Ophthalmology)", 9,
         "Cataract surgeon and paediatric ophthalmologist.",
         ["Highlands Medical Suites"],
         ["Ophthalmology"], "KMCR/OPH/00577"),
        ("Dr. James Kimani", "Dentistry", "BDS, MSc Oral Surgery", 8,
         "Oral and maxillofacial surgeon with a gentle chairside manner.",
         ["Meridian Specialists Clinic", "AfyaNow General Hospital"],
         ["Dentistry", "General Surgery"], "KMCR/DEN/00612"),
        ("Dr. Faith Chebet", "Physiotherapy", "BSc Physiotherapy, MSc Sports Rehab", 5,
         "Physiotherapist helping patients recover movement and strength.",
         ["Savanna Medical Centre"],
         ["Physiotherapy"], "KMCR/PHY/00745"),
        ("Dr. Oscar Kiptoo", "Paediatrics", "MBChB, MMed (Paediatrics)", 11,
         "Paediatrician dedicated to child wellness, nutrition and immunisation.",
         ["AfyaNow General Hospital", "Highlands Medical Suites"],
         ["Paediatrics", "Cardiology"], "KMCR/PAE/00809"),
        ("Dr. Cynthia Auma", "Gynaecology", "MBChB, MMed (Obs & Gyn)", 13,
         "Consultant obstetrician-gynaecologist and fertility specialist.",
         ["Lakeview Health Institute", "AfyaNow General Hospital"],
         ["Gynaecology"], "KMCR/GYN/00988"),
        ("Dr. Brian Mwangi", "ENT", "MBChB, MMed (ENT)", 7,
         "ENT specialist for hearing, balance, allergy and sinus care.",
         ["Meridian Specialists Clinic"],
         ["ENT"], "KMCR/ENT/01021"),
        ("Dr. Esther Ouko", "Psychiatry", "MBBS, MMed (Psychiatry)", 10,
         "Psychiatrist offering compassionate mental health care for all ages.",
         ["Savanna Medical Centre", "Highlands Medical Suites"],
         ["Psychiatry"], "KMCR/PSY/01134"),
    ]

    providers = {}
    for idx, (full_name, spec, quals, years, bio, fac_names, svc_names, lic) in enumerate(provider_data):
        slug = full_name.lower().replace(".", "").replace(" ", "_")
        email = "doctor@example.com" if idx == 0 else (
            full_name.lower().replace(" ", "").replace(".", "") + "@example.com")
        u = create_user(slug, email, f"+2547{random.randint(10000000, 99999999)}",
                        ROLE_PROVIDER, "Doctor@123")
        p = HealthcareProvider(
            user_id=u.id, full_name=full_name,
            title="Dr." if not full_name.startswith("Dr") else "Dr.",
            specialty_id=specs[spec].id, qualifications=quals,
            experience_years=years, bio=bio, license_number=lic,
        )
        db.session.add(p)
        db.session.flush()
        p.facilities = [facilities[n] for n in fac_names]
        p.services = [services[n] for n in svc_names]
        providers[full_name] = p
    db.session.flush()

    # ---------------- Provider availability ----------------
    availability_map = {
        "Dr. John Michael": [(0, "08:00", "12:00"), (0, "13:00", "16:00"), (2, "08:00", "13:00"), (4, "09:00", "14:00")],
        "Dr. Sarah Joseph": [(1, "09:00", "13:00"), (3, "09:00", "13:00")],
        "Dr. David Otieno": [(0, "10:00", "15:00"), (3, "08:00", "12:00"), (5, "09:00", "13:00")],
        "Dr. Amina Hassan": [(1, "08:00", "14:00"), (4, "08:00", "13:00")],
        "Dr. Peter Njoroge": [(2, "08:00", "16:00"), (5, "08:00", "13:00")],
        "Dr. Grace Wanjiku": [(0, "09:00", "14:00"), (2, "09:00", "12:00")],
        "Dr. James Kimani": [(1, "08:00", "15:00"), (3, "08:00", "15:00"), (5, "09:00", "13:00")],
        "Dr. Faith Chebet": [(2, "09:00", "16:00"), (4, "09:00", "16:00")],
        "Dr. Oscar Kiptoo": [(0, "08:00", "12:00"), (2, "08:00", "13:00"), (5, "08:00", "12:00")],
        "Dr. Cynthia Auma": [(1, "08:00", "13:00"), (3, "09:00", "15:00")],
        "Dr. Brian Mwangi": [(2, "09:00", "14:00"), (4, "10:00", "15:00")],
        "Dr. Esther Ouko": [(0, "09:00", "16:00"), (3, "10:00", "15:00")],
    }
    for name, slots in availability_map.items():
        for day, start, end in slots:
            db.session.add(ProviderAvailability(
                provider_id=providers[name].id, day_week=day,
                start_time=start, end_time=end))
    db.session.flush()

    # ---------------- Patients ----------------
    patient_data = [
        ("Alice Wanjiru", "patient@example.com", "+254711111111", "Female", "1992-04-12", "Nairobi"),
        ("Brian Kipchoge", "brian.patient@example.com", "+254722222222", "Male", "1988-09-30", "Kisumu"),
        ("Catherine Muthoni", "cathy.patient@example.com", "+254733333333", "Female", "1995-01-25", "Mombasa"),
        ("Daniel Okello", "daniel.patient@example.com", "+254744444444", "Male", "1975-06-18", "Nakuru"),
        ("Fatuma Zahra", "fatuma.patient@example.com", "+254755555555", "Female", "2000-12-02", "Eldoret"),
    ]
    patients = {}
    for name, email, phone, gender, dob, city in patient_data:
        u = create_user(email.split("@")[0], email, phone, ROLE_PATIENT, "Patient@123")
        d = datetime.strptime(dob, "%Y-%m-%d").date()
        pat = Patient(user_id=u.id, full_name=name, gender=gender, date_of_birth=d, address=f"City: {city}")
        db.session.add(pat)
        patients[name] = (u, pat)
    db.session.flush()

    # ---------------- Appointments (mixed statuses) ----------------
    today = date.today()
    appt_records = [
        # (patient, provider, service, facility, days_from_today, time, reason, status, response, age_days)
        ("Alice Wanjiru", "Dr. John Michael", "Cardiology", "AfyaNow General Hospital", 3, "10:00",
         "Recurring chest tightness and blood pressure review", APPT_ACCEPTED, "Happy to see you.", 2),
        ("Brian Kipchoge", "Dr. Peter Njoroge", "Orthopaedics", "AfyaNow General Hospital", 1, "09:00",
         "Right knee pain after playing football", APPT_PENDING, None, 1),
        ("Catherine Muthoni", "Dr. Amina Hassan", "Dermatology", "Meridian Specialists Clinic", 2, "11:00",
         "Persistent acne and skin irritation", APPT_ACCEPTED, "Please bring your current skincare products.", 2),
        ("Daniel Okello", "Dr. David Otieno", "Neurology", "Savanna Medical Centre", 5, "14:00",
         "Recurring migraines for the past month", APPT_PENDING, None, 1),
        ("Fatuma Zahra", "Dr. Grace Wanjiku", "Ophthalmology", "Highlands Medical Suites", 4, "10:00",
         "Routine eye check and prescription renewal", APPT_PENDING, None, 0),
        ("Alice Wanjiru", "Dr. James Kimani", "Dentistry", "Meridian Specialists Clinic", -10, "09:30",
         "Tooth filling review", APPT_COMPLETED, "Healing well. Return in 6 months.", 25),
        ("Brian Kipchoge", "Dr. Cynthia Auma", "Gynaecology", "Lakeview Health Institute", -20, "12:00",
         "Annual wellness screening", APPT_COMPLETED, "All results normal.", 30),
        ("Catherine Muthoni", "Dr. Esther Ouko", "Psychiatry", "Savanna Medical Centre", -6, "15:00",
         "Anxiety management session", APPT_DECLINED, "Provider unavailable that week; please rebook.", 12),
        ("Daniel Okello", "Dr. Oscar Kiptoo", "Paediatrics", "AfyaNow General Hospital", -3, "08:30",
         "Child vaccination appointment", APPT_CANCELLED, "Cancelled by patient - child had fever.", 8),
        ("Fatuma Zahra", "Dr. Sarah Joseph", "Cardiology", "AfyaNow General Hospital", -2, "13:00",
         "ECG follow-up", APPT_COMPLETED, "ECG normal. Continue medication.", 15),
    ]

    status_history_map = {
        APPT_ACCEPTED: ["Request submitted", "Accepted by provider"],
        APPT_DECLINED: ["Request submitted", "Declined by provider"],
        APPT_COMPLETED: ["Request submitted", "Accepted by provider", "Patient attended"],
        APPT_CANCELLED: ["Request submitted", "Cancelled by patient"],
    }

    appointments = []
    for idx, (pname, doc, svc, fac, days_from, t, reason, status, response, age_days) in enumerate(appt_records):
        d = today + timedelta(days=days_from)
        u, pat = patients[pname]
        provider = providers[doc]
        appt_date = d
        code = f"AP-DEMO-{idx + 11}"
        a = Appointment(
            booking_code=code, patient_id=pat.id, provider_id=provider.id,
            facility_id=facilities[fac].id, service_id=services[svc].id,
            appointment_date=appt_date, appointment_time=t,
            reason_for_visit=reason, status=status, provider_response=response,
        )
        a.created_at = datetime.utcnow() - timedelta(days=age_days)
        a.updated_at = datetime.utcnow() - timedelta(days=age_days)
        db.session.add(a)
        db.session.flush()
        for note in status_history_map.get(status, ["Request submitted"]):
            db.session.add(AppointmentStatusHistory(
                appointment_id=a.id, status=APPT_PENDING if note == "Request submitted" else status,
                changed_by_role="patient" if note == "Request submitted" or note == "Cancelled by patient" else "provider",
                note=note,
                created_at=a.created_at,
            ))
        appointments.append(a)
    db.session.flush()

    # ---------------- Notifications ----------------
    sample_notifications = [
        ("Alice Wanjiru", "Appointment accepted",
         "Your appointment AP-DEMO-11 (Cardiology) with Dr. John Michael has been ACCEPTED."),
        ("Alice Wanjiru", "Upcoming appointment reminder",
         "Reminder: Cardiology appointment with Dr. John Michael in 3 days."),
        ("Brian Kipchoge", "Appointment submitted",
         "Your appointment request AP-DEMO-12 has been submitted and is awaiting review."),
        ("Brian Kipchoge", "System announcement",
         "Welcome to AfyaNow! New laboratory services are now available for booking."),
        ("Catherine Muthoni", "Appointment accepted",
         "Your Dermatology appointment with Dr. Amina Hassan has been ACCEPTED."),
        ("Daniel Okello", "Appointment submitted",
         "Your appointment request AP-DEMO-14 has been submitted and is awaiting review."),
        ("Fatuma Zahra", "Appointment submitted",
         "Your appointment request AP-DEMO-15 has been submitted and is awaiting review."),
        ("Dr. John Michael", "New appointment request",
         "Patient Alice Wanjiru requested Cardiology on " + (today + timedelta(days=3)).strftime("%d %b %Y") + "."),
        ("Dr. Peter Njoroge", "New appointment request",
         "Patient Brian Kipchoge requested Orthopaedics on " + (today + timedelta(days=1)).strftime("%d %b %Y") + "."),
        ("Dr. Amina Hassan", "New appointment request",
         "Patient Catherine Muthoni requested Dermatology."),
        ("Dr. David Otieno", "New appointment request",
         "Patient Daniel Okello requested Neurology."),
        ("Dr. Grace Wanjiku", "New appointment request",
         "Patient Fatuma Zahra requested Ophthalmology."),
        ("Alice Wanjiru", "System announcement",
         "AfyaNow will be carrying out scheduled maintenance this weekend."),
    ]

    lookup = {}
    for name, pat in patients.items():
        lookup[name] = pat[0].id
    for name, p in providers.items():
        lookup[name] = p.user_id

    for recipient_name, title, message in sample_notifications:
        rid = lookup[recipient_name]
        db.session.add(Notification(user_id=rid, title=title, message=message,
                                    ntype="announcement" if "announcement" in title.lower() else "appointment"))

    # ---------------- Announcements ----------------
    db.session.add(Announcement(
        title="Welcome to AfyaNow",
        message="AfyaNow connects patients with specialized healthcare providers. "
                "Browse services, view specialists and book appointments online.",
        audience="all", created_by=admin_user.id))
    db.session.add(Announcement(
        title="New Laboratory Services",
        message="Laboratory Services are now available for booking across all partner facilities.",
        audience="all", created_by=admin_user.id))

    # ---------------- Audit logs ----------------
    db.session.add(AuditLog(user_id=admin_user.id, action="System seeded",
                            details="Demo dataset created (LDES lab)."))
    db.session.add(AuditLog(user_id=admin_user.id, action="Admin login", details="admin@example.com"))
    db.session.add(AuditLog(user_id=None, action="Patient registration", details="Demo patients created"))

    db.session.commit()
    print("Seed data committed successfully.")
    print()
    print("=== AFYANOW DEMO CREDENTIALS (development only) ===")
    print("  Administrator : admin@example.com    / Admin@123")
    print("  Doctor        : doctor@example.com   / Doctor@123")
    print("  Patient       : patient@example.com  / Patient@123")
    print()
    print("Run the app with:  python app.py")
    print("Open:            http://127.0.0.1:5000/")


if __name__ == "__main__":
    main()