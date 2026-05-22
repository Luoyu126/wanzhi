from datetime import date

from wanzhi.services.medication.repository import MedicationRepository


def test_medication_repository_lists_due_items(tmp_path) -> None:
    repo = MedicationRepository(tmp_path / "wanzhi.db")
    repo.add_medication("降压药", "1片", "08:00")

    items = repo.list_due_on(date(2026, 5, 22))

    assert items == [
        {
            "id": 1,
            "name": "降压药",
            "dosage": "1片",
            "time_of_day": "08:00",
            "date": "2026-05-22",
        }
    ]
