
from zoneinfo import ZoneInfo
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

    def get_room_inf(self):
        with self.rooms_lock:
            active_rooms_copy = dict(self.active_rooms)
        today = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)
        for room in active_rooms_copy.values():
            with self.db_lock:
                room_id_getter = self.db.conn.execute(
                    "SELECT id FROM rooms WHERE room_name=?",
                    (room["room_name"],)
                ).fetchone()["id"]
                
                room_bookings = self.db.conn.execute(
                    """
                    SELECT start_time, end_time 
                    FROM bookings 
                    WHERE room_id=? AND start_time>=? AND start_time<? AND end_time>=? AND status <> 'checked out'
                    ORDER BY start_time ASC
                    """,
                    (room_id_getter, today, tomorrow, now)
                ).fetchall()

            room["bookings"] = [
                {
                    "start_time": datetime.fromisoformat(booking["start_time"]).strftime("%H:%M"),
                    "end_time": datetime.fromisoformat(booking["end_time"]).strftime("%H:%M"),
                }
                for booking in room_bookings
            ]

        return active_rooms_copy
        
    def register_user(self, request: dict):
        full_name = request["Full_Name"]
        password = request["Password"]
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        email = request["Email"]
        unique_id = request["Unique_ID"]
        token = str(binascii.hexlify(os.urandom(20)).decode())
        role = "user"
        user = User(email=email, password=pw_hash, full_name=full_name,
                    user_id=unique_id, user_token=token, role=role)

        try:
            with self.db_lock:
                userId = self.db.create_user(user)
            active_rooms_copy = self.get_room_inf()
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
    def login_admin(self, request):
        email = request['Email']
        password = request['Password']
        try:
            with self.db_lock:
                admin_data = self.db. conn.execute("SELECT * FROM users WHERE email=? AND password=? AND role='admin'", (email, password)).fetchone()
            if admin_data:
                return {"op": "LOG", 
                        "action": "log in",
                        "type": "success",
                        "user_id" : admin_data["id"]
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
                active_rooms_copy = self.get_room_inf()
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
    
    def admin_information(self):
        try:
            with self.db_lock:
                user_count = self.db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                room_count = self.db.conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
                booking_count = self.db.conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
                recent_bookings = self.db.conn.execute("SELECT b.*, u.full_name, r.room_name FROM bookings b LEFT JOIN users u ON b.user_id = u.id LEFT JOIN rooms r ON b.room_id = r.id ORDER BY b.start_time DESC LIMIT 5").fetchall()
                rows = self.db.conn.execute("SELECT * FROM rooms").fetchall()
                room_statuses = [dict(row) for row in rows]

            return {
                'op': 'LOG', 'action': 'admin info', 'type': 'success',
                'user_count':user_count, 'room_count':room_count,
                'booking_count':booking_count, 'recent_bookings':recent_bookings,
                'room_statuses':room_statuses
            }
        except Exception as e:
            return {'op': 'LOG', 'action': 'admin info', 'type': 'failure', 'reason': str(e)}
    
    def admin_get_users(self):
        try:
            with self.db_lock:
                rows = self.db.conn.execute("SELECT * FROM users").fetchall()
            users = [dict(row) for row in rows]
            return {
                'op': 'LOG', 'action': 'admin get users', 'type': 'success',
                'users' : users
            }
        except Exception as e:
            return {'op': 'LOG', 'action': 'admin get users', 'type': 'failure', 'reason': str(e)}

    def create_security(self, request):
        try:
            name = request['name']
            email = request['email']
            password = request['password']
            passHash = hashlib.sha256(password.encode()).hexdigest()
            with self.db_lock:
                new_user = User(email=email, password=password, full_name=name, user_id=email, role='security', user_token=email)
                user_id = self.db.create_user(new_user) 
            return {'op': 'LOG', 'action': 'create security', 'type': 'success', 'user_id': user_id}
        except Exception as e:
            return {'op': 'LOG', 'action': 'create security', 'type': 'failure', 'reason': str(e)}

    def delete_user(self, request):
        try:
            with self.db_lock:
                self.db.conn.execute("DELETE FROM users WHERE id=?", (request['user_id'],))
                self.db.conn.commit
            return {'op': 'LOG', 'action': 'admin get users', 'type': 'success',
                    'user_id' : request['user_id']}
        except Exception as e:
           return {'op': 'LOG', 'action': 'delete user', 'type': 'failure', 'reason': str(e)} 

    def get_user(self, request):
        with self.db_lock:
            row = self.db.conn.execute("SELECT * FROM users WHERE id=?", (request['user_id'],)).fetchone()
            user_req = dict(row)
        return {'op': 'LOG', 'action': 'get user', 'type': 'success', 'user': user_req }

    def update_user(self, request):
        with self.db_lock:
            self.db.conn.execute("UPDATE users SET full_name=?, email=?, role=? WHERE id=?", (request['name'], request['email'], request['role'], request['user_id']))
        return {'op': 'LOG', 'action': 'update user', 'type': 'success'}

    def admin_get_rooms(self):
        with self.db_lock:
            rows = self.db.conn.execute("""
                SELECT r.id, r.room_name, r.status,
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
        rooms = [dict(row) for row in rows]
        return {'op' : 'LOG' , 'action' : 'ADMIN GET ROOMS','type':'success' ,'rooms' : rooms}

    def get_logs(self):
        with self.db_lock:
            rows = self.db.conn.execute("SELECT l.*, u.full_name FROM logs l LEFT JOIN users u ON l.user_id = u.id ORDER BY l.timestamp DESC").fetchall()
        logs = [dict(row) for row in rows]
        return {'op': 'LOG', 'action': 'GET LOGS', 'type': 'success', "logs": logs}
    def get_booking_logs(self):
        with self.db_lock:
            rows = self.db.conn.execute("SELECT b.*, u.full_name, r.room_name FROM bookings b LEFT JOIN users u ON b.user_id = u.id LEFT JOIN rooms r ON b.room_id = r.id ORDER BY b.start_time DESC").fetchall()
        bookings = [dict(row) for row in rows]
        return {'op': 'LOG', 'action': 'GET BOOKING LOGS', 'type': 'success', 'bookings': bookings}
    def get_booking_count(self):
        with self.db_lock:
            rows = self.db.conn.execute("SELECT room_id, COUNT(*) AS count FROM bookings GROUP BY room_id").fetchall()
        print(rows)
        data = [dict(row) for row in rows]
        return {'op': 'LOG', 'action': 'GET BOOKING COUNT', 'type': 'success', 'data': data}

    def get_sensor_history(self, request):
        with self.db_lock:
            rows = self.db.conn.execute(
                "SELECT timestamp, temperature, humidity, pressure FROM sensor_data WHERE room_id=? ORDER BY timestamp DESC LIMIT 20",
                (request['room_id'],)
            ).fetchall()
        return {'op': 'LOG', 'action': 'GET SENSOR HISTORY', 'type': 'success', 'rows':rows}
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
                    new_room = Room(room_name,"", 0, status="Available")
                    self.db.create_room(new_room)
                else:
                    room_bookings = self.db.conn.execute(
                        "SELECT * FROM bookings WHERE room_id=? and status <> 'checked out'",
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
                    "id": room_id,
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
                "booking_id": booking_id, "room id": request['room_id']
            }
        except Exception as e:
            return {
                "op": "LOG", "action": "booking", "type": "failure",
                "room_id": room_id, "reason": f"Booking failed: {e}"
            }

    def get_bookings(self, token: str):
        print("[DEBUG] Entering get_bookings with token:", token)
        try:
            with self.db_lock:
                now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)
                print("[DEBUG] Executing SQL query...")
                bookings_data = self.db.conn.execute(
                    "SELECT * FROM bookings WHERE token=? AND end_time > ? ORDER BY start_time ASC",
                    (token, now)
                ).fetchall()
                print("[DEBUG] Query executed. Rows fetched:", len(bookings_data))

            bookings_list = []
            for booking in bookings_data:
                print("[DEBUG] Processing booking:", dict(booking))
                if booking["status"] in ('Booked', 'checked in'):
                    bookings_list.append({
                        "booking_id": booking["id"],
                        "room_id": booking["room_id"],
                        "date": datetime.fromisoformat(booking["start_time"]).strftime("%Y-%m-%d"),
                        "start_time": datetime.fromisoformat(booking["start_time"]).strftime("%H:%M"),
                        "end_time": datetime.fromisoformat(booking["end_time"]).strftime("%H:%M"),
                        "full_start_time": datetime.fromisoformat(booking["start_time"]).strftime("%Y-%m-%dT%H:%M"),
                        "full_end_time": datetime.fromisoformat(booking["end_time"]).strftime("%Y-%m-%dT%H:%M"),
                        "status": booking["status"]
                    })

            response = {
                "op": "LOG",
                "action": "fetch_bookings",
                "type": "success",
                "bookings": bookings_list
            }
            print("[DEBUG] Returning response:", response)
            return response

        except Exception as e:
            print("[ERROR] get_bookings failed:", e)
            raise


    def check_in(self, request: dict):
        with self.db_lock:
            booking_id = request["booking_id"]
            booking = self.db.conn.execute(
                "SELECT * FROM bookings WHERE id=? and status='Booked'",
                (booking_id,)
            ).fetchone()
            if not booking:
                return {
                    "op": "LOG", "action": "check in", "type": "failure",
                    "reason": "Check-in failed: Invalid booking ID or already checked in/out"
                }
            else:
                self.db.conn.execute(
                            "UPDATE bookings SET status = ? WHERE id=?",
                            ("checked in", booking_id)
                        )
                self.db.conn.commit()
                return {
                    "op": "LOG", "action": "check in", "type": "success",
                    "message": "Check-in successful", "booking_id": booking_id, "room id": request['room_id']
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
                            "UPDATE bookings SET status = ? WHERE id=?",
                            ("checked out", booking_id)
                        )
                self.db.conn.commit()
                return {
                    "op": "LOG", "action": "check out", "type": "success",
                    "message": "Check-out successful", "booking_id": booking_id, "room id": request['room_id']
                }

    def cancel_booking(self, request: dict):
        print("Entering cancel_booking with request:", request)
        booking_id = request["booking_id"]
        token = request["token"]
        print(booking_id, token)
        with self.db_lock:
            booking = self.db.conn.execute(
                "SELECT * FROM bookings WHERE id=? and token=? and status='Booked'",
                (booking_id, token)
            ).fetchone()
            if not booking:
                return {
                    "op": "LOG", "action": "cancel booking", "type": "failure",
                    "reason": "Cancellation failed: Invalid booking ID, token, or booking already checked in/out"
                }
            else:
                self.db.conn.execute(
                            "DELETE FROM bookings WHERE id=?",
                            (booking_id, )
                        )
                self.db.conn.commit()
                return {
                    "op": "LOG", "action": "cancel booking", "type": "success",
                    "message": "Booking cancelled successfully", "booking_id": booking_id, "room id": request["room_id"]
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
                        msg = f"User checked in to room {log['room id']} successfully."
                        self.db.create_log(None, "check in", msg)
                    elif log["action"] == "check out":
                        msg = f"User checked out of room {log['room id']} successfully."
                        self.db.create_log(None, "check out", msg)
                    elif log["action"] == "booking":
                        msg = f"Room {log['room id']} booked successfully."
                        self.db.create_log(None, "booking", msg)
                    elif log["action"]== "cancel booking":
                        msg = f"Booking {log['booking_id']} on room {log['room id']} has been canceled"
                        self.db.create_log(None, "cancel booking", msg)
                elif log["type"] == "failure":
                    self.db.create_log(None, log["action"], log["reason"])

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
            elif request["op"] == "UPDATE_ROOMS":
                response = {
                    "op": "LOG", "action": "update rooms",
                    "type": "success", "rooms": self.get_room_inf()
                }
            elif request["op"] == "ADMIN_LOGIN":
                response = self.login_admin(request)
            elif request['op'] == "ADMIN_DASHBOARD":
                response = self.admin_information()
            elif request['op'] == 'GET USERS LIST':
                response = self.admin_get_users()
            elif request['op'] == 'CREATE SECURITY':
                response = self.create_security(request)
            elif request['op'] == 'DELETE USER':
                response = self.delete_user(request)
            elif request['op'] == 'GET USER':
                response = self.get_user(request)
            elif request['op'] == 'UPDATE USER':
                response = self.update_user(request)
            elif request['op'] == 'ADMIN GET ROOMS':
                response = self.admin_get_rooms()
            elif request['op'] == 'GET LOGS':
                response = self.get_logs()
            elif request['op'] == 'GET BOOKING LOGS':
                response = self.get_booking_logs()
            elif request['op'] == 'GET BOOKING COUNT':
                response = self.get_booking_count()
            elif request["op"] == "LOG":
                print(request["action"])
                if request["type"] == "success" and request["action"] == "booking":
                    response = self.book_room(request)
                    print(response)
                elif request["type"] == "success" and request["action"] == "check in":
                    response  = self.check_in(request)
                    print(response)
                elif request["type"] == "success" and request["action"] == "check out":
                    response = self.check_out(request)
                    print(response)
                elif request["type"] == "success" and request["action"] == "cancel booking":
                    response = self.cancel_booking(request)
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
            elif request["op"] == "GET_BOOKINGS":
                response = self.get_bookings(request["token"])
            else:
                response = {
                    "op": request.get("op"),
                    "type": "failure",
                    "reason": "Unknown operation"
                }
            print(response)
            self.log_create(response)
            print(response)
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
