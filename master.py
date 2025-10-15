from datetime import datetime
import sys
import os
from database import Database
from models.user import User
from models.room import Room
from models.booking import Booking

# Add project root to sys.path for relative imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import json
import hashlib
import threading
import binascii
import paho.mqtt.client as mqtt
import time
import config
from typing import Optional, Tuple, Any
from paho.mqtt.client import Client, ConnectFlags, MQTTMessage
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode



class Master:
    def __init__(self):
        #self.mqtt_client = mqtt.Client()
        self.running = True
        self.socket_server_thread = None
        #self.mqtt_publisher_thread = None
        self.active_rooms = {}

        DB_FILE = os.path.join('database.db')
        self.db = Database(DB_FILE)


    '''def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode , properties: Optional[Properties]) -> None:
        pass

    def _on_mqtt_message(self, client: Client, userdata: Any, msg: MQTTMessage) -> None:
        pass'''

    '''def _process_command(self, message: str) -> str:
        parts = message.split("|")
        command = parts[0] if parts else None

        # Registration
        if command == "REGISTER":
            if len(parts) == 5:
                _, email, password, full_name, unique_id = parts
                new_user = User(email=email, password=password, full_name=full_name, user_id=unique_id, role='user')
                try:
                    self.db.create_user(new_user)
                    return "Registration_success"
                except Exception as e:
                    return f"Registration_failed: {e}"
            else:
                return "Registration_failed: Invalid format"

        # Login
        elif command == "LOGIN":
            if len(parts) == 3:
                _, email, password = parts
                try:
                    user_data = self.db.conn.execute(
                        "SELECT * FROM users WHERE email=? AND password=?",
                        (email, password)
                    ).fetchone()

                    if user_data:
                        return (
                            f"login_success|"
                            f"role={user_data['role']}|"
                            f"user_id={user_data['user_id']}|"
                            f"full_name={user_data['full_name']}"
                        )
                    else:
                        return "Login Failed: Wrong credentials"
                except Exception as e:
                    return f"Login Failed: {e}"
            else:
                return "Login Failed: Invalid format"

        else:
            return "Unknown command"'''

    def register_user(self, request: dict):
        full_name=request["Full_Name"]
        password=request["Password"]
        pw_hash= hashlib.sha256(password.encode()).hexdigest()
        email=request["Email"]
        unique_id=request["Unique_ID"]
        token = str(binascii.hexlify(os.urandom(20)).decode())
        role = "user"
        print(f"Registering user: {email}, {full_name}, {unique_id}")
        user = User(email=email, password=pw_hash, full_name=full_name, user_id=unique_id, user_token=token, role=role)
        try:
            userId = self.db.create_user(user)
            print(f"User {email} registered with ID {userId}")
            return {"op":"LOG", "action" : "register", "type": "success", "message": "Registration successful", "user_token": token, "user_id": userId, "rooms": self.active_rooms}
        except Exception as e:
            print(f"Error registering user {email}: {e}")
            return {"op":"LOG", "action" : "register","type": "failure","user_id": unique_id ,"reason": f"Registration failed: {e}"}
        
    def login_user(self, request: dict):
        email=request["Email"]
        password=request["Password"]
        pw_hash= hashlib.sha256(password.encode()).hexdigest()
        try:
            user_data = self.db.conn.execute(
                "SELECT * FROM users WHERE email=? AND password=?",
                (email, pw_hash)
            ).fetchone()

            if user_data:
                print(self.active_rooms)
                return {
                    "op":"LOG", "action" : "log in",
                    "type": "success", 
                    "full_name": user_data["full_name"],
                    "user_token": user_data["user_token"],
                    "user_id": user_data["id"],
                    "role": user_data["role"],
                    "rooms": self.active_rooms
                }
            else:
                return {"op":"LOG", "action" : "log in", "type": "failure", "reason": "Login failed: Wrong credentials"}
        except Exception as e:
            return {"op":"LOG", "action" : "log in", "type": "failure", "reason": f"Login failed: {e}"}

    def activated_room(self, request: dict):
        room_id = request["room_id"]
        room_name = request["room_name"]
        room_ip = request["ip"]
        room_port = request["port"]
        try:
            bookings_list = {}
            room_data = self.db.conn.execute(
                "SELECT * FROM rooms WHERE id=?",
                (room_id,)
            ).fetchone()
            if not room_data:
                new_room = Room(id=room_id, room_name=room_name, location="", capacity=0, status="Available")
                self.db.create_room(new_room)
            else:
                room_bookings = self.db.conn.execute(
                    "SELECT * FROM bookings WHERE room_id=?",
                    (room_id,)
                ).fetchall()
                for booking in room_bookings:
                    bookings_list[f"booking_{booking['start_time']}"] = {"start_time": booking["start_time"], "end_time": booking["end_time"], "token": booking["token"]}
            self.active_rooms[room_id] = {
                "room_name": room_name,
                "ip": room_ip,
                "port": room_port,
                "status": request["status"]
            }
            return {"op":"LOG", "action" : "room connection", "type": "success", "bookings": bookings_list, "room id": room_id}
        except Exception as e:
            return {"op":"LOG", "action" : "room connection", "type": "failure", "reason": f"Room activation failed: {e}"}

    def book_room(self, request: dict):
        user_id = self.db.conn.execute(
            "SELECT id FROM users WHERE user_token=?",
            (request["token"],)
        ).fetchone()["id"]
        room_id = request["room_id"]
        start_time = request["starttime"]
        end_time = request["endtime"]
        token = request["token"]
        booking = Booking(user_id=user_id, room_id=room_id, start_time=start_time, end_time=end_time, token=token)
        try:
            booking_id = self.db.create_booking(booking)
            return {"op":"LOG", "action" : "booking", "type": "success", "message": "Booking successful", "booking_id": booking_id}
        except Exception as e:
            return {"op":"LOG", "action" : "booking","type": "failure","room_id": room_id ,"reason": f"Booking failed: {e}"}

    def log_create(self, log):
        if log["op"] == "LOG":
            if log["type"]=="success":
                msg = ""
                if log["action"]=="register":
                    msg = f"User {log['user_id']} registered successfully."
                    self.db.create_log(log["user_id"], "register", msg)
                elif log["action"]=="log in":
                    msg = f"User {log['user_id']} logged in successfully."
                    self.db.create_log(log["user_id"], "log in", msg)
                elif log["action"]=="room connection":
                    msg = f"Room {log['room id']} connected successfully."
                    self.db.create_log(None, "room connection", msg)
                elif log["action"]=="check in":
                    msg = f"User checked in to room {log['room_id']} successfully."
                    self.db.create_log(None, "check in", msg)
                elif log["action"]=="check out":
                    msg = f"User checked out of room {log['room_id']} successfully."
                    self.db.create_log(None, "check out", msg)
                elif log["action"]=="booking":
                    msg = f"Room {log['room_id']} booked successfully from {log['starttime']} to {log['endtime']}."
                    self.db.create_log(None, "booking", msg)
            elif log["type"]=="failure":   
                self.db.create_log(None, log["action"], log["reason"])
            # Add more actions as needed 

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        

        request_dict = conn.recv(1024).decode()
        request = json.loads(request_dict)
        print(request["op"])
        if request["op"] == "REGISTER":
            print("register")
            response = self.register_user(request)
        elif request["op"] == "LOGIN":
            response = self.login_user(request)
        elif request["op"] == "ACTIVATED_ROOM":
            response = self.activated_room(request)
        elif request["op"] == "LOG":
            if request["type"] == "success" and request["action"] == "booking":
                response = self.book_room(request)
            else:
                response = request
        elif request["op"] == "SENSOR_DATA":
            room_id = request["room_id"]
            temperature = request["temperature"]
            humidity = request["humidity"]
            pressure = request["pressure"]
            status = request["status"]
            timestamp = datetime.fromtimestamp(request["timestamp"])
            self.active_rooms[room_id]["status"] = status

            # Update latest values in rooms table
            self.db.conn.execute(
                "UPDATE rooms SET status = ? WHERE id=?",
                (status, room_id)
            )
            # Insert historical data into sensor_data table
            self.db.conn.execute(
                "INSERT INTO sensor_data (room_id, timestamp, temperature, humidity, pressure) VALUES (?, ?, ?, ?, ?)",
                (room_id, timestamp, temperature, humidity, pressure)
            )
            self.db.conn.commit()
            response = {
                "op": "LOG",
                "action": "sensor_update",
                "type": "success",
                "room_id": room_id
            }
        else:
            response = {"op": request.get("op"), "type": "failure", "reason": "Unknown operation"}
        self.log_create(response)
        response_str = json.dumps(response)
        conn.sendall(response_str.encode())
        conn.close()


    def _socket_server_thread(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((config.SOCKET_HOST, config.SOCKET_PORT))
            s.listen()

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
                        pass

    '''def _mqtt_publisher_thread(self):
        try:
            self.mqtt_client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
            self.mqtt_client.loop_start()

            while self.running:
                time.sleep(1)
        except Exception as e:
            pass
        finally:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        '''
    def start(self):
        self.socket_server_thread = threading.Thread(target=self._socket_server_thread)
        #self.mqtt_publisher_thread = threading.Thread(target=self._mqtt_publisher_thread)

        self.socket_server_thread.daemon = True
        #self.mqtt_publisher_thread.daemon = True

        self.socket_server_thread.start()
        #self.mqtt_publisher_thread.start()

        while self.running:
            time.sleep(1)
        self.stop()

    def stop(self):
        self.running = False

if __name__ == "__main__":
    master = Master()
    master.start()
