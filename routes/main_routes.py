from flask import Blueprint, render_template

from models import Service, HealthcareFacility, HealthcareProvider, Speciality

main_bp = Blueprint("main", __name__)


@main_bp.route("/landing")
def landing():
    services = Service.query.filter_by(is_active=True).count()
    providers = HealthcareProvider.query.count()
    facilities = HealthcareFacility.query.filter_by(is_active=True).count()
    specialties = Speciality.query.count()
    return render_template(
        "landing.html",
        stats={
            "services": services,
            "providers": providers,
            "facilities": facilities,
            "specialties": specialties,
        },
    )


@main_bp.route("/about")
def about():
    return render_template("public/about.html")


@main_bp.route("/contact")
def contact():
    return render_template("public/contact.html")