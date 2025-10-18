import sys
sys.path.append(".")
from database import Database

from models.user import User
from models.room import Room

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import matplotlib.pyplot as plt
import io, base64
from datetime import datetime

import paho.mqtt.client as mqtt
import json
import config

def publish_mqtt_announcement(message: str):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
        client.loop_start() # Start a non-blocking loop
        payload = {"message": message, "timestamp": datetime.now().isoformat()}
        client.publish(config.TOPIC_ANNOUNCEMENTS, json.dumps(payload))
        print(f"MQTT | Published announcement: {message}")
    except Exception as e:
        print(f"MQTT | Error publishing announcement: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

def publish_mqtt_room_command(room_id: int, op: str, status: str = None):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
        client.loop_start()
        payload = {"op": op, "room_id": room_id}
        if status:
            payload["status"] = status
        print(f"MASTER_WEB | Publishing room command: {payload} to topic: {config.TOPIC_ROOM_COMMAND_PREFIX}{room_id}/command") # Add this
        client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{room_id}/command", json.dumps(payload))
        print(f"MASTER_WEB | Published room command for room {room_id}: {payload}")
    except Exception as e:
        print(f"MQTT | Error publishing room command: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

app = Flask(__name__)
app.secret_key = "supersecretkey"

DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")
db = Database(DB_FILE)

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
        conn = db.conn
        user = conn.execute("SELECT * FROM users WHERE email=? AND password=? AND role='admin'", (email, password)).fetchone()
        if user:
            session["admin"] = email
            flash("Login successful!")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.")
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
    conn = db.conn
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    room_count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    booking_count = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    recent_bookings = conn.execute("SELECT b.*, u.full_name, r.room_name FROM bookings b LEFT JOIN users u ON b.user_id = u.id LEFT JOIN rooms r ON b.room_id = r.id ORDER BY b.start_time DESC LIMIT 5").fetchall()
    room_statuses = conn.execute("SELECT * FROM rooms").fetchall()
    return render_template("admin-dashboard.html", user_count=user_count, room_count=room_count, booking_count=booking_count, recent_bookings=recent_bookings, room_statuses=room_statuses)


# ---------- USERS ----------
@app.route("/users")
def manage_users():
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    users = conn.execute("SELECT * FROM users").fetchall()
    return render_template("users.html", users=users)

@app.route("/create_security", methods=["POST"])
def create_security():
    if "admin" not in session:
        return redirect(url_for("login"))
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]
    new_user = User(email=email, password=password, full_name=name, user_id=email, role='security', user_token=email)
    db.create_user(new_user)
    flash("Security staff created.")
    return redirect(url_for("manage_users"))

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    flash("User deleted.")
    return redirect(url_for("manage_users"))

@app.route("/edit_user/<int:user_id>", methods=["GET"])
def edit_user(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return render_template("edit_user.html", user=user)

@app.route("/update_user/<int:user_id>", methods=["POST"])
def update_user(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))
    name = request.form["name"]
    email = request.form["email"]
    role = request.form["role"]
    conn = db.conn
    conn.execute("UPDATE users SET full_name=?, email=?, role=? WHERE id=?", (name, email, role, user_id))
    conn.commit()
    flash("User updated.")
    return redirect(url_for("manage_users"))

# ---------- ROOMS ----------
@app.route("/rooms")
def rooms():
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    
    # Fetch all rooms with their latest sensor data
    base_rooms = conn.execute("""
        SELECT r.id, r.room_name, r.status, r.location, r.capacity,
               sd.temperature, sd.humidity, sd.pressure, sd.timestamp
        FROM rooms r
        LEFT JOIN (
            SELECT room_id, temperature, humidity, pressure, timestamp
            FROM sensor_data
            WHERE (room_id, timestamp) IN (
                SELECT room_id, MAX(timestamp)
                FROM sensor_data
                GROUP BY room_id
            )
        ) sd ON r.id = sd.room_id
    """).fetchall()

    rooms_list = [dict(row) for row in base_rooms]

    now = datetime.now()

    for room in rooms_list:
        # Prioritize manually set status
        if room['status'] in ['Maintenance', 'Fault', 'Occupied']:
            pass
        else:
            # Check for active bookings
            future_booking = conn.execute("""
                SELECT 1 FROM bookings 
                WHERE room_id = ? AND end_time > ? AND status IN ('Booked', 'checked in')
                LIMIT 1
            """, (room['id'], now)).fetchone()

            if future_booking:
                room['status'] = 'Booked'
            else:
                room['status'] = 'Available'

        # Get bookings for the room
        bookings = conn.execute("""
            SELECT u.full_name, b.start_time, b.end_time
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.room_id = ? AND b.end_time > ? AND b.status IN ('Booked', 'checked in')
            ORDER BY b.start_time ASC
        """, (room['id'], now)).fetchall()
        room['bookings'] = bookings

    return render_template("rooms.html", rooms=rooms_list)

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
    
    # Publish MQTT message to room
    publish_mqtt_room_command(int(room_id), "UPDATE_STATUS", new_status) # Add this line
    
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
        publish_mqtt_announcement(msg)
    ann = conn.execute("SELECT * FROM announcements ORDER BY timestamp DESC").fetchall()
    return render_template("announcements.html", announcements=ann)

# ---------- LOGS ----------
@app.route("/logs")
def logs():
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    logs = conn.execute("SELECT l.*, u.full_name FROM logs l LEFT JOIN users u ON l.user_id = u.id ORDER BY l.timestamp DESC").fetchall()
    return render_template("logs.html", logs=logs)

# ---------- BOOKING LOGS ----------
@app.route("/booking_logs")
def booking_logs():
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    bookings = conn.execute("SELECT b.*, u.full_name, r.room_name FROM bookings b LEFT JOIN users u ON b.user_id = u.id LEFT JOIN rooms r ON b.room_id = r.id ORDER BY b.start_time DESC").fetchall()
    return render_template("booking_logs.html", bookings=bookings)


# ---------- REPORTS ----------
@app.route("/reports")
def reports():
    if "admin" not in session:
        return redirect(url_for("login"))
    conn = db.conn
    data = conn.execute("SELECT room_id, COUNT(*) AS count FROM bookings GROUP BY room_id").fetchall()
    
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
    conn = db.conn
    rows = conn.execute(
        "SELECT timestamp, temperature, humidity, pressure FROM sensor_data WHERE room_id=? ORDER BY timestamp DESC LIMIT 20",
        (room_id,)
    ).fetchall()
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
