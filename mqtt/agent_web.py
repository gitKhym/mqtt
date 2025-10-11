from flask import Flask, render_template, request, redirect, url_for, session, flash
import socket


app = Flask(__name__)
app.secret_key = "supersecretkey"  # replace with something secure


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
            session["user"] = email
            flash("Login successful!")

            # Determine role based on Master Pi message
            if "role=security" in response:
                return redirect(url_for("security_home"))
            elif "role=user" in response or "role=student" in response or "role=teacher" in response:
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

@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("home.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
