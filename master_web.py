import sys
sys.path.append(".")
from database import Database

from models.user import User
from models.room import Room

from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import matplotlib.pyplot as plt
import io, base64

app = Flask(__name__)
app.secret_key = "supersecretkey"

DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")
db = Database(DB_FILE)

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
    return render_template("admin_dashboard.html")

# ---------- USERS ----------
@app.route("/users")
def manage_users():
    conn = db.conn
    users = conn.execute("SELECT * FROM users").fetchall()
    return render_template("users.html", users=users)

@app.route("/create_security", methods=["POST"])
def create_security():
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]
    # Assuming a dummy user_id for security staff, or generate one if needed
    new_user = User(email=email, password=password, full_name=name, user_id=email, role='security')
    db.create_user(new_user)
    flash("Security staff created.")
    return redirect(url_for("manage_users"))

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    conn = db.conn
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    flash("User deleted.")
    return redirect(url_for("manage_users"))

# ---------- ROOMS ----------
@app.route("/rooms")
def rooms():
    conn = db.conn
    rooms = conn.execute("SELECT * FROM rooms").fetchall()
    return render_template("rooms.html", rooms=rooms)

@app.route("/update_room_status", methods=["POST"])
def update_room_status():
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
    conn = db.conn
    if request.method == "POST":
        msg = request.form["message"]
        conn.execute("INSERT INTO announcements (admin_id, target_audience, message) VALUES (1, 'all', ?)", (msg,))
        conn.commit()
        flash("Announcement published!")
        # TODO: publish to MQTT "classroom/all"
    ann = conn.execute("SELECT * FROM announcements ORDER BY timestamp DESC").fetchall()
    return render_template("announcements.html", announcements=ann)

# ---------- LOGS ----------
@app.route("/logs")
def logs():
    conn = db.conn
    logs = conn.execute("SELECT * FROM logs ORDER BY timestamp DESC").fetchall()
    return render_template("logs.html", logs=logs)

# ---------- REPORTS ----------
@app.route("/reports")
def reports():
    conn = db.conn
    data = conn.execute("SELECT room_id, COUNT(*) AS count FROM bookings GROUP BY room_id").fetchall()
    rooms = [f"Room {r['room_id']}" for r in data]
    counts = [r["count"] for r in data]
    plt.bar(rooms, counts)
    plt.title("Room Usage Frequency")
    plt.xlabel("Room")
    plt.ylabel("Bookings")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plot_data = base64.b64encode(buf.getvalue()).decode()
    return render_template("reports.html", plot_data=plot_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)
 
