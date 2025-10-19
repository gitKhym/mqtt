from typing import List
from agent import Agent
import re
import sys
import os
import json

from models.room import Room
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, jsonify
import socket
from config import SOCKET_HOST, SOCKET_PORT



app = Flask(__name__)

app.secret_key = "supersecretkey"
rooms = {}


def send_to_master(message):
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
            flash("Room booked successfully.")
            return redirect(url_for("home"))
        else:
            flash(f"Failed to book the room: {response['reason']}")
            return redirect(url_for("booking"))
     
    msg = {"op": "UPDATE_ROOMS"}  
    response = json.loads(send_to_master(json.dumps(msg)))
     
    session['rooms'] = response['rooms']
    rooms = session.get("rooms", {})
    return render_template("book_room.html", rooms=rooms)  

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
        msg = {
            "op": "CANCEL_BOOKING",
            "booking_id": booking_id,
            "token": session["token"]
        }
        msg = json.dumps(msg)
        response = json.loads(send_to_master(msg))
        if response["type"] == "success":
            flash("Booking cancelled successfully.")
        else:
            flash("Failed to cancel booking.")

    elif action == "check_in":
        msg = {
            "op": "CHECK_IN",
            "booking_id": booking_id,
            "token": session["token"]
        }
        
        response = json.loads(send_to_master(json.dumps(msg)))
        if response["type"] == "success":
            flash("Checked in successfully.")
        else:
            flash("Failed to check in.")
    elif action == "check_out":
        msg = {
            "op": "CHECK_OUT",
            "booking_id": booking_id,
            "token": session["token"]
        }
        response = json.loads(send_to_master(json.dumps(msg)))
        if response["type"] == "success":
            flash("Checked out successfully.")
        else:
            flash("Failed to check out.")

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
            return jsonify(response.get("rooms", {}))
        else:
            return jsonify({"error": "Failed to retrieve rooms", "details": response.get("reason")}), 500
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
            return jsonify(response.get("bookings", []))
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
