
from typing import Optional, Tuple, Any

from database import Database
from models.user import User
from models.room import Room
from models.booking import Booking
import config

from paho.mqtt.client import Client, MQTTMessage, ConnectFlags
from paho.mqtt.properties import Properties
import paho.mqtt.client as mqtt
from paho.mqtt.reasoncodes import ReasonCode
import socket, os, datetime, threading, time, json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
            # Enrich with live data from active_rooms if available
            if room_id in self.active_rooms:
                room.update(self.active_rooms[room_id])

            # The rest of the logic is the same, just applied to `room`
            room_bookings = self.db.conn.execute(
                """
                SELECT b.start_time, b.end_time, u.full_name
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                WHERE b.room_id=? AND b.start_time>=? AND b.start_time<? AND b.end_time>=?
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
        start_time = datetime.fromisoformat(request["starttime"]) # Convert starttime
        duration_seconds = request["duration"]
        end_time = start_time + timedelta(seconds=duration_seconds) # Calculate end_time
        token = request["token"]
        booking = Booking(user_id=user_id, room_id=room_id,
                          start_time=start_time, end_time=end_time, token=token)
        try:
            print(f"MASTER | Attempting to book room: {room_id} for user {user_id} from {start_time} to {end_time}") # Add this
            booking_id = self.db.create_booking(booking)
            print(f"MASTER | Booking successful, booking_id: {booking_id}") # Add this

            # Publish MQTT message to room
            mqtt_payload = {
                "op": "BOOK_ROOM",
                "room_id": room_id,
                "booking_id": booking_id,
                "starttime": start_time.isoformat(),
                "endtime": end_time.isoformat(),
                "token": token
            }
            self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{room_id}/command", json.dumps(mqtt_payload))
            print(f"MASTER | Published BOOK_ROOM MQTT for room {room_id}") # Add this

            return {
                "op": "LOG", "action": "booking",
                "type": "success", "message": "Booking successful",
                "booking_id": booking_id
            }
        except Exception as e:
            print(f"MASTER | Booking failed: {e}") # Add this
            return {
                "op": "LOG", "action": "booking", "type": "failure",
                "room_id": room_id, "reason": f"Booking failed: {e}"
            }

    def get_bookings(self, token: str):
        try:
            now = datetime.now().replace(microsecond=0) # Removed ZoneInfo and replace(tzinfo=None)
            bookings_data = self.db.conn.execute(
                "SELECT * FROM bookings WHERE token=? AND end_time > ? ORDER BY start_time ASC",
                (token, now)
            ).fetchall()

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
            return response

        except Exception as e:
            print("[ERROR] get_bookings failed:", e)
            raise


    def check_in(self, request: dict):
        booking_id = request["booking_id"]
        print(f"MASTER | Attempting check-in for booking_id: {booking_id}")
        booking = self.db.conn.execute(
            "SELECT * FROM bookings WHERE id=? and status='Booked'",
            (booking_id,)
        ).fetchone()
        if not booking:
            print(f"MASTER | Check-in failed: Booking {booking_id} not found or not 'Booked'")
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
            print(f"MASTER | Booking {booking_id} status updated to 'checked in'")

            # Publish MQTT message to room
            mqtt_payload = {
                "op": "CHECK_IN",
                "room_id": booking["room_id"],
                "booking_id": booking_id,
                "token": booking["token"]
            }
            self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{booking['room_id']}/command", json.dumps(mqtt_payload))
            print(f"MASTER | Published CHECK_IN MQTT for room {booking['room_id']}")

            return {
                "op": "LOG", "action": "check in", "type": "success",
                "message": "Check-in successful", "booking_id": booking_id
            }   
    def check_out(self, request: dict):
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

            # Publish MQTT message to room
            mqtt_payload = {
                "op": "CHECK_OUT",
                "room_id": booking["room_id"],
                "booking_id": booking_id,
                "token": booking["token"]
            }
            self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{booking['room_id']}/command", json.dumps(mqtt_payload))

            return {
                "op": "LOG", "action": "check out", "type": "success",
                "message": "Check-out successful", "booking_id": booking_id
            }

    def cancel_booking(self, request: dict):
        print("Entering cancel_booking with request:", request)
        booking_id = request["booking_id"]
        token = request["token"]
        print(booking_id, token)
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

            # Publish MQTT message to room
            mqtt_payload = {
                "op": "CANCEL_BOOKING",
                "room_id": booking["room_id"],
                "booking_id": booking_id,
                "token": token
            }
            self.mqtt_client.publish(config.TOPIC_ROOM_COMMAND_PREFIX + f"{booking['room_id']}/command", json.dumps(mqtt_payload))

            return {
                "op": "LOG", "action": "cancel booking", "type": "success",
                "message": "Booking cancelled successfully", "booking_id": booking_id
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
            elif request["op"] == "BOOK_ROOM":
                response = self.book_room(request)
            elif request["op"] == "CHECK_IN":
                response = self.check_in(request)
            elif request["op"] == "CHECK_OUT":
                response = self.check_out(request)
            elif request["op"] == "CANCEL_BOOKING":
                response = self.cancel_booking(request)
            elif request["op"] == "LOG":
                print(request["action"])
                if request["type"] == "success" and request["action"] == "booking":
                    response = self.book_room(request)
                elif request["type"] == "success" and request["action"] == "check in":
                    response  = self.check_in(request)
                elif request["type"] == "success" and request["action"] == "check out":
                    response = self.check_out(request)
                elif request["type"] == "success" and request["action"] == "cancel booking":
                    response = self.cancel_booking(request)
                else:
                    response = request
            elif request["op"] == "GET_BOOKINGS":
                response = self.get_bookings(request["token"])
            elif request["op"] == "GET_ROOMS":
                rooms_data = self.get_room_inf()
                response = {"op": "GET_ROOMS", "type": "success", "rooms": rooms_data}
            else:
                response = {
                    "op": request.get("op"),
                    "type": "failure",
                    "reason": "Unknown operation"
                }
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
