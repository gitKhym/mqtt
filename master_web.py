import socket
import sys
import re
sys.path.append(".")
from database import Database

from models.user import User
from models.room import Room
from config import SOCKET_HOST, SOCKET_PORT

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import json
import matplotlib.pyplot as plt
import io, base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")
db = Database(DB_FILE)

def send_to_master(message):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((SOCKET_HOST, SOCKET_PORT))
        s.sendall(message.encode())
        response = s.recv(4096).decode()
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

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if not value:
        return ""
    try:
        # It might be a timestamp
        return datetime.fromtimestamp(int(value)).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        # It might be a datetime string
        try:
            # Handle formats with and without microseconds
            if '.' in value:
                dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            else:
                dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            # If all else fails, return the original value
            return value

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if not email or not password:
            flash("Email and password are required")
            return redirect(url_for("/"))
        msg_json = {"op": "ADMIN_LOGIN", "Email": email, "Password": password}
        msg = json.dumps(msg_json)
        response = json.loads(send_to_master(msg))
        if response['type'] == 'success':
            session['admin'] = email
            flash('Log in succesful')
            return redirect(url_for("dashboard"))
        else:
            flash(request['reason'])
    return render_template("admin-login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    flash("Logged out.")
    return redirect(url_for("login"))

# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if "admin" not in session:
        return redirect(url_for("login"))
    msg_jon = {'op': 'ADMIN_DASHBOARD'} 
    msg = json.dumps(msg_jon)
    response = json.loads(send_to_master(msg))
    print(response)
    return render_template("admin-dashboard.html", user_count = response['user_count'],
                            room_count=response['room_count'],
                            booking_count=response['booking_count'], 
                            recent_bookings=response['recent_bookings'], 
                            room_statuses=response['room_statuses'])


# ---------- USERS ----------
@app.route("/users")
def manage_users():
    if "admin" not in session:
        return redirect(url_for("login"))
    msg_jon = {'op': 'GET USERS LIST'} 
    msg = json.dumps(msg_jon)
    response = json.loads(send_to_master(msg))
    return render_template("users.html", users=response['users'])

@app.route("/create_security", methods=["POST"])
def create_security():
    if "admin" not in session:
        return redirect(url_for("login"))
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]
    if not all([name, email, password]):
            flash("All fields are required.")
            return redirect(url_for("manage_users"))

    if not re.match(r"^[A-Za-zÀ-ÿ' -]{2,50}$", name):
        flash("Full name must contain only letters and be 2-50 characters long.")
        return redirect(url_for("manage_users"))

    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email):
        flash("Invalid email format.")
        return redirect(url_for("manage_users"))

    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$", password):
        flash("Password must be at least 8 characters long and include upper, lower, number, and special character.")
        return redirect(url_for("manage_users"))
    # Assuming a dummy user_id for security staff, or generate one if needed
 
    msg_jon = {'op': 'CREATE SECURITY', 'name': name, 'email':email, 'password': password} 
    msg = json.dumps(msg_jon)
    response = json.loads(send_to_master(msg))
    flash("Security staff created.")
    return redirect(url_for("manage_users"))

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))
    msg_jon = {'op': 'DELETE USER', 'user_id':user_id} 
    msg = json.dumps(msg_jon)
    response = json.loads(send_to_master(msg))
    flash("User deleted.")
    return redirect(url_for("manage_users"))

@app.route("/edit_user/<int:user_id>", methods=["GET"])
def edit_user(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))
    msg_jon = {'op': 'GET USER', 'user_id':user_id} 
    msg = json.dumps(msg_jon)
    response = json.loads(send_to_master(msg))
    print(response)
    return render_template("edit_user.html", user=response['user'])

