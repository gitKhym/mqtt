from agent import Agent
import sys
import os
import json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, render_template, request, redirect, url_for, session, flash
import socket
from config import SOCKET_HOST, SOCKET_PORT


app = Flask(__name__)

app.secret_key = "supersecretkey"
rooms = {}

def send_to_master(message):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((SOCKET_HOST, SOCKET_PORT))
        s.sendall(message.encode())
        response = s.recv(1024).decode()
        return response

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

        msg_dict = {
            "op": "REGISTER",
            "Full_Name": full_name,
            "Email": email,
            "Password": password,
            "Unique_ID": unique_id}
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
            rsp = response["reason"]
            flash(rsp)
            return redirect(url_for("register"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # Send login request to Master Pi
        msg_json = {
            "op": "LOGIN",
            "Email": email,
            "Password": password
        }
        msg = json.dumps(msg_json)
        response = json.loads(send_to_master(msg))

        

        # Check Master Pi response
        if response['type']=="success":
            session["user_email"] = email
            flash("Login successful!")

          
            user_role = response["role"]
            user_id = response["user_id"]
            full_name = response["full_name"]
            token = response["user_token"]
            
            session["user_role"] = user_role
            session["user_id"] = user_id
            session["full_name"] = full_name
            session["token"] = token

            # Determine redirect based on role
            if user_role == "security":
                return redirect(url_for("security_home"))
            elif user_role in ["user", "student", "teacher"]:
                return redirect(url_for("home"))
            else:
                flash("Unknown role returned by Master Pi.")
                return redirect(url_for("login"))

        elif response["type"] == "failure":
            reason = response["reason"]
            flash(f"Login failed: {reason}")
            return redirect(url_for("login"))

        else:
            flash("Unexpected response from Master Pi.")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/security_home")
def security_home():
    if "user_email" not in session or session.get("user_role") != "security":
        return redirect(url_for("login"))
    return render_template("security_home.html")

@app.route("/home")
def home():
    if "token" not in session:
        return redirect(url_for("login"))
    return render_template("home.html")

@app.route("/logout")
def logout():
    session.pop("user_email", None)
    session.pop("user_id", None)
    session.pop("user_role", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))

@app.route("/book-a-room", methods=["GET", "POST"])
def booking():
    if "token" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        room_id = request.form["room_id"]
        date = request.form["date"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]

        msg_dict = {
            "op": "BOOK_ROOM",
            "User_ID": session["user_id"],
            "Token": session["token"],
            "Room_ID": room_id,
            "Date": date,
            "Start_Time": start_time,
            "End_Time": end_time
        }
        msg = json.dumps(msg_dict)
        response = json.loads(send_to_master(msg))

        if response["type"] == "success":
            flash("Room booked successfully!")
            return redirect(url_for("my_bookings"))
        else:
            reason = response.get("reason", "Unknown error")
            flash(f"Failed to book room: {reason}")
            return redirect(url_for("booking"))

    rooms = session.get("rooms", {})
    return render_template("book_a_room.html", rooms=rooms)

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