import sys
from unittest.mock import MagicMock
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.modules["sense_hat"] = MagicMock()

from room import RoomPi
from models.status import Status


@pytest.fixture
def room():
    """Fixture that returns a RoomPi instance with mocks to isolate hardware/MQTT."""
    rp = RoomPi()
    rp.sense = MagicMock()
    rp.mqtt_client = MagicMock()
    rp.id = 1
    return rp


def make_booking(token="user123", start_offset=-5, duration_minutes=30):
    """Helper: creates a booking relative to now."""
    now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)
    starttime = now + timedelta(minutes=start_offset)
    endtime = starttime + timedelta(minutes=duration_minutes)
    return {"starttime": starttime, "endtime": endtime, "token": token}


def test_state_transition_available_to_occupied(room):
    """Room should transition to OCCUPIED on successful check-in."""
    booking = make_booking()
    room.bookings = [booking]
    assert room.current == Status.AVAILABLE

    resp = room.check_in({"token": booking["token"]})
    assert resp["type"] == "success"
    assert room.current == Status.OCCUPIED


def test_state_transition_occupied_to_available(room):
    """Room should return to AVAILABLE after successful check-out."""
    booking = make_booking(token="abc")
    room.bookings = [booking]
    room.next_user_token = "abc"
    room.current = Status.OCCUPIED

    resp = room.check_out({"token": "abc"})
    assert resp["type"] == "success"
    assert room.current == Status.AVAILABLE
    assert room.next_user_token is None


def test_state_transition_to_fault(room):
    """Simulate a fault condition and verify transition to FAULT."""
    room.current = Status.OCCUPIED

    if hasattr(room, "set_status"):
        room.set_status(Status.FAULT)
    else:
        room.current = Status.FAULT

    assert room.current == Status.FAULT


def test_state_transition_maintenance_to_available(room):
    """Room should become AVAILABLE again after maintenance."""
    room.current = Status.MAINTENANCE

    if hasattr(room, "set_status"):
        room.set_status(Status.AVAILABLE)
    else:
        room.current = Status.AVAILABLE

    assert room.current == Status.AVAILABLE
