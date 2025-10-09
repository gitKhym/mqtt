from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import matplotlib.pyplot as plt
import io, base64

app = Flask(__name__)
app.secret_key = "supersecretkey"

DB_PATH = os.path.join(os.path.dirname(__file__), "classroom.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=? AND role='admin'", (email,)).fetchone()
        if user and user["password_hash"] == password:
            session["admin"] = email
            flash("Login successful!")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.")
    return render_template("admin_login.html")

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
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    return render_template("users.html", users=users)

@app.route("/create_security", methods=["POST"])
def create_security():
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]
    conn = get_db()
    conn.execute(
        "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'security')",
        (name, email, password),
    )
    conn.commit()
    flash("Security staff created.")
    return redirect(url_for("manage_users"))

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    conn.commit()
    flash("User deleted.")
    return redirect(url_for("manage_users"))

# ---------- ROOMS ----------
@app.route("/rooms")
def rooms():
    conn = get_db()
    rooms = conn.execute("SELECT * FROM rooms").fetchall()
    return render_template("rooms.html", rooms=rooms)

@app.route("/update_room_status", methods=["POST"])
def update_room_status():
    room_id = request.form["room_id"]
    new_status = request.form["status"]
    conn = get_db()
    conn.execute("UPDATE rooms SET status=? WHERE room_id=?", (new_status, room_id))
    conn.commit()
    flash("Room status updated.")
    return redirect(url_for("rooms"))

# ---------- ANNOUNCEMENTS ----------
@app.route("/announcements", methods=["GET", "POST"])
def announcements():
    conn = get_db()
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
    conn = get_db()
    logs = conn.execute("SELECT * FROM logs ORDER BY timestamp DESC").fetchall()
    return render_template("logs.html", logs=logs)

# ---------- REPORTS ----------
@app.route("/reports")
def reports():
    conn = get_db()
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
    app.run(host="0.0.0.0", port=8000, debug=True)
 