from flask import Flask, render_template, request, redirect, url_for, session, flash
import socket


app = Flask(__name__)
app.secret_key = "supersecretkey"  # replace with something secure

app.secret_key = "supersecretkey"

def send_to_master(message):
    print(f"[Agent Web] Sending to Master: {message}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((SOCKET_HOST, SOCKET_PORT))
        s.sendall(message.encode())
        response = s.recv(1024).decode()
        print(f"[Agent Web] Received from Master: {response}")
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
            session["user"] = email
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
                    user_id = int(part.split("=")[1])
                elif part.startswith("full_name="):
                    full_name = part.split("=")[1]
            
            session["user_role"] = user_role
            session["user_id"] = user_id
            session["full_name"] = full_name

            # Determine redirect based on role
            if user_role == "security":
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

@app.route("/rooms", methods=["GET", "POST"])
def rooms():
    if "user_email" not in session:
        flash("Please log in to view rooms.")
        return redirect(url_for("login"))

    available_rooms = []
    search_performed = False

    if request.method == "POST":
        search_performed = True
        start_time_str = request.form["start_time"]
        end_time_str = request.form["end_time"]

        # Basic validation
        if not start_time_str or not end_time_str:
            flash("Please provide both start and end times.", "error")
        else:
            try:
                msg = f"SEARCH_ROOMS|{start_time_str}|{end_time_str}"
                response = send_to_master(msg)

                if response.startswith("SEARCH_ROOMS_SUCCESS"):
                    room_data = response.split("|")[1:]
                    if room_data and room_data[0] != "No rooms available":
                        for room_str in room_data:
                            parts = room_str.split(",")
                            if len(parts) == 4:
                                available_rooms.append({
                                    "id": parts[0],
                                    "name": parts[1],
                                    "location": parts[2],
                                    "capacity": parts[3]
                                })
                    else:
                        flash("No rooms available for the selected time.", "info")
                else:
                    flash(f"Error searching rooms: {response}", "error")
            except Exception as e:
                flash(f"An unexpected error occurred: {e}", "error")

    return render_template("rooms.html", available_rooms=available_rooms, search_performed=search_performed)

@app.route("/book_room", methods=["POST"])
def book_room():
    if "user_id" not in session:
        flash("Please log in to book a room.", "error")
        return redirect(url_for("login"))

    room_id = request.form["room_id"]
    start_time = request.form["start_time"]
    end_time = request.form["end_time"]
    user_id = session["user_id"]

    if not all([room_id, start_time, end_time, user_id]):
        flash("Missing booking information.", "error")
        return redirect(url_for("rooms"))

    try:
        msg = f"BOOK_ROOM|{user_id}|{room_id}|{start_time}|{end_time}"
        response = send_to_master(msg)

        if response.startswith("BOOK_ROOM_SUCCESS"):
            _, booking_id, token = response.split("|")
            flash(f"Room booked successfully! Your booking ID is {booking_id} and token is {token}. Please keep this token safe.", "success")
        else:
            flash(f"Failed to book room: {response}", "error")
    except Exception as e:
        flash(f"An unexpected error occurred during booking: {e}", "error")

    return redirect(url_for("rooms"))


@app.route("/my_bookings")
def my_bookings():
    if "user_id" not in session:
        flash("Please log in to view your bookings.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    bookings = []
    try:
        msg = f"GET_USER_BOOKINGS|{user_id}"
        response = send_to_master(msg)

        if response.startswith("GET_USER_BOOKINGS_SUCCESS"):
            booking_data = response.split("|")[1:]
            if booking_data and booking_data[0] != "No bookings found":
                for booking_str in booking_data:
                    parts = booking_str.split(",")
                    if len(parts) == 8:
                        bookings.append({
                            "id": parts[0],
                            "room_name": parts[1],
                            "start_time": parts[2],
                            "end_time": parts[3],
                            "token": parts[4],
                            "status": parts[5],
                            "token_used": parts[6] == 'True'
                        })
            else:
                flash("You have no active bookings.", "info")
        else:
            flash(f"Error fetching bookings: {response}", "error")
    except Exception as e:
        flash(f"An unexpected error occurred while fetching bookings: {e}", "error")

    return render_template("my-bookings.html", bookings=bookings)

@app.route("/cancel_booking", methods=["POST"])
def cancel_booking():
    if "user_id" not in session:
        flash("Please log in to cancel a booking.", "error")
        return redirect(url_for("login"))

    booking_id = request.form["booking_id"]
    user_id = session["user_id"]

    try:
        msg = f"CANCEL_BOOKING|{user_id}|{booking_id}"
        response = send_to_master(msg)

        if response == "CANCEL_BOOKING_SUCCESS":
            flash("Booking cancelled successfully.", "success")
        else:
            flash(f"Failed to cancel booking: {response}", "error")
    except Exception as e:
        flash(f"An unexpected error occurred during cancellation: {e}", "error")

    return redirect(url_for("my_bookings"))

@app.route("/use_room", methods=["POST"])
def use_room():
    if "user_id" not in session:
        flash("Please log in to use a room.", "error")
        return redirect(url_for("login"))

    token = request.form["token"]

    try:
        msg = f"USE_ROOM|{token}"
        response = send_to_master(msg)

        if response.startswith("USE_ROOM_SUCCESS"):
            room_id = response.split("|")[1]
            flash(f"Booked {room_id}", "success")
        else:
            flash(f"Failed to use room: {response}", "error")
    except Exception as e:
        flash(f"An unexpected error occurred while trying to use the room: {e}", "error")

    return redirect(url_for("my_bookings"))

@app.route("/return_room", methods=["POST"])
def return_room():
    if "user_id" not in session:
        flash("Please log in to return a room.", "error")
        return redirect(url_for("login"))

    booking_id = request.form["booking_id"]
    user_id = session["user_id"]

    try:
        msg = f"RETURN_ROOM|{user_id}|{booking_id}"
        response = send_to_master(msg)

        if response == "RETURN_ROOM_SUCCESS":
            flash("Room marked as returned.", "success")
        else:
            flash(f"Failed to return room: {response}", "error")
    except Exception as e:
        flash(f"An unexpected error occurred while trying to return the room: {e}", "error")

    return redirect(url_for("my_bookings"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
