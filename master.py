
from datetime import timedelta
from datetime import datetime
import sys
import os
import socket
import json
import hashlib
import threading
import binascii
import time
from typing import Optional, Tuple, Any

from database import Database
from models.user import User
from models.room import Room
from models.booking import Booking
import config


class Master:
    def __init__(self):
        self.running = True
        self.socket_server_thread = None
        self.active_rooms = {}

        # === Mutex Locks ===
        self.db_lock = threading.RLock()       # Protects all database access
        self.rooms_lock = threading.RLock()    # Protects self.active_rooms

        DB_FILE = os.path.join('database.db')
        self.db = Database(DB_FILE)

    # -------------------------
    # User Registration
    # -------------------------
    def register_user(self, request: dict):
        full_name = request["Full_Name"]
        password = request["Password"]
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        email = request["Email"]
        unique_id = request["Unique_ID"]
        token = str(binascii.hexlify(os.urandom(20)).decode())
        role = "user"

        print(f"Registering user: {email}, {full_name}, {unique_id}")
        user = User(email=email, password=pw_hash, full_name=full_name,
                    user_id=unique_id, user_token=token, role=role)

        try:
            with self.db_lock:
                userId = self.db.create_user(user)
            print(f"User {email} registered with ID {userId}")
            with self.rooms_lock:
                active_rooms_copy = dict(self.active_rooms)
            print(active_rooms_copy)
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = today + timedelta(days=1)
            now = datetime.now()
            for room in active_rooms_copy.values():
                with self.db_lock:
                    room_bookings = self.db.conn.execute(
                        """
                        SELECT start_time, end_time 
                        FROM bookings 
                        WHERE room_id=? AND start_time>=? AND start_time<? AND end_time>=?
                        ORDER BY start_time ASC
                        """,
                        (room["id"], today, tomorrow, now)
                    ).fetchall()

                room["bookings"] = [
                    {
                        "start_time": booking["start_time"],
                        "end_time": booking["end_time"],
                    }
                    for booking in room_bookings
                ]
            return {
                "op": "LOG", "action": "register", "type": "success",
                "message": "Registration successful",
                "user_token": token, "user_id": userId,
                "rooms": active_rooms_copy
            }
        except Exception as e:
            print(f"Error registering user {email}: {e}")
            return {
                "op": "LOG", "action": "register", "type": "failure",
                "user_id": unique_id,
                "reason": f"Registration failed: {e}"
            }

    # -------------------------
    # User Login
    # -------------------------
    def login_user(self, request: dict):
        email = request["Email"]
        password = request["Password"]
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            with self.db_lock:
                user_data = self.db.conn.execute(
                    "SELECT * FROM users WHERE email=? AND password=?",
                    (email, pw_hash)
                ).fetchone()

            if user_data:
                with self.rooms_lock:
                    active_rooms_copy = dict(self.active_rooms)
                print(active_rooms_copy)
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow = today + timedelta(days=1)
                now = datetime.now()
                for room in active_rooms_copy.values():
                    with self.db_lock:
                        room_bookings = self.db.conn.execute(
                            """
                            SELECT start_time, end_time 
                            FROM bookings 
                            WHERE room_id=? AND start_time>=? AND start_time<? AND end_time>=?
                            ORDER BY start_time ASC
                            """,
                            (room["id"], today, tomorrow, now)
                        ).fetchall()

                    room["bookings"] = [
                        {
                            "start_time": booking["start_time"],
                            "end_time": booking["end_time"],
                        }
                        for booking in room_bookings
                    ]
                return {
                    "op": "LOG", "action": "log in", "type": "success",
                    "full_name": user_data["full_name"],
                    "user_token": user_data["user_token"],
                    "user_id": user_data["id"],
                    "role": user_data["role"],
                    "rooms": active_rooms_copy
                }
            else:
                return {
                    "op": "LOG", "action": "log in", "type": "failure",
                    "reason": "Login failed: Wrong credentials"
                }
        except Exception as e:
            return {
                "op": "LOG", "action": "log in", "type": "failure",
                "reason": f"Login failed: {e}"
            }

    # -------------------------
    # Room Activation
    # -------------------------
    def activated_room(self, request: dict):
        room_id = request["room_id"]
        room_name = request["room_name"]
        room_ip = request["ip"]
        room_port = request["port"]

        try:
            bookings_list = {}
            with self.db_lock:
                room_data = self.db.conn.execute(
                    "SELECT * FROM rooms WHERE id=?",
                    (room_id,)
                ).fetchone()

                if not room_data:
                    new_room = Room(id=room_id, room_name=room_name,
                                    location="", capacity=0, status="Available")
                    self.db.create_room(new_room)
                else:
                    room_bookings = self.db.conn.execute(
                        "SELECT * FROM bookings WHERE room_id=?",
                        (room_id,)
                    ).fetchall()
                    for booking in room_bookings:
                        bookings_list[f"booking_{booking['start_time']}"] = {
                            "start_time": booking["start_time"],
                            "end_time": booking["end_time"],
                            "token": booking["token"]
                        }

            with self.rooms_lock:
                self.active_rooms[room_id] = {
                    "room_name": room_name,
                    "ip": room_ip,
                    "port": room_port,
                    "status": request["status"]
                }

            return {
                "op": "LOG", "action": "room connection",
                "type": "success", "bookings": bookings_list,
                "room id": room_id
            }

        except Exception as e:
            return {
                "op": "LOG", "action": "room connection",
                "type": "failure", "reason": f"Room activation failed: {e}"
            }

    # -------------------------
    # Room Booking
    # -------------------------
    def book_room(self, request: dict):
        with self.db_lock:
            user_id = self.db.conn.execute(
                "SELECT id FROM users WHERE user_token=?",
                (request["token"],)
            ).fetchone()["id"]

        room_id = request["room_id"]
        start_time = request["starttime"]
        end_time = request["endtime"]
        token = request["token"]
        booking = Booking(user_id=user_id, room_id=room_id,
                          start_time=start_time, end_time=end_time, token=token)
        try:
            with self.db_lock:
                booking_id = self.db.create_booking(booking)
            return {
                "op": "LOG", "action": "booking",
                "type": "success", "message": "Booking successful",
                "booking_id": booking_id
            }
        except Exception as e:
            return {
                "op": "LOG", "action": "booking", "type": "failure",
                "room_id": room_id, "reason": f"Booking failed: {e}"
            }

    def get_bookings(self, token: str):
        with self.db_lock:
            bookings_data = self.db.conn.execute(
                "SELECT * FROM bookings WHERE token=?",
                (token,)
            ).fetchall()
        bookings_list = []
        for booking in bookings_data:
            if booking["status"] == 'booked' or booking["status"] == 'checked in':
                bookings_list.append({
                    "booking_id": booking["id"],
                    "room_id": booking["room_id"],
                    "start_time": booking["start_time"],
                    "end_time": booking["end_time"],
                    "status": booking["status"]
                })
        return {"op": "LOG", "action": "fetch_bookings", "type": "success", "bookings": bookings_list}

    def check_in(self, request: dict):
        with self.db_lock:
            booking_id = request["booking_id"]
            booking = self.db.conn.execute(
                "SELECT * FROM bookings WHERE id=? and status='booked'",
                (booking_id,)
            ).fetchone()
            if not booking:
                return {
                    "op": "LOG", "action": "check in", "type": "failure",
                    "reason": "Check-in failed: Invalid booking ID or already checked in/out"
                }
            else:
                self.db.conn.execute(
                            "UPDATE booking SET status = ? WHERE id=?",
                            ("checked in", booking_id)
                        )
                self.db.conn.commit()
                return {
                    "op": "LOG", "action": "check in", "type": "success",
                    "message": "Check-in successful", "booking_id": booking_id
                }   
    def check_out(self, request: dict):
        with self.db_lock:
            booking_id = request["booking_id"]
            booking = self.db.conn.execute(
                "SELECT * FROM bookings WHERE id=? and status='checked in'",
                (booking_id,)
            ).fetchone()
            if not booking:
                return {
                    "op": "LOG", "action": "check out", "type": "failure",
                    "reason": "Check-out failed: Invalid booking ID or not checked in"
                }
            else:
                self.db.conn.execute(
                            "UPDATE booking SET status = ? WHERE id=?",
                            ("checked out", booking_id)
                        )
                self.db.conn.commit()
                return {
                    "op": "LOG", "action": "check out", "type": "success",
                    "message": "Check-out successful", "booking_id": booking_id
                }

    # -------------------------
    # Logging Operations
    # -------------------------
    def log_create(self, log):
        if log["op"] == "LOG":
            with self.db_lock:
                if log["type"] == "success":
                    msg = ""
                    if log["action"] == "register":
                        msg = f"User {log['user_id']} registered successfully."
                        self.db.create_log(log["user_id"], "register", msg)
                    elif log["action"] == "log in":
                        msg = f"User {log['user_id']} logged in successfully."
                        self.db.create_log(log["user_id"], "log in", msg)
                    elif log["action"] == "room connection":
                        msg = f"Room {log['room id']} connected successfully."
                        self.db.create_log(None, "room connection", msg)
                    elif log["action"] == "check in":
                        msg = f"User checked in to room {log['room_id']} successfully."
                        self.db.create_log(None, "check in", msg)
                    elif log["action"] == "check out":
                        msg = f"User checked out of room {log['room_id']} successfully."
                        self.db.create_log(None, "check out", msg)
                    elif log["action"] == "booking":
                        msg = f"Room {log['room_id']} booked successfully."
                        self.db.create_log(None, "booking", msg)
                elif log["type"] == "failure":
                    self.db.create_log(None, log["action"], log["reason"])

    # -------------------------
    # Handle Client Connections
    # -------------------------
    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        try:
            request_dict = conn.recv(1024).decode()
            request = json.loads(request_dict)
            print(request["op"])

            if request["op"] == "REGISTER":
                response = self.register_user(request)
            elif request["op"] == "LOGIN":
                response = self.login_user(request)
            elif request["op"] == "ACTIVATED_ROOM":
                response = self.activated_room(request)
            elif request["op"] == "LOG":
                if request["type"] == "success" and request["action"] == "booking":
                    response = self.book_room(request)
                elif request["type"] == "success" and request["action"] == "check in":
                    response  = self.check_in(request)
                elif request["type"] == "success" and request["action"] == "check out":
                    response = self.check_out(request)
                else:
                    response = request
            elif request["op"] == "SENSOR_DATA":
                room_id = request["room_id"]
                temperature = request["temperature"]
                humidity = request["humidity"]
                pressure = request["pressure"]
                status = request["status"]
                timestamp = datetime.fromtimestamp(request["timestamp"])

                # Update shared memory safely
                with self.rooms_lock:
                    if room_id in self.active_rooms:
                        self.active_rooms[room_id]["status"] = status

                # Update database safely
                with self.db_lock:
                    self.db.conn.execute(
                        "UPDATE rooms SET status = ? WHERE id=?",
                        (status, room_id)
                    )
                    self.db.conn.execute(
                        "INSERT INTO sensor_data (room_id, timestamp, temperature, humidity, pressure) VALUES (?, ?, ?, ?, ?)",
                        (room_id, timestamp, temperature, humidity, pressure)
                    )
                    self.db.conn.commit()

                response = {
                    "op": "LOG", "action": "sensor_update",
                    "type": "success", "room_id": room_id
                }
            else:
                response = {
                    "op": request.get("op"),
                    "type": "failure",
                    "reason": "Unknown operation"
                }

            self.log_create(response)
            conn.sendall(json.dumps(response).encode())

        except Exception as e:
            error_response = {"op": "LOG", "type": "failure", "reason": str(e)}
            conn.sendall(json.dumps(error_response).encode())
        finally:
            conn.close()

    # -------------------------
    # Socket Server Thread
    # -------------------------
    def _socket_server_thread(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((config.SOCKET_HOST, config.SOCKET_PORT))
            s.listen()

            s.settimeout(1.0)
            while self.running:
                try:
                    conn, addr = s.accept()
                    thread = threading.Thread(
                        target=self._handle_client, args=(conn, addr))
                    thread.daemon = True
                    thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Socket error: {e}")

    # -------------------------
    # Start & Stop
    # -------------------------
    def start(self):
        self.socket_server_thread = threading.Thread(
            target=self._socket_server_thread)
        self.socket_server_thread.daemon = True
        self.socket_server_thread.start()

        print("Master server started.")
        while self.running:
            time.sleep(1)
        self.stop()

    def stop(self):
        self.running = False
        print("Master server stopped.")


if __name__ == "__main__":
    master = Master()
    master.start()
