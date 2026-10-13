"""Shared pytest fixtures for the test suite."""

import pytest

from app import create_app, db as _db


@pytest.fixture(scope="session")
def app():
    """Create the Flask app once for the whole test session."""
    app = create_app("testing")
    yield app


@pytest.fixture(scope="function")
def db(app):
    """Provide a clean database for every test function."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app, db):
    """Flask test client with a clean database."""
    with app.test_client() as c:
        with app.app_context():
            yield c