@app.route("/update_user/<int:user_id>", methods=["POST"])
def update_user(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))
    name = request.form["name"]
    email = request.form["email"]
    role = request.form["role"]
    if not all([name, email, role]):
            flash("All fields are required.")
            return redirect(url_for("manage_users"))

    if not re.match(r"^[A-Za-zÀ-ÿ' -]{2,50}$", name):
        flash("Full name must contain only letters and be 2-50 characters long.")
        return redirect(url_for("manage_users"))

    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email):
        flash("Invalid email format.")
        return redirect(url_for("manage_users"))

    msg_jon = {'op': 'UPDATE USER', 'user_id':user_id, 'name' : name, 'email': email, 'role': role} 
    msg = json.dumps(msg_jon)
    response = json.loads(send_to_master(msg))
    flash("User updated.")
    return redirect(url_for("manage_users"))

# ---------- ROOMS ----------
@app.route("/rooms")
def rooms():
    if "admin" not in session:
        return redirect(url_for("login"))

    msg = {'op': 'ADMIN GET ROOMS'}
    msg = json.dumps(msg)
    response = json.loads(send_to_master(msg))
    print(response)
    
    return render_template("rooms.html", rooms=response['rooms'])

@app.route("/update_room_status", methods=["POST"])
def update_room_status():
    if "admin" not in session:
        return redirect(url_for("login"))
    room_id = request.form["room_id"]
    new_status = request.form["status"]
    conn = db.conn
    conn.execute("UPDATE rooms SET status=? WHERE id=?", (new_status, room_id))
    conn.commit()
    flash("Room status updated.")
    return redirect(url_for("rooms"))

# ---------- ANNOUNCEMENTS ----------
@app.route("/announcements", methods=["GET", "POST"])
def announcements():
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    if request.method == "POST":
        msg = request.form["message"]
        #TODO: get admin id from session
        conn.execute("INSERT INTO announcements (admin_id, target_audience, message) VALUES (1, 'all', ?)", (msg,))
        conn.commit()
        flash("Announcement published!")
        # TODO: publish to MQTT "classroom/all"
    ann = conn.execute("SELECT * FROM announcements ORDER BY timestamp DESC").fetchall()
    return render_template("announcements.html", announcements=ann)

# ---------- LOGS ----------
@app.route("/logs")
def logs():
    if "admin" not in session:
        return redirect(url_for("login"))

    msg = {'op': 'GET LOGS'}
    msg = json.dumps(msg)
    response = json.loads(send_to_master(msg))
    print(response['logs'])
    return render_template("logs.html", logs=response['logs'])

# ---------- BOOKING LOGS ----------
@app.route("/booking_logs")
def booking_logs():
    if "admin" not in session:
        return redirect(url_for("login"))
    msg = {'op': 'GET BOOKING LOGS'}
    msg = json.dumps(msg)
    response = json.loads(send_to_master(msg))
    return render_template("booking_logs.html", bookings=response['bookings'])


# ---------- REPORTS ----------
@app.route("/reports")
def reports():
    if "admin" not in session:
        return redirect(url_for("login"))
    msg = {'op': 'GET BOOKING COUNT'}
    msg = json.dumps(msg)
    response = json.loads(send_to_master(msg))
    print(response)
    data = response['data']
    if not data:
        return render_template("reports.html", plot_data=None)

    rooms = [f"Room {r['room_id']}" for r in data]
    counts = [r["count"] for r in data]
    
    plt.figure(figsize=(10, 5))
    plt.bar(rooms, counts)
    plt.title("Room Usage Frequency")
    plt.xlabel("Room")
    plt.ylabel("Number of Bookings")
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plot_data = base64.b64encode(buf.getvalue()).decode()
    
    return render_template("reports.html", plot_data=plot_data)

# ---------- SENSOR HISTORY ----------
@app.route("/sensor_history/<int:room_id>")
def sensor_history(room_id):
    if "admin" not in session:
        return redirect(url_for("login"))
    msg = {'op': 'GET SENSOR HISTORY'}
    msg = json.dumps(msg)
    response = json.loads(send_to_master(msg))
    rows = response['rows']
    history = [
        {
            "timestamp": row["timestamp"],
            "temperature": row["temperature"],
            "humidity": row["humidity"],
            "pressure": row["pressure"]
        }
        for row in rows
    ]
    return jsonify(history)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)
