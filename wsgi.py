from app import create_app

app = create_app()


def _seed_if_empty():
    from models import Speciality

    with app.app_context():
        if Speciality.query.first() is None:
            from seed import main as seed_main

            seed_main()


_seed_if_empty()