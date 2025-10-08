from flask import Flask, render_template, request, redirect, url_for, session, flash
import socket
import config

app = Flask(__name__)
app.secret_key = "supersecretkey"  # replace with something secure

# ---------- Helper Function for Socket Communication ----------
def send_to_master(message):
    """Send message to Master Pi using sockets and return response."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((config.SOCKET_HOST, config.SOCKET_PORT))
            s.sendall(message.encode())
            response = s.recv(1024).decode()
        return response
    except Exception as e:
        print(f"Socket Error: {e}")
        return "Connection error with Master Pi."

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
        return redirect(url_for("home"))
        msg = f"LOGIN|{email}|{password}"
        response = send_to_master(msg)

        if "success" in response.lower():
            session["user"] = email
            flash("Login successful!")
            return redirect(url_for("home"))
        else:
            flash(response)
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
