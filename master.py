
from typing import Optional, Tuple, Any
import binascii

from database import Database
from models.user import User
from models.room import Room
from models.booking import Booking
from models.status import Status
import config

from paho.mqtt.client import Client, MQTTMessage, ConnectFlags
from paho.mqtt.properties import Properties
import paho.mqtt.client as mqtt
from paho.mqtt.reasoncodes import ReasonCode

import socket, os, datetime, threading, time, json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib
import secrets

class Master:
    def __init__(self):
        self.running = True
        self.socket_server_thread = None
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_subscriber_thread = None
        self.active_rooms = {}


        DB_FILE = os.path.join('database.db')
        self.db = Database(DB_FILE)

    def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode, properties: Optional[Properties]) -> None:
        if rc == 0:
            print(f"MQTT | Master connected to MQTT")
            client.subscribe(config.TOPIC_ROOM_SENSOR_DATA_PREFIX + "+/status")
            client.subscribe(config.TOPIC_ROOM_REGISTER)
            print(f"MQTT | Master subscribed to topic: {config.TOPIC_ROOM_SENSOR_DATA_PREFIX}+/status")
            print(f"MQTT | Master subscribed to topic: {config.TOPIC_ROOM_REGISTER}")
        else:
            print(f"MQTT | Master failed to connect to MQTT")

    def _on_mqtt_message(self, client: Client, userdata: Any, msg: MQTTMessage):
        topic_parts = msg.topic.split('/')
        if len(topic_parts) == 3 and topic_parts[0] == 'rooms' and topic_parts[2] == 'status':
            room_id = topic_parts[1]
            try:
                payload = json.loads(msg.payload.decode())
                temperature = payload.get("temperature")
                humidity = payload.get("humidity")
                pressure = payload.get("pressure")
                status = payload.get("status")
                timestamp = datetime.fromisoformat(payload.get("timestamp"))

                # Update room status in DB
                self.db.conn.execute(
                    "UPDATE rooms SET status = ? WHERE id = ?",
                    (status, room_id)
                )

                # Insert sensor data
                self.db.conn.execute(
                    "INSERT INTO sensor_data (room_id, timestamp, temperature, humidity, pressure) VALUES (?, ?, ?, ?, ?)",
                    (room_id, timestamp, temperature, humidity, pressure)
                )

                self.db.conn.commit()
                if room_id in self.active_rooms:
                    self.active_rooms[room_id]['status'] = status
                print(f"MQTT | Received sensor data for room {room_id}: {payload}")
            except Exception as e:
                print(f"MQTT | Error processing sensor data for room {room_id}: {e}")
        elif msg.topic == config.TOPIC_ROOM_REGISTER:
            try:
                payload = json.loads(msg.payload.decode())
                room_id = payload.get("room_id")
                room_name = payload.get("room_name")
                room_ip = payload.get("ip")
                room_port = payload.get("port")
                location = payload.get("location")
                capacity = payload.get("capacity")
                status = payload.get("status")

                bookings_list = {}
                room_data = self.db.conn.execute(
                    "SELECT * FROM rooms WHERE id=?",
                    (room_id,)
                ).fetchone()

                if not room_data:
                    new_room = Room(room_name, location, capacity, status="Available")
                    self.db.create_room(new_room)
                else:
                    self.db.conn.execute(
                        "UPDATE rooms SET room_name = ?, location = ?, capacity = ? WHERE id = ?",
                        (room_name, location, capacity, room_id)
                    )
                    self.db.conn.commit()
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

                self.active_rooms[room_id] = {
                    "id": room_id,
                    "room_name": room_name,
                    "ip": room_ip,
                    "port": room_port,
                    "status": status,
                    "location": location,
                    "capacity": capacity
                }
                print(f"MQTT | Room {room_id} registered: {payload}")
            except Exception as e:
                print(f"MQTT | Error processing room registration: {e}")
        else:
            print(f"MQTT | Received message on unexpected topic: {msg.topic}")

    def _mqtt_subscriber_thread(self):
        try:
            self.mqtt_client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
            self.mqtt_client.loop_forever()
        except Exception as e:
            print(f"MQTT | Error in MQTT subscriber thread: {e}")
        finally:
            self.mqtt_client.disconnect()
            print("MQTT | Master MQTT subscriber stopped.")

    # -------------------------
    # User Registration
    # -------------------------

    def get_room_inf(self):
        # Get all rooms from the database as the source of truth
        all_rooms_from_db = self.db.conn.execute("SELECT * FROM rooms").fetchall()
        
        # Use a dictionary for easy lookup and modification
        rooms_map = {room['id']: dict(room) for room in all_rooms_from_db}

        today = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)

        for room_id, room in rooms_map.items():
            if room_id in self.active_rooms:
                room.update(self.active_rooms[room_id])

            # Prioritize manually set status from DB
            db_status = room['status']
            if db_status in [Status.MAINTENANCE.value, Status.FAULT.value, Status.OCCUPIED.value]:
                room['status'] = db_status
            else:
                # Check for active bookings at the current time
                future_booking = self.db.conn.execute("""
                    SELECT 1 FROM bookings 
                    WHERE room_id = ? AND start_time <= ? AND end_time > ? AND status IN (?, ?)
                    LIMIT 1
                """, (room_id, now, now, Status.BOOKED.value, Status.CHECKED_IN.value)).fetchone()

                if future_booking:
                    room['status'] = Status.BOOKED.value
                else:
                    room['status'] = Status.AVAILABLE.value

            room_bookings = self.db.conn.execute(
                """
                SELECT b.start_time, b.end_time, u.full_name
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                WHERE b.room_id=? AND b.start_time>=? AND b.start_time<? AND b.end_time>=? AND b.status NOT IN ('checked out', 'Cancelled')
                ORDER BY b.start_time ASC
                """,
                (room_id, today, tomorrow, now)
            ).fetchall()

            latest_sensor_data = self.db.conn.execute(
                """
                SELECT temperature, humidity, pressure
                FROM sensor_data
                WHERE room_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (room_id,)
            ).fetchone()

            room["bookings"] = [
                {
                    "start_time": datetime.fromisoformat(booking["start_time"]).strftime("%H:%M"),
                    "end_time": datetime.fromisoformat(booking["end_time"]).strftime("%H:%M"),
                    "full_name": booking["full_name"],
                }
                for booking in room_bookings
            ]

            if latest_sensor_data:
                room["temperature"] = f"{latest_sensor_data['temperature']:.1f}"
                room["humidity"] = f"{latest_sensor_data['humidity']:.1f}"
                room["pressure"] = f"{latest_sensor_data['pressure']:.1f}"
            else:
                room["temperature"] = "N/A"
                room["humidity"] = "N/A"
                room["pressure"] = "N/A"

        return rooms_map
        
    def register_user(self, request: dict):
        full_name = request["Full_Name"]
        password = request["Password"]
        email = request["Email"]
        unique_id = request["Unique_ID"]
        token = str(binascii.hexlify(os.urandom(20)).decode())
        role = "user"
        user = User(email=email, password=password, full_name=full_name,
                    user_id=unique_id, user_token=token, role=role)

        try:
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
        try:
            user_data = self.db.conn.execute(
                "SELECT * FROM users WHERE email=? AND password=?",
                (email, password)
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
            new_user = User(email=email, password=password, full_name=name, user_id=email, role='security', user_token=email)
            user_id = self.db.create_user(new_user) 
            return {'op': 'LOG', 'action': 'create security', 'type': 'success', 'user_id': user_id}
        except Exception as e:
            return {'op': 'LOG', 'action': 'create security', 'type': 'failure', 'reason': str(e)}

    def delete_user(self, request):
        try:
            self.db.conn.execute("DELETE FROM users WHERE id=?", (request['user_id'],))
            self.db.conn.commit
            return {'op': 'LOG', 'action': 'admin get users', 'type': 'success',
                    'user_id' : request['user_id']}
        except Exception as e:
           return {'op': 'LOG', 'action': 'delete user', 'type': 'failure', 'reason': str(e)} 

    def get_user(self, request):
        row = self.db.conn.execute("SELECT * FROM users WHERE id=?", (request['user_id'],)).fetchone()
        user_req = dict(row)
        return {'op': 'LOG', 'action': 'get user', 'type': 'success', 'user': user_req }

    def update_user(self, request):
        self.db.conn.execute("UPDATE users SET full_name=?, email=?, role=? WHERE id=?", (request['name'], request['email'], request['role'], request['user_id']))
        return {'op': 'LOG', 'action': 'update user', 'type': 'success'}

    def admin_get_rooms(self):
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
        rows = self.db.conn.execute("SELECT l.*, u.full_name FROM logs l LEFT JOIN users u ON l.user_id = u.id ORDER BY l.timestamp DESC").fetchall()
        logs = [dict(row) for row in rows]
        return {'op': 'LOG', 'action': 'GET LOGS', 'type': 'success', "logs": logs}
    def get_booking_logs(self):
        rows = self.db.conn.execute("SELECT b.*, u.full_name, r.room_name FROM bookings b LEFT JOIN users u ON b.user_id = u.id LEFT JOIN rooms r ON b.room_id = r.id ORDER BY b.start_time DESC").fetchall()
        bookings = [dict(row) for row in rows]
        return {'op': 'LOG', 'action': 'GET BOOKING LOGS', 'type': 'success', 'bookings': bookings}
    def get_booking_count(self):
        rows = self.db.conn.execute("SELECT r.room_name, COUNT(b.id) AS count FROM rooms r LEFT JOIN bookings b ON r.id = b.room_id GROUP BY r.id").fetchall()
        print(rows)
        data = [dict(row) for row in rows]
        return {'op': 'LOG', 'action': 'GET BOOKING COUNT', 'type': 'success', 'data': data}

    def get_sensor_history(self, request):
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
        location = request["location"]
        capacity = request["capacity"]

        try:
            bookings_list = {}
            room_data = self.db.conn.execute(
                "SELECT * FROM rooms WHERE id=?",
                (room_id,)
            ).fetchone()

            if not room_data:
                new_room = Room(room_name, location, capacity, status="Available")
                self.db.create_room(new_room)
            else:
                self.db.conn.execute(
                    "UPDATE rooms SET room_name = ?, location = ?, capacity = ? WHERE id = ?",
                    (room_name, location, capacity, room_id)
                )
                self.db.conn.commit()
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

                self.active_rooms[room_id] = {
                    "id": room_id,
                    "room_name": room_name,
                    "ip": room_ip,
                    "port": room_port,
                    "status": request["status"],
                    "location": location,
                    "capacity": capacity
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
        user_id = self.db.conn.execute(
            "SELECT id FROM users WHERE user_token=?",
            (request["token"],)
        ).fetchone()["id"]

        room_id = request["room_id"]
        start_time = datetime.fromisoformat(request["starttime"])
        duration_seconds = request["duration"]
        end_time = start_time + timedelta(seconds=duration_seconds)
        booking_access_token = secrets.token_hex(16)

        booking = Booking(user_id=user_id, room_id=room_id,
                          start_time=start_time, end_time=end_time, token=booking_access_token)

        overlapping_bookings = self.db.conn.execute(
            """SELECT * FROM bookings 
            WHERE room_id = ? AND (start_time < ? AND end_time > ?) AND status NOT IN ('Cancelled', 'checked out')
            """,
            (room_id, end_time, start_time)
        ).fetchall()

        if overlapping_bookings:
            return {
                "op": "LOG", "action": "booking", "type": "failure",
                "room_id": room_id, "reason": "Time slot not available"
            }

        try:
            booking_id = self.db.create_booking(booking)

            # Update room status in DB
            self.db.conn.execute(
                "UPDATE rooms SET status = ? WHERE id = ?",
                (Status.BOOKED.value, room_id)
            )
            self.db.conn.commit()

            # Publish MQTT message to room
            mqtt_payload = {
                "op": "UPDATE_STATUS",
                "status": Status.BOOKED.value,
                "booking_id": booking_id,
                "booking_access_token": booking_access_token
            }
            self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{room_id}/command", json.dumps(mqtt_payload))

            return {
                "op": "LOG", "action": "booking",
                "type": "success", "message": "Booking successful",
                "booking_id": booking_id, "room_id": request['room_id'],
                "booking_access_token": booking_access_token
            }
        except Exception as e:
            print(f"MASTER | Booking failed: {e}") # Add this
            return {
                "op": "LOG", "action": "booking", "type": "failure",
                "room_id": room_id, "reason": f"Booking failed: {e}"
            }

    def get_bookings(self, user_token: str):
        try:
            user_id = self.db.conn.execute(
                "SELECT id FROM users WHERE user_token=?",
                (user_token,)
            ).fetchone()["id"]

            now = datetime.now().replace(microsecond=0)
            bookings_data = self.db.conn.execute(
                "SELECT * FROM bookings WHERE user_id=? AND end_time > ? ORDER BY start_time ASC",
                (user_id, now)
            ).fetchall()

            bookings_list = []
            for booking in bookings_data:
                print("[DEBUG] Processing booking:", dict(booking))
                if booking["status"] in (Status.BOOKED.value, Status.CHECKED_IN.value):
                    bookings_list.append({
                        "booking_id": booking["id"],
                        "room_id": booking["room_id"],
                        "date": datetime.fromisoformat(booking["start_time"]).strftime("%Y-%m-%d"),
                        "start_time": datetime.fromisoformat(booking["start_time"]).strftime("%H:%M"),
                        "end_time": datetime.fromisoformat(booking["end_time"]).strftime("%H:%M"),
                        "full_start_time": datetime.fromisoformat(booking["start_time"]).strftime("%Y-%m-%dT%H:%M"),
                        "full_end_time": datetime.fromisoformat(booking["end_time"]).strftime("%Y-%m-%dT%H:%M"),
                        "status": booking["status"],
                        "booking_access_token": booking["token"]
                    })

            response = {
                "op": "LOG",
                "action": "fetch_bookings",
                "type": "success",
                "bookings": bookings_list
            }
            return response

        except Exception as e:
            print("[ERROR] get_bookings failed:", e)
            raise


    def check_in(self, request: dict):
        print(f"MASTER | check_in request: {request}")
        booking_id = request["booking_id"]
    
        booking = self.db.conn.execute(
            "SELECT * FROM bookings WHERE id=? and status=?",
            (booking_id, Status.BOOKED.value)
        ).fetchone()
        print(f"MASTER | check_in booking: {booking}")
        if not booking:
            return {
                "op": "LOG", "action": "check in", "type": "failure",
                "reason": "Invalid booking ID or already checked in/out"
            }

        now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)
        start_time = datetime.fromisoformat(booking['start_time'])
        end_time = datetime.fromisoformat(booking['end_time'])

        if not (start_time <= now and now < end_time):
            return {
                "op": "LOG", "action": "check in", "type": "failure",
                "reason": "Check-in is not available at this time."
            }

        room_id = booking['room_id']
        self.db.conn.execute(
                    "UPDATE bookings SET status = ? WHERE id=?",
                    (Status.CHECKED_IN.value, booking_id)
                )
        self.db.conn.commit()

        # Publish MQTT message to room
        mqtt_payload = {
            "op": "UPDATE_STATUS",
            "status": Status.OCCUPIED.value
        }
        self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{room_id}/command", json.dumps(mqtt_payload))

        return {
            "op": "LOG", "action": "check in", "type": "success",
            "message": "Check-in successful", "booking_id": booking_id, "room id": room_id
        }

    def check_out(self, request: dict):
        booking_id = request["booking_id"]
        booking = self.db.conn.execute(
            "SELECT * FROM bookings WHERE id=? and status=?",
            (booking_id, Status.CHECKED_IN.value)
        ).fetchone()
        if not booking:
            return {
                "op": "LOG", "action": "check out", "type": "failure",
                "reason": "Check-out failed: Invalid booking ID or not checked in"
            }
        else:
            room_id = booking['room_id']
            self.db.conn.execute(
                        "UPDATE bookings SET status = ? WHERE id=?",
                        (Status.CHECKED_OUT.value, booking_id)
                    )
            self.db.conn.commit()

            # Publish MQTT message to room
            mqtt_payload = {
                "op": "UPDATE_STATUS",
                "status": Status.AVAILABLE.value
            }
            self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{room_id}/command", json.dumps(mqtt_payload))

            return {
                "op": "LOG", "action": "check out", "type": "success",
                "message": "Check-out successful", "booking_id": booking_id, "room id": room_id
            }

    def cancel_booking(self, request: dict):
        print("Entering cancel_booking with request:", request)
        booking_id = request["booking_id"]
        token = request["token"]
        print(f"MASTER | cancel_booking request: {request}")
        print(f"MASTER | cancel_booking booking_id: {booking_id}, token: {token}")
        booking = self.db.conn.execute(
            "SELECT * FROM bookings WHERE id=? and token=? and status=?",
            (booking_id, token, Status.BOOKED.value)
        ).fetchone()
        print(f"MASTER | cancel_booking booking: {booking}")
        if not booking:
            return {
                "op": "LOG", "action": "cancel booking", "type": "failure",
                "reason": "Cancellation failed: Invalid booking ID, token, or booking already checked in/out"
            }
        else:
            room_id = booking['room_id']
            self.db.conn.execute(
                        "UPDATE bookings SET status = ? WHERE id=?",
                        (Status.CANCELLED.value, booking_id)
                    )
            self.db.conn.commit()

            # Publish MQTT message to room
            mqtt_payload = {
                "op": "UPDATE_STATUS",
                "status": Status.AVAILABLE.value
            }
            self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{room_id}/command", json.dumps(mqtt_payload))

            return {
                "op": "LOG", "action": "cancel booking", "type": "success",
                "message": "Booking cancelled successfully", "booking_id": booking_id, "room id": room_id
            }

    def validate_booking_token(self, request: dict):
        room_id = request["room_id"]
        booking_access_token = request["booking_access_token"]
        now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)

        # First, check if the token and room_id exist at all
        booking = self.db.conn.execute(
            """SELECT * FROM bookings 
            WHERE room_id = ? AND token = ?
            """,
            (room_id, booking_access_token)
        ).fetchone()

        if not booking:
            return {
                "op": "LOG", "action": "validate token", "type": "failure",
                "reason": "Invalid token or room ID."
            }

        # Check if the booking is cancelled
        if booking['status'] == Status.CANCELLED.value:
            return {
                "op": "LOG", "action": "validate token", "type": "failure",
                "reason": "This booking has been cancelled."
            }

        # Check if the booking is already checked in or out
        if booking['status'] == Status.CHECKED_IN.value:
            return {
                "op": "LOG", "action": "validate token", "type": "failure",
                "reason": "This booking is already checked in."
            }
        if booking['status'] == Status.CHECKED_OUT.value:
            return {
                "op": "LOG", "action": "validate token", "type": "failure",
                "reason": "This booking has already been checked out."
            }

        # Check if the current time is within the booking period
        start_time = datetime.fromisoformat(booking['start_time'])
        end_time = datetime.fromisoformat(booking['end_time'])

        if not (start_time <= now and now < end_time):
            if now < start_time:
                return {
                    "op": "LOG", "action": "validate token", "type": "failure",
                    "reason": "Check-in is not yet available for this booking."
                }
            # now >= end_time
            else:
                return {
                    "op": "LOG", "action": "validate token", "type": "failure",
                    "reason": "This booking has expired."
                }
        
        # If all checks pass, and status is BOOKED, then it's valid
        if booking['status'] == Status.BOOKED.value:
            return {
                "op": "LOG", "action": "validate token", "type": "success",
                "message": "Token is valid", "booking_id": booking["id"], "room_id": room_id
            }
        else:
            return {
                "op": "LOG", "action": "validate token", "type": "failure",
                "reason": f"Booking status is {booking['status']}.", "room_id": room_id
            }

    # -------------------------
    # Logging Operations
    # -------------------------
    def log_create(self, log):
        if log["op"] == "LOG":
            if log["type"] == "success":
                msg = ""
                if log["action"] == "register":
                    msg = f"User {log['user_id']} registered successfully."
                    self.db.create_log(log["user_id"], "register", msg)
                elif log["action"] == "log in":
                    msg = f"User {log['user_id']} logged in successfully."
                    self.db.create_log(log["user_id"], "log in", msg)
                elif log["action"] == "room connection":
                    msg = f"Room {log['room_id']} connected successfully."
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
                elif log["action"]== "cancel booking":
                    msg = f"Booking {log['booking_id']} on room {log['room_id']} has been canceled"
                    self.db.create_log(None, "cancel booking", msg)
            elif log["type"] == "failure":
                self.db.create_log(None, log["action"], log["reason"])

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        try:
            request_dict = conn.recv(1024).decode()
            request = json.loads(request_dict)
            print(f"MASTER | Received request: {request}")
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
            elif request["op"] == "BOOK_ROOM":
                response = self.book_room(request)
            elif request["op"] == "CHECK_IN":
                response = self.check_in(request)
            elif request["op"] == "CHECK_OUT":
                response = self.check_out(request)
            elif request["op"] == "CANCEL_BOOKING":
                response = self.cancel_booking(request)
            elif request["op"] == "GET_BOOKINGS":
                response = self.get_bookings(request["token"])
            elif request["op"] == "GET_ROOMS":
                rooms_data = self.get_room_inf()
                response = {"op": "GET_ROOMS", "type": "success", "rooms": rooms_data}
            elif request["op"] == "VALIDATE_BOOKING_TOKEN":
                response = self.validate_booking_token(request)
            elif request["op"] == "GET_ALL_ROOM_STATUSES":
                rooms_data = self.get_room_inf()
                response = {"op": "GET_ALL_ROOM_STATUSES", "type": "success", "rooms": rooms_data}
            else:
                response = {
                    "op": request.get("op"),
                    "type": "failure",
                    "reason": "Unknown operation"
                }
            print(response)
            self.log_create(response)
            print(f"MASTER | Sending response: {json.dumps(response)}") # Add this line
            conn.sendall(json.dumps(response).encode()) # Sends the response

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

        self.mqtt_subscriber_thread = threading.Thread(target=self._mqtt_subscriber_thread)
        self.mqtt_subscriber_thread.daemon = True
        self.mqtt_subscriber_thread.start()

        print("Master server started.")
        while self.running:
            time.sleep(1)
        self.stop()

    def stop(self):
        self.running = False
        self.mqtt_client.disconnect()
        print("Master server stopped.")


if __name__ == "__main__": 
    master = Master()
    master.start()
