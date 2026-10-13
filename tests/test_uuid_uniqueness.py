"""Test that form UUIDs are unique across 100 creations.

Verifies both the model-level UUID generation and the API endpoint
produce unique identifiers every time.
"""

import uuid

import pytest

from app.models import Form, User


class TestUUIDUniqueness:
    """Form IDs must be unique UUIDs across many creations."""

    def test_100_forms_via_api_have_unique_uuids(self, client, db):
        """Create 100 forms via the API and verify all IDs are unique valid UUIDs."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.commit()

        form_ids = set()
        for i in range(100):
            resp = client.post("/api/forms", json={
                "title": f"Form {i}",
                "owner_id": owner.id,
            })
            assert resp.status_code == 201, f"Form {i} creation failed: {resp.get_json()}"
            form_id = resp.get_json()["id"]

            # Verify it's a valid UUID-4
            parsed = uuid.UUID(form_id, version=4)
            assert str(parsed) == form_id, f"Form {i} ID is not a valid UUID-4"

            form_ids.add(form_id)

        # All 100 IDs must be distinct
        assert len(form_ids) == 100, (
            f"Expected 100 unique UUIDs, got {len(form_ids)} "
            f"({100 - len(form_ids)} duplicates)"
        )

    def test_100_forms_via_model_have_unique_uuids(self, app, db):
        """Create 100 forms directly via the model and verify uniqueness."""
        with app.app_context():
            owner = User(name="Owner", email="owner@test.com", role="owner")
            db.session.add(owner)
            db.session.flush()

            form_ids = set()
            for i in range(100):
                form = Form(title=f"Form {i}", owner_id=owner.id)
                db.session.add(form)
                db.session.flush()
                form_ids.add(form.id)

            db.session.commit()

            assert len(form_ids) == 100, (
                f"Expected 100 unique UUIDs, got {len(form_ids)}"
            )

            # Verify each is a valid UUID-4
            for fid in form_ids:
                parsed = uuid.UUID(fid, version=4)
                assert str(parsed) == fid

    def test_uuid_format_is_standard(self, client, db):
        """UUID format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx (36 chars)."""
        owner = User(name="Owner", email="owner@test.com", role="owner")
        db.session.add(owner)
        db.session.commit()

        resp = client.post("/api/forms", json={
            "title": "Format Test",
            "owner_id": owner.id,
        })
        form_id = resp.get_json()["id"]

        assert len(form_id) == 36
        # 5 groups separated by hyphens: 8-4-4-4-12
        parts = form_id.split("-")
        assert len(parts) == 5
        assert [len(p) for p in parts] == [8, 4, 4, 4, 12]
        # Version nibble is '4'
        assert parts[2][0] == "4"
