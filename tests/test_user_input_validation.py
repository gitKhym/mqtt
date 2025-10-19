import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch
from agent_web import app


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    client = app.test_client()

    # Mock network communication
    def mock_send_to_master(message):
        msg = json.loads(message)
        if msg["op"] == "REGISTER":
            if msg["Email"] == "exists@example.com":
                return json.dumps({"type": "failure", "reason": "Email already exists."})
            return json.dumps({
                "type": "success",
                "rooms": {},
                "user_id": "123",
                "user_token": "fake_token"
            })
        elif msg["op"] == "LOGIN":
            if msg["Email"] == "user@example.com" and msg["Password"] == "ValidPass1!":
                return json.dumps({
                    "type": "success",
                    "role": "user",
                    "user_id": "123",
                    "full_name": "John Doe",
                    "user_token": "abc",
                    "rooms": {}
                })
            return json.dumps({"type": "failure", "reason": "Invalid credentials."})
        return json.dumps({"type": "failure", "reason": "Unknown operation."})

    monkeypatch.setattr("agent_web.send_to_master", mock_send_to_master)
    return client


def test_register_missing_fields(client):
    data = {"full_name": "", "email": "", "password": "", "unique_id": ""}
    resp = client.post("/register", data=data, follow_redirects=True)
    assert b"All fields are required." in resp.data


def test_register_invalid_name(client):
    data = {
        "full_name": "123Invalid",
        "email": "test@example.com",
        "password": "ValidPass1!",
        "unique_id": "s1234567"
    }
    resp = client.post("/register", data=data, follow_redirects=True)
    assert b"Full name must contain only letters" in resp.data


def test_register_invalid_email(client):
    data = {
        "full_name": "John Doe",
        "email": "not-an-email",
        "password": "ValidPass1!",
        "unique_id": "s1234567"
    }
    resp = client.post("/register", data=data, follow_redirects=True)
    assert b"Invalid email format" in resp.data


def test_register_weak_password(client):
    data = {
        "full_name": "John Doe",
        "email": "test@example.com",
        "password": "weakpass",
        "unique_id": "s1234567"
    }
    resp = client.post("/register", data=data, follow_redirects=True)
    assert b"Password must be at least 8 characters long" in resp.data


def test_register_invalid_unique_id(client):
    data = {
        "full_name": "John Doe",
        "email": "test@example.com",
        "password": "ValidPass1!",
        "unique_id": "x1234567"
    }
    resp = client.post("/register", data=data, follow_redirects=True)
    assert b"Wrong RMIT id" in resp.data


def test_register_success(client):
    data = {
        "full_name": "John Doe",
        "email": "new@example.com",
        "password": "ValidPass1!",
        "unique_id": "s1234567"
    }
    resp = client.post("/register", data=data, follow_redirects=True)
    assert b"registration succesful" in resp.data


def test_register_existing_email(client):
    data = {
        "full_name": "John Doe",
        "email": "exists@example.com",
        "password": "ValidPass1!",
        "unique_id": "s1234567"
    }
    resp = client.post("/register", data=data, follow_redirects=True)
    assert b"Registration failed" in resp.data


# -------- LOGIN VALIDATION TESTS --------

def test_login_success(client):
    data = {"email": "user@example.com", "password": "ValidPass1!"}
    resp = client.post("/login", data=data, follow_redirects=True)
    assert b"Login successful" in resp.data


def test_login_invalid_credentials(client):
    data = {"email": "wrong@example.com", "password": "WrongPass!"}
    resp = client.post("/login", data=data, follow_redirects=True)
    assert b"Login failed" in resp.data


def test_login_missing_fields(client):
    # Missing email and password triggers a generic failure but not crash
    data = {"email": "", "password": ""}
    resp = client.post("/login", data=data, follow_redirects=True)
    # Just check it renders the page without throwing unexpected errors
    assert b"Login failed" not in resp.data
    assert b"Unexpected response from Master Pi" not in resp.data

def login_session(client):
    """Helper to populate session with token and rooms for booking tests"""
    with client.session_transaction() as sess:
        sess["token"] = "fake_token"
        sess["rooms"] = {
            "1": {"room_name": "Room 1", "ip": "127.0.0.1", "port": 1234, "status": "Available"}
        }

def test_booking_get_page(client):
    login_session(client)
    # Mock send_to_master for updating rooms
    with patch("agent_web.send_to_master") as mock_master:
        mock_master.return_value = json.dumps({
            "type": "success",
            "rooms": {
                "1": {"room_name": "Room 1", "ip": "127.0.0.1", "port": 1234, "status": "Available"}
            }
        })
        resp = client.get("/booking")
        assert resp.status_code == 200
        assert b"Room 1" in resp.data

def test_booking_post_success(client):
    login_session(client)
    starttime = (datetime.now() + timedelta(hours=1)).isoformat(timespec='minutes')

    data = {
        "room_id": "1",
        "starttime": starttime,
        "duration": "2"
    }

    mock_master_response = json.dumps({
        "type": "success",
        "booking_access_token": "mock_access_token"
    })

    with patch("agent_web.send_to_master", return_value=mock_master_response):
        resp = client.post("/booking", data=data, follow_redirects=True)

    assert b"Room booked successfully" in resp.data
    assert b"mock_access_token" in resp.data

def test_booking_post_too_long(client):
    login_session(client)
    starttime = (datetime.now() + timedelta(hours=1)).isoformat(timespec='minutes')
    data = {"room_id": "1", "starttime": starttime, "duration": "3"}  # >2 hours

    with patch("agent_web.send_to_master") as mock_master:
        mock_master.return_value = json.dumps({
            "type": "success",
            "rooms": {
                "1": {"room_name": "Room 1", "ip": "127.0.0.1", "port": 1234, "status": "Available"}
            }
        })
        resp = client.post("/booking", data=data, follow_redirects=True)
        assert b"You can only book a room for 2h max" in resp.data

def test_booking_post_failure(client):
    login_session(client)
    starttime = (datetime.now() + timedelta(hours=1)).isoformat(timespec='minutes')

    data = {
        "room_id": "1",
        "starttime": starttime,
        "duration": "1"
    }

    mock_responses = [
        json.dumps({"type": "error", "reason": "Room not available"}), 
        json.dumps({"rooms": {}})  
    ]

    def mock_send_to_master(msg):
        return mock_responses.pop(0)

    with patch("agent_web.send_to_master", side_effect=mock_send_to_master):
        resp = client.post("/booking", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Failed to book the room" in resp.data
    assert b"Room not available" in resp.data

