import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, render_template, request, redirect, url_for, session, flash
import socket
from config import SOCKET_HOST, SOCKET_PORT


app = Flask(__name__)

app.secret_key = "supersecretkey"

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

        msg = f"REGISTER|{email}|{password}|{full_name}|{unique_id}"
        response = send_to_master(msg)

        flash(response)
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # Send login request to Master Pi
        msg = f"LOGIN|{email}|{password}"
        response = send_to_master(msg)

        # Normalize case and spacing
        response = response.strip().lower()

        # Check Master Pi response
        if response.startswith("login_success"):
            session["user_email"] = email
            flash("Login successful!")

            # Parse role, user_id, and full_name from Master Pi message
            response_parts = response.split("|")
            user_role = "user" # Default role
            user_id = None
            full_name = None

            for part in response_parts:
                if part.startswith("role="):
                    user_role = part.split("=")[1]
                elif part.startswith("user_id="):
                    user_id = part.split("=")[1]
                elif part.startswith("full_name="):
                    full_name = part.split("=")[1]
            
            session["user_role"] = user_role
            session["user_id"] = user_id
            session["full_name"] = full_name

            # Determine redirect based on role
            if user_role == "security":
                return redirect(url_for("security_home"))
            elif user_role in ["user", "student", "teacher"]:
                return redirect(url_for("home"))
            else:
                flash("Unknown role returned by Master Pi.")
                return redirect(url_for("login"))

        elif response.startswith("login_failed"):
            reason = response.split("=", 1)[1] if "=" in response else "Invalid credentials"
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
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("home.html")

@app.route("/logout")
def logout():
    session.pop("user_email", None)
    session.pop("user_id", None)
    session.pop("user_role", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7001, debug=True)
