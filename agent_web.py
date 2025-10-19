from typing import List
from agent import Agent
import re
import sys
import os
import json

from models.room import Room
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, jsonify
import socket
from config import SOCKET_HOST, SOCKET_PORT



app = Flask(__name__)

app.secret_key = "supersecretkey"
rooms = {}


def send_to_master(message):
    print(f"AGENT_WEB | send_to_master message type: {type(message)}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((SOCKET_HOST, SOCKET_PORT))
        s.sendall(message.encode())
        
        # Receive all data until connection is closed
        total_data = []
        while True:
            data = s.recv(4096) # Receive in chunks
            if not data:
                break
            total_data.append(data.decode())
        response = "".join(total_data)
        return response

def send_to_room(ip, port, message):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((ip, port))
            s.sendall(message.encode())
            response = s.recv(4096).decode()
            return response
        except Exception as e:
            print(f"Error connecting to room at {ip}:{port} - {e}")
            return None

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"]
        email = request.form["email"]
        password = request.form["password"]
        unique_id = request.form["unique_id"]

        if not all([full_name, email, password, unique_id]):
            flash("All fields are required.")
            return redirect(url_for("register"))

        if not re.match(r"^[A-Za-zÀ-ÿ' -]{2,50}$", full_name):
            flash("Full name must contain only letters and be 2-50 characters long.")
            return redirect(url_for("register"))

        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email):
            flash("Invalid email format.")
            return redirect(url_for("register"))

        if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$", password):
            flash("Password must be at least 8 characters long and include upper, lower, number, and special character.")
            return redirect(url_for("register"))


        if not re.match(r"^s[0-9]{7}$", unique_id):
            flash("Wrong RMIT id.")
            return redirect(url_for("register"))

        msg_dict = {
            "op": "REGISTER",
            "Full_Name": full_name,
            "Email": email,
            "Password": password,
            "Unique_ID": unique_id
        }
        msg = json.dumps(msg_dict)
        response = json.loads(send_to_master(msg))
        if response["type"] == "success":
            session["user_email"] = email
            session["rooms"] = response["rooms"]
            session["user_role"] = "User"
            session["user_id"] = response["user_id"]
            session["full_name"] = full_name
            session["token"] = response["user_token"]
            flash("registration succesful")
            return redirect(url_for("home"))
        else:
            flash(f"Registration failed: {response['reason']}")
            return redirect(url_for("register"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if not email or not password:
            flash("Email and password are required")
            return redirect(url_for("login"))

        msg_json = {"op": "LOGIN", "Email": email, "Password": password}
        msg = json.dumps(msg_json)
        response = json.loads(send_to_master(msg))

        if response['type'] == "success":
            session["user_email"] = email
            flash("Login successful")
            user_role = response["role"]
            session["user_role"] = user_role
            session["user_id"] = response["user_id"]
            session["rooms"] = response["rooms"]
            session["full_name"] = response["full_name"]
            session["token"] = response["user_token"]


            return redirect(url_for("home"))

        elif response["type"] == "failure":
            flash(f"Login failed: {response['reason']}")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/home")
def home():
    if "token" not in session:
        return redirect(url_for("login"))
    return render_template("home.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("index"))    



@app.route("/booking", methods=["GET", "POST"])
def booking():
    if "token" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        if session.get("user_role") == "Security" and "room_id" in request.form and "new_status" in request.form:
            room_id = request.form["room_id"]
            new_status = request.form["new_status"]
            msg = {
                "op": "UPDATE_ROOM_STATUS",
                "room_id": room_id,
                "status": new_status,
                "token": session["token"]
            }
            response = json.loads(send_to_master(json.dumps(msg)))

            if response["type"] == "success":
                flash(f"Room {room_id} status updated to {new_status}.")
            else:
                flash(f"Failed to update room status: {response['reason']}")
            return redirect(url_for("booking"))

        # Existing booking logic for regular users
        room_id = request.form["room_id"]
        starttime_str = request.form["starttime"]
        duration_hours = int(request.form["duration"])
        if duration_hours > 2:
            flash("You can only book a room for 2h max")
            return redirect(url_for("booking"))

        # Convert and compute endtime
        starttime = datetime.fromisoformat(starttime_str)

        booking_request = {
            "op": "BOOK_ROOM",
            "room_id": room_id,
            "starttime": starttime.isoformat(),
            "duration": duration_hours * 3600,  
            "token": session["token"]
        }
        msg = json.dumps(booking_request)
        response = json.loads(send_to_master(msg))
        if response["type"] == "success":
            booking_access_token = response.get("booking_access_token")
            flash(f"Room booked successfully. Your booking access token is: {booking_access_token}")
            return redirect(url_for("home"))
        else:
            flash(f"Failed to book the room: {response['reason']}")
            return redirect(url_for("booking"))
     
    msg = {"op": "UPDATE_ROOMS"}  
    response = json.loads(send_to_master(json.dumps(msg)))
     
    session['rooms'] = response['rooms']
    rooms = session.get("rooms", {})
    now = datetime.now(ZoneInfo("Australia/Melbourne"))
    min_datetime = (now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
    return render_template("book_room.html", rooms=rooms, min_datetime=min_datetime)

@app.route("/my-bookings", methods=["GET"])
def my_bookings():
    if "token" not in session:
        return redirect(url_for("login"))
    # Fetch bookings from Master Pi
    msg = {
        "op": "GET_BOOKINGS",
        "token": session["token"]
    }
    response = json.loads(send_to_master(json.dumps(msg)))
    
    if response["type"] == "success":
        bookings = response["bookings"]
        return render_template("my_bookings.html", bookings=bookings)
    else:
        flash("Failed to retrieve bookings.")
        return redirect(url_for("home"))

@app.route("/my-bookings", methods=["POST"])
def handle_bookings():
    if "token" not in session:
        return redirect(url_for("login"))
    booking_id = request.form.get("booking_id")
    room_id = request.form.get("room_id")
    action = request.form.get("action")
    if action == "cancel":
        booking_access_token = request.form.get("booking_access_token")
        msg = {
            "op": "CANCEL_BOOKING",
            "booking_id": booking_id,
            "token": booking_access_token,
        }
        msg = json.dumps(msg)
        response = json.loads(send_to_master(msg))

        print(f"AGENT_WEB | Cancel booking response: {response}")

        if response["type"] == "success":
            flash("Booking cancelled successfully.")

    elif action == "check_in":
        booking_access_token = request.form["booking_access_token"]
        room_id = request.form["room_id"]

        print(f"ROOM ID IS {room_id}")
        validation_msg = {
            "op": "VALIDATE_BOOKING_TOKEN",
            "room_id": room_id,
            "booking_access_token": booking_access_token
        }

        print(f"VALIDATION MESSAGE {validation_msg}")
        validation_response = json.loads(send_to_master(json.dumps(validation_msg)))

        if validation_response["type"] == "success":
            validated_booking_id = validation_response["booking_id"]
            msg = {
                "op": "CHECK_IN",
                "booking_id": validated_booking_id,
                "token": session["token"]
            }
            response = json.loads(send_to_master(json.dumps(msg)))
            if response["type"] == "success":
                flash("Checked in successfully.")
        else:
            flash(f"Check-in failed: {validation_response['reason']}")
    elif action == "check_out":
        msg = {
            "op": "CHECK_OUT",
            "booking_id": booking_id,
            "token": session["token"]
        }
        response = json.loads(send_to_master(json.dumps(msg)))
        if response["type"] == "success":
            flash("Checked out successfully.")

    elif action == "update_booking_status":
        new_booking_status = request.form["new_booking_status"]
        msg = {
            "op": "UPDATE_BOOKING_STATUS",
            "booking_id": booking_id,
            "status": new_booking_status,
            "token": session["token"]
        }
        response = json.loads(send_to_master(json.dumps(msg)))
        if response["type"] == "success":
            flash(f"Booking {booking_id} status updated to {new_booking_status}.")
        else:
            flash(f"Failed to update booking status: {response['reason']}")

    return redirect(url_for("home"))


@app.route("/api/rooms")
def api_rooms():
    if "token" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    msg = {
        "op": "GET_ROOMS"
    }
    response_str = send_to_master(json.dumps(msg))
    try:
        response = json.loads(response_str)
        if response.get("type") == "success":
            rooms_data = response.get("rooms", {})
            user_role = session.get("user_role")
            return jsonify({"rooms": rooms_data, "user_role": user_role})
        else:
            return jsonify({"error": "Failed to retrieve rooms", "details": response.get('reason')}), 500
    except (json.JSONDecodeError, AttributeError):
        return jsonify({"error": "Invalid response from master"}), 500

@app.route("/api/my-bookings")
def api_my_bookings():
    if "token" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    msg = {
        "op": "GET_BOOKINGS",
        "token": session["token"]
    }
    response_str = send_to_master(json.dumps(msg))
    try:
        response = json.loads(response_str)
        if response.get("type") == "success":
            bookings_data = response.get("bookings", [])
            user_role = session.get("user_role")
            return jsonify({"bookings": bookings_data, "user_role": user_role})
        else:
            return jsonify({"error": "Failed to retrieve bookings", "details": response.get("reason")}), 500
    except (json.JSONDecodeError, AttributeError):
        return jsonify({"error": "Invalid response from master"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7001, debug=True)

'''
session rooms:
{
    "1": {
        "room_name": "Room_1",
        "ip": ip,
        "port": port,
        "status": status
    },
    "2": {
        "room_name": "Room_2",
        "ip": ip,
        "port": port, 
        "status": status
    }
'''
