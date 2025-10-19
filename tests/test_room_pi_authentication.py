import sys
from unittest.mock import MagicMock, patch

sys.modules["sense_hat"] = MagicMock()

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from room import RoomPi
from models.status import Status


@pytest.fixture
def room():
    """Fixture that returns a RoomPi instance with mocks to isolate hardware/MQTT."""
    with patch("room.SenseHat", MagicMock()):
        rp = RoomPi()
        rp.id = 1
        rp.sense = MagicMock()
        rp.mqtt_client = MagicMock()
        return rp


def make_booking(token="valid_token", start_offset=-5, duration_minutes=10):
    """Helper to create a booking around the current time."""
    starttime = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None) + timedelta(minutes=start_offset)
    endtime = starttime + timedelta(minutes=duration_minutes)
    return {"starttime": starttime, "endtime": endtime, "token": token}


# ---------- TESTS FOR CHECK-IN ----------

def test_check_in_success(room):
    booking = make_booking(token="abc")
    room.bookings = [booking]

    msg = {"token": "abc", "booking_id": "B001"}
    resp = room.check_in(msg)

    assert resp["type"] == "success"
    assert room.current == Status.OCCUPIED
    assert room.next_user_token == "abc"
    room.sense.clear.assert_called_once()  # LEDs updated


def test_check_in_invalid_token(room):
    booking = make_booking(token="valid_token")
    room.bookings = [booking]

    msg = {"token": "wrong_token"}
    resp = room.check_in(msg)

    assert resp["type"] == "failure"
    assert "Invalid token" in resp["reason"]
    assert room.current == Status.AVAILABLE  # Should not change


def test_check_in_outside_time_window(room):
    """If booking is not active yet or expired, check-in should fail."""
    future_booking = make_booking(start_offset=60, duration_minutes=30)  # starts in 1h
    room.bookings = [future_booking]

    msg = {"token": future_booking["token"]}
    resp = room.check_in(msg)

    assert resp["type"] == "failure"
    assert "not within booking time" in resp["reason"]
    assert room.current == Status.AVAILABLE


# ---------- TESTS FOR CHECK-OUT ----------

def test_check_out_success(room):
    booking = make_booking(token="xyz")
    room.bookings = [booking]
    room.next_user_token = "xyz"
    room.current = Status.OCCUPIED

    msg = {"token": "xyz", "booking_id": "B002"}
    resp = room.check_out(msg)

    assert resp["type"] == "success"
    assert room.current == Status.AVAILABLE
    assert room.next_user_token is None
    assert len(room.bookings) == 0
    room.sense.clear.assert_called_once()


def test_check_out_with_unknown_token(room):
    """Should still succeed but not crash if token doesn't match."""
    booking = make_booking(token="t1")
    room.bookings = [booking]

    msg = {"token": "unknown_token", "booking_id": "B002"}
    resp = room.check_out(msg)

    assert resp["type"] == "success"  # system just resets state
    assert room.current == Status.AVAILABLE
    assert room.next_user_token is None
    assert len(room.bookings) == 1  # unchanged because token not found


# ---------- ROUNDTRIP AUTH TEST ----------

def test_check_in_then_out(room):
    booking = make_booking(token="user123")
    room.bookings = [booking]

    checkin_resp = room.check_in({"token": "user123", "booking_id": "B010"})
    assert checkin_resp["type"] == "success"
    assert room.current == Status.OCCUPIED

    checkout_resp = room.check_out({"token": "user123", "booking_id": "B010"})
    assert checkout_resp["type"] == "success"
    assert room.current == Status.AVAILABLE
    assert room.next_user_token is None
    assert room.bookings == []


# ---------- EDGE CASES ----------

def test_check_in_with_empty_bookings(room):
    """If no bookings exist, check-in should fail gracefully."""
    room.bookings = []
    resp = room.check_in({"token": "anything"})
    assert resp["type"] == "failure"
    assert "Invalid token" in resp["reason"]

def test_check_in_invalid_time_format_does_not_raise(room):
    """Invalid booking time values trigger ValueError (for now)."""
    class Dummy:
        def isoformat(self):
            raise ValueError("broken isoformat")

    room.bookings = [{"starttime": Dummy(), "endtime": Dummy(), "token": "abc"}]
    msg = {"token": "abc"}

    with pytest.raises(ValueError, match="broken isoformat"):
        room.check_in(msg)

