import sys
import os
import datetime
import random

from paho.mqtt.reasoncodes import ReasonCode
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import socket
import threading
import paho.mqtt.client as mqtt
import time
import config
from typing import Optional, Tuple, Any
from paho.mqtt.client import Client, ConnectFlags, MQTTMessage
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from database import Database
from models.user import User
from models.booking import Booking
from models.room import Room


class Master:
    def __init__(self):
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.running = True
        self.socket_server_thread = None
        self.mqtt_publisher_thread = None

        DB_FILE = os.path.join(os.path.dirname(__file__), '..', 'database.db')
        self.db = Database(DB_FILE)

    def _generate_unique_token(self) -> str:
        while True:
            timestamp_part = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f") # Added microseconds for better uniqueness
            random_part = str(random.randint(10000, 99999)) # Increased range for random part
            token = f"{timestamp_part}-{random_part}"
            
            # Check if token already exists in the database
            cur = self.db.conn.cursor()
            cur.execute("SELECT id FROM bookings WHERE token = ?", (token,))
            if cur.fetchone() is None:
                return token

    def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode , properties: Optional[Properties]) -> None:
        print(f"MQTT | Master connected")

    def _on_mqtt_message(self, client: Client, userdata: Any, msg: MQTTMessage) -> None:
        pass

    def _process_command(self, message: str) -> str:
        parts = message.split("|")
        command = parts[0] if parts else None

        # Registration
        if command == "REGISTER":
            if len(parts) == 5:
                _, email, password, full_name, unique_id = parts
                new_user = User(email=email, password=password, full_name=full_name, user_id=unique_id, role='user')
                try:
                    self.db.create_user(new_user)
                    self.db.create_log(None, "REGISTER", datetime.datetime.now().isoformat(), f"User {email} registered.")
                    return "Registration_success"
                except Exception as e:
                    self.db.create_log(None, "REGISTER_FAILED", datetime.datetime.now().isoformat(), f"User {email} registration failed: {e}")
                    return f"Registration_failed: {e}"
            else:
                return "Registration_failed: Invalid format"

        # Login
        elif command == "LOGIN":
            if len(parts) == 3:
                _, email, password = parts
                print(f"[Master] Received LOGIN request for email: {email}, password: {password}")
                try:
                    user_data = self.db.conn.execute(
                        "SELECT * FROM users WHERE email=? AND password=?",
                        (email, password)
                    ).fetchone()

                    if user_data:
                        print(f"[Master] Login successful for user: {user_data['email']}")
                        self.db.create_log(user_data['id'], "LOGIN", datetime.datetime.now().isoformat(), f"User {email} logged in.")
                        return (
                            f"login_success|"
                            f"role={user_data['role']}|"
                            f"user_id={user_data['id']}|"
                            f"full_name={user_data['full_name']}"
                        )
                    else:
                        self.db.create_log(None, "LOGIN_FAILED", datetime.datetime.now().isoformat(), f"Attempted login for {email} with wrong credentials.")
                        return "Login Failed: Wrong credentials"
                except Exception as e:
                    self.db.create_log(None, "LOGIN_FAILED", datetime.datetime.now().isoformat(), f"Login for {email} failed: {e}")
                    return f"Login Failed: {e}"
            else:
                return "Login Failed: Invalid format"

        # Search Rooms
        elif command == "SEARCH_ROOMS":
            if len(parts) == 3:
                _, start_time_str, end_time_str = parts
                print(f"[Master] Received SEARCH_ROOMS request for start_time: {start_time_str}, end_time: {end_time_str}")
                try:
                    # Convert string times to datetime objects for comparison
                    start_time = datetime.datetime.fromisoformat(start_time_str)
                    end_time = datetime.datetime.fromisoformat(end_time_str)

                    available_rooms = self.db.get_available_rooms(start_time_str, end_time_str)
                    print(f"[Master] Available rooms from DB: {available_rooms}")
                    if available_rooms:
                        room_list = "|".join([f"{room.id},{room.room_name},{room.location},{room.capacity}" for room in available_rooms])
                        return f"SEARCH_ROOMS_SUCCESS|{room_list}"
                    else:
                        return "SEARCH_ROOMS_SUCCESS|No rooms available"
                except Exception as e:
                    self.db.create_log(None, "SEARCH_ROOMS_FAILED", datetime.datetime.now().isoformat(), f"Search rooms failed: {e}")
                    return f"SEARCH_ROOMS_FAILED: {e}"
            else:
                return "SEARCH_ROOMS_FAILED: Invalid format"

        # Book Room
        elif command == "BOOK_ROOM":
            if len(parts) == 5:
                _, user_id_str, room_id_str, start_time_str, end_time_str = parts
                try:
                    user_id = int(user_id_str)
                    room_id = int(room_id_str)
                    start_time = datetime.datetime.fromisoformat(start_time_str)
                    end_time = datetime.datetime.fromisoformat(end_time_str)

                    # Check if room is available
                    if not self.db.get_available_rooms(start_time_str, end_time_str):
                        return "BOOK_ROOM_FAILED: Room not available for the selected time"

                    token = self._generate_unique_token()
                    new_booking = Booking(user_id=user_id, room_id=room_id,
                                          start_time=start_time_str, end_time=end_time_str,
                                          token=token, status='booked', token_used=False)
                    booking_id = self.db.create_booking(new_booking)
                    self.db.create_log(user_id, "BOOK_ROOM", datetime.datetime.now().isoformat(), f"Booking {booking_id} created for room {room_id} by user {user_id}. Token: {token}")
                    return f"BOOK_ROOM_SUCCESS|{booking_id}|{token}"
                except Exception as e:
                    self.db.create_log(user_id, "BOOK_ROOM_FAILED", datetime.datetime.now().isoformat(), f"Booking room failed for user {user_id}: {e}")
                    return f"BOOK_ROOM_FAILED: {e}"
            else:
                return "BOOK_ROOM_FAILED: Invalid format"

        # Cancel Booking
        elif command == "CANCEL_BOOKING":
            if len(parts) == 3:
                _, user_id_str, booking_id_str = parts
                try:
                    user_id = int(user_id_str)
                    booking_id = int(booking_id_str)

                    booking = self.db.get_booking_by_id(booking_id)
                    if not booking or booking.user_id != user_id:
                        return "CANCEL_BOOKING_FAILED: Booking not found or not authorized"

                    if booking.status == 'cancelled':
                        return "CANCEL_BOOKING_FAILED: Booking already cancelled"

                    self.db.update_booking_status(booking_id, 'cancelled')
                    self.db.create_log(user_id, "CANCEL_BOOKING", datetime.datetime.now().isoformat(), f"Booking {booking_id} cancelled by user {user_id}.")
                    return "CANCEL_BOOKING_SUCCESS"
                except Exception as e:
                    self.db.create_log(user_id, "CANCEL_BOOKING_FAILED", datetime.datetime.now().isoformat(), f"Cancel booking {booking_id} failed for user {user_id}: {e}")
                    return f"CANCEL_BOOKING_FAILED: {e}"
            else:
                return "CANCEL_BOOKING_FAILED: Invalid format"

        # Use Room (Token Validation)
        elif command == "USE_ROOM":
            if len(parts) == 2:
                _, token = parts
                try:
                    booking = self.db.get_booking_by_token(token)
                    if not booking:
                        return "USE_ROOM_FAILED: Invalid token"
                    if booking.token_used:
                        return "USE_ROOM_FAILED: Token already used"
                    if booking.status != 'booked':
                        return "USE_ROOM_FAILED: Booking not active"

                    self.db.mark_token_used(booking.id)
                    self.db.update_booking_status(booking.id, 'used')
                    self.db.create_log(booking.user_id, "USE_ROOM", datetime.datetime.now().isoformat(), f"Room {booking.room_id} used with token {token} by user {booking.user_id}.")
                    return f"USE_ROOM_SUCCESS|{booking.room_id}"
                except Exception as e:
                    self.db.create_log(None, "USE_ROOM_FAILED", datetime.datetime.now().isoformat(), f"Use room with token {token} failed: {e}")
                    return f"USE_ROOM_FAILED: {e}"
            else:
                return "USE_ROOM_FAILED: Invalid format"

        # Return Room
        elif command == "RETURN_ROOM":
            if len(parts) == 3:
                _, user_id_str, booking_id_str = parts
                try:
                    user_id = int(user_id_str)
                    booking_id = int(booking_id_str)

                    booking = self.db.get_booking_by_id(booking_id)
                    if not booking or booking.user_id != user_id:
                        return "RETURN_ROOM_FAILED: Booking not found or not authorized"

                    if booking.status != 'used':
                        return "RETURN_ROOM_FAILED: Room not currently in use"

                    self.db.update_booking_status(booking.id, 'returned')
                    self.db.create_log(user_id, "RETURN_ROOM", datetime.datetime.now().isoformat(), f"Room {booking.room_id} returned for booking {booking_id} by user {user_id}.")
                    return "RETURN_ROOM_SUCCESS"
                except Exception as e:
                    self.db.create_log(user_id, "RETURN_ROOM_FAILED", datetime.datetime.now().isoformat(), f"Return room for booking {booking_id} failed for user {user_id}: {e}")
                    return f"RETURN_ROOM_FAILED: {e}"
            else:
                return "RETURN_ROOM_FAILED: Invalid format"

        # Get User Bookings
        elif command == "GET_USER_BOOKINGS":
            if len(parts) == 2:
                _, user_id_str = parts
                try:
                    user_id = int(user_id_str)
                    bookings = self.db.get_user_bookings(user_id)
                    if bookings:
                        booking_list = "|".join([f"{b.id},{self.db.get_room_by_id(b.room_id).room_name},{b.start_time},{b.end_time},{b.token},{b.status},{b.token_used}" for b in bookings])
                        return f"GET_USER_BOOKINGS_SUCCESS|{booking_list}"
                    else:
                        return "GET_USER_BOOKINGS_SUCCESS|No bookings found"
                except Exception as e:
                    self.db.create_log(user_id, "GET_USER_BOOKINGS_FAILED", datetime.datetime.now().isoformat(), f"Failed to get bookings for user {user_id}: {e}")
                    return f"GET_USER_BOOKINGS_FAILED: {e}"
            else:
                return "GET_USER_BOOKINGS_FAILED: Invalid format"

        else:
            return "Unknown command"

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        ip = addr[0]
        port = addr[1]
        address = f"{ip}:{port}"
        print(f"SOCKET | New connection from {address}")

        with conn:
            while self.running:
                try:
                    conn.settimeout(1.0) 
                    data = conn.recv(1024)
                    if not data:
                        break
                    print(f"Data received from {address}: {data.decode()}")
                    conn.sendall(b"Message received by Master")
                except Exception as e:
                    print(f"Error handling {address}: {e}")
                    break
        print(f"{address} Connection closed")

    def _socket_server_thread(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((config.SOCKET_HOST, config.SOCKET_PORT))
            s.listen()
            print(f"Master server listening on {config.SOCKET_HOST}:{config.SOCKET_PORT}")

            s.settimeout(1.0)
            while self.running:
                try:
                    conn, addr = s.accept()
                    thread = threading.Thread(target=self._handle_client, args=(conn, addr))
                    thread.daemon = True
                    thread.start()
                except socket.timeout:
                    continue 
                except Exception as e:
                    if self.running:
                        print(f"Error connecting: {e}")
            print("Master server stopped.")

    def _mqtt_publisher_thread(self):
        try:
            self.mqtt_client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
            self.mqtt_client.loop_start()
            print(f"PUBLISHER | Master publisher connected to {config.MQTT_IP}:{config.MQTT_PORT}")

            while self.running:
                time.sleep(1)
        except Exception as e:
            print(f"PUBLISHER | Error in MQTT publisher thread: {e}")
        finally:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            print("PUBLISHER | Master MQTT publisher stopped.")

    def start(self):
        print("Starting Master services...")
        self.socket_server_thread = threading.Thread(target=self._socket_server_thread)
        self.mqtt_publisher_thread = threading.Thread(target=self._mqtt_publisher_thread)

        self.socket_server_thread.daemon = True
        self.mqtt_publisher_thread.daemon = True

        self.socket_server_thread.start()
        self.mqtt_publisher_thread.start()
        print("Master services started.")

        # Keep main thread alive to allow background threads to run
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping Master...")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        print("Master server services stopped.")

if __name__ == "__main__":
    master = Master()
    master.start()
