from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
import socket
from sense_hat import SenseHat
import time
import config
import json
import sys
from collections import OrderedDict
import traceback

from paho.mqtt.client import Client, MQTTMessage, ConnectFlags
from paho.mqtt.properties import Properties
import paho.mqtt.client as mqtt
from paho.mqtt.reasoncodes import ReasonCode
from typing import Any, Optional
import threading

class RoomPi:
    STATUS = ["Available", "Occupied", "Maintenance", "Fault"]
    COLORS = [(0,255,0), (255,255,0), (255,165,0), (255,0,0)]

    def __init__(self):
        self.current = self.STATUS[0]
        self.next_user_token = None
        self.environment_thread = None
        self.id  = None
        self.socket_users = None
        self.sense = SenseHat()
        self.running = True
        self.bookings = []
        self.registration_payload = None

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_subscriber_thread = None

    def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode, properties: Optional[Properties]) -> None:
        if rc == 0:
            print(f"MQTT | Room {self.id} connected to MQTT")
            client.subscribe(config.TOPIC_ROOM_COMMAND_PREFIX + f"{self.id}/command")
            print(f"MQTT | Room {self.id} subscribed to topic: {config.TOPIC_ROOM_COMMAND_PREFIX}{self.id}/command")
            
            # Publish registration message after successful connection
            if self.registration_payload:
                client.publish(config.TOPIC_ROOM_REGISTER, json.dumps(self.registration_payload))
                print(f"MQTT | Room {self.id} published registration: {self.registration_payload}")
        else:
            print(f"MQTT | Room {self.id} failed to connect to MQTT")

    def _on_mqtt_message(self, client: Client, userdata: Any, msg: MQTTMessage):
        # Expected topic format: rooms/<room_id>/command
        topic_parts = msg.topic.split('/')
        if len(topic_parts) == 3 and topic_parts[0] == 'rooms' and topic_parts[2] == 'command':
            room_id = topic_parts[1]
            try:
                payload = json.loads(msg.payload.decode())
                op = payload.get("op")
                token = payload.get("token")
                booking_id = payload.get("booking_id")

                if op == "BOOK_ROOM":
                    starttime = datetime.fromisoformat(payload.get("starttime"))
                    endtime = datetime.fromisoformat(payload.get("endtime"))
                    booking_entry = {"starttime": starttime, "endtime": endtime, "token": token}
                    self.insert_booking(booking_entry)
                    print(f"MQTT | Room {self.id} received BOOK_ROOM command: {payload}")
                elif op == "CANCEL_BOOKING":
                    starttime = datetime.fromisoformat(payload.get("starttime"))
                    for b in self.bookings:
                        if b['starttime'] == starttime and b["token"] == token:
                            self.bookings.remove(b)
                            print(f"MQTT | Room {self.id} received CANCEL_BOOKING command: {payload}")
                            break
                elif op == "CHECK_IN":
                    self.current = self.STATUS[1]  # In Use
                    self.next_user_token = token
                    self.update_leds()
                    print(f"MQTT | Room {self.id} received CHECK_IN command: {payload}")
                elif op == "CHECK_OUT":
                    self.current = self.STATUS[0]  # Available
                    self.next_user_token = None
                    self.update_leds()
                    # Remove the booking that was checked out
                    for b in self.bookings:
                        if b["token"] == token:
                            self.bookings.remove(b)
                            break
                    print(f"MQTT | Room {self.id} received CHECK_OUT command: {payload}")
                elif op == "UPDATE_STATUS": # Add this block
                    new_status = payload.get("status")
                    print(f"ROOM {self.id} | Received UPDATE_STATUS command with new_status: {new_status}") # Add this
                    if new_status in self.STATUS:
                        self.current = new_status
                        self.update_leds()
                        print(f"ROOM {self.id} | Status updated to {new_status} via MQTT: {payload}")
                    else:
                        print(f"ROOM {self.id} | Received invalid status: {new_status}")
            except Exception as e:
                print(f"MQTT | Error processing command for room {room_id}: {e}")
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
            print(f"MQTT | Room {self.id} MQTT subscriber stopped.")

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't need to exist — forces use of active interface
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def update_leds(self):
        color = self.COLORS[self.STATUS.index(self.current)]
        try:
            self.sense.clear(color)
        except Exception:
            # In case sense hat isn't available (e.g., during testing), ignore errors.
            pass

    def insert_booking(self, booking: dict):
        """
        Insert booking (with datetime objects) keeping bookings ordered by starttime.
        Booking dict expected: {"starttime": datetime, "endtime": datetime, "token": str}
        """
        for b in self.bookings:
            if booking["starttime"] < b["starttime"]:
                self.bookings.insert(self.bookings.index(b), booking)
                return
        self.bookings.append(booking)
            

    def environment_readings(self):
        """
        Runs in its own thread. Sends environment data regularly.
        Thread catches exceptions to avoid silent crash.
        """
        while self.running:
            try:
                # SenseHat reads; may raise in some environments
                try:
                    temperature = self.sense.get_temperature()
                    humidity = self.sense.get_humidity()
                    pressure = self.sense.get_pressure()
                except Exception:
                    # fallback values if sensing fails
                    temperature = None
                    humidity = None
                    pressure = None

                timestamp = time.time()
                # update LEDs from current state
                try:
                    self.update_leds()
                except Exception:
                    pass

                status = self.current
                room_id = self.id

                # Publish MQTT message with sensor data
                mqtt_payload = {
                    "op": "SENSOR_DATA",
                    "room_id": room_id,
                    "timestamp": datetime.now().isoformat(), # Use ISO format
                    "temperature": temperature,
                    "humidity": humidity,
                    "pressure": pressure,
                    "status": status
                }
                self.mqtt_client.publish(config.TOPIC_ROOM_SENSOR_DATA_PREFIX + f"{room_id}/status", json.dumps(mqtt_payload))
            except Exception:
                print("environment_readings exception:", traceback.format_exc())
            # Sleep but allow quicker shutdown by sleeping in short increments
            sleep_total = 10
            slept = 0
            while self.running and slept < sleep_total:
                time.sleep(0.5)
                slept += 0.5


    def cancel_booking(self, msg: dict):
        try:
            booking_id = msg["booking_id"]
            starttime = msg["starttime"]
            token = msg["token"]
            starttime_dt = datetime.fromisoformat(starttime)
            print(booking_id, starttime_dt, token)
        except KeyError as e:
            return {"op": "LOG", "action": "cancel booking", "room_id": self.id,
                    "type": "failure", "reason": f"Missing field: {e}"}
        except ValueError as e:
            return {"op": "LOG", "action": "cancel booking", "room_id": self.id,
                    "type": "failure", "reason": f"Invalid starttime format: {e}"}

        for b in self.bookings:
            if b['starttime'] == starttime_dt and b["token"] == token:
                self.bookings.remove(b)
                return {"op": "LOG", "action": "cancel booking", "room_id": self.id, "token": token,
                        "type": "success", "booking_id": booking_id}

        return {"op": "LOG", "action": "cancel booking", "room_id": self.id,
                "type": "failure", "reason": "Booking not found or invalid token"}


    def book_room(self, msg: dict):
        """
        msg expects:
        {
            "op":"BOOK_ROOM",
            "starttime":"2025-10-15T19:00:00",
            "duration":3600,
            "token":"abc"
        }
        """
        try:
            starttime = datetime.fromisoformat(msg["starttime"])
            duration_sec = int(msg["duration"])
            endtime = starttime + timedelta(seconds=duration_sec)
            token = msg["token"]
            print(starttime, endtime)
        except Exception as e:
            return {"op": "LOG", "action": "booking", "room_id": self.id,
                    "type": "failure", "reason": f"bad payload: {e}"}

        now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)
        if starttime < now:
            return {"op": "LOG", "action": "booking", "room_id": self.id,
                    "type": "failure", "reason": "Cannot book for past time"}

        # Check for overlap
        
        for b in self.bookings:
            print(b["starttime"], b["endtime"])
            if starttime < b["endtime"] and endtime > b["starttime"]:
                return {"op": "LOG", "action": "booking", "room_id": self.id,
                        "type": "failure", "reason": "Time slot already booked"}

        booking_entry = {"starttime": starttime, "endtime": endtime, "token": token}
        self.insert_booking(booking_entry)

        return {"op": "LOG", "action": "booking", "type": "success", "room_id": self.id,
                "starttime": starttime.isoformat(), "endtime": endtime.isoformat(), "token": token}

    def check_in(self, msg: dict):
        token = msg.get("token")
        now = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)
        print("Check in attempt:", token, now)
        for b in self.bookings:
            starttime = datetime.fromisoformat(b["starttime"].isoformat())
            endtime = datetime.fromisoformat(b["endtime"].isoformat())
            print(starttime, endtime, token, b["token"])
            if b["token"] == token and starttime < now and endtime > now:
                self.current = self.STATUS[1]  # In Use
                self.next_user_token = token
                self.update_leds()
                return {"op": "LOG", "action": "check in", "room_id": self.id, "type": "success", "booking_id": msg.get("booking_id"), "token": token}
        return {"op": "LOG", "action": "check in", "room_id": self.id,
                "type": "failure", "reason": "Invalid token or not within booking time"}

    def check_out(self, msg: dict):
        token = msg.get("token")
        # Must be the same user currently checked in
        if token == self.next_user_token:
            self.current = self.STATUS[0]  # Available
            self.next_user_token = None
            self.update_leds()

            # Find and remove only the first (next) booking with this token
            for b in self.bookings:
                if b["token"] == token:
                    self.bookings.remove(b)
                    break  # remove only one booking

            return {"op": "LOG", "action": "check out", "room_id": self.id, "type": "success", "booking_id": msg.get("booking_id"), "token": token}

        # If we reach here, conditions failed
        return {
            "op": "LOG",
            "action": "check out",
            "room_id": self.id,
            "type": "failure",
            "reason": "Invalid token or not checked in"
    }


    def handle_user(self, sc: socket.socket):
        """
        Each connection is handled on its own thread.
        This function tries to recv JSON once (with a timeout) and respond.
        """
        try:
            sc.settimeout(5.0)
            data = b""
            try:
                chunk = sc.recv(4096)
                if chunk:
                    data += chunk
            except socket.timeout:
                # no data in time -> close
                sc.close()
                return
            if not data:
                sc.close()
                return
            try:
                req = json.loads(data.decode())
            except Exception:
                # Bad JSON
                resp = {"op": "LOG", "action": "request", "type": "failure", "reason": "Invalid JSON"}
                sc.sendall(json.dumps(resp).encode())
                sc.close()
                return
            print(req)
            msg_dic = {}
            op = req.get("op")
            if op == "BOOK_ROOM":
                msg_dic = self.book_room(req)

            elif op == "CANCEL_BOOKING":
                msg_dic = self.cancel_booking(req)
            elif op == "CHECK_IN":
                msg_dic = self.check_in(req)
            elif op == "CHECK_OUT":
                msg_dic = self.check_out(req)
            else:
                msg_dic = {"op": "LOG", "action": "request", "type": "failure", "reason": "Unknown op"}

            # Directly send response back to client
            try:
                sc.sendall(json.dumps(msg_dic).encode())
            except Exception:
                pass
        except Exception:
            print("handle_user exception:", traceback.format_exc())
        finally:
            try:
                sc.close()
            except Exception:
                pass

    def room_management(self):
        '''
        Acts like a server that listens to user requests host = ip, port = 10000 + room_id
        The accept loop is non-blocking (with timeout) so we can shutdown cleanly.
        '''
        ip = self.get_local_ip()
        port = 10000 + self.id

        self.socket_users = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_users.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_users.bind((ip, port))
        self.socket_users.listen(5)
        # set timeout so accept() wakes periodically and checks self.running
        self.socket_users.settimeout(1.0)

        try:
            while self.running:
                try:
                    sc, client_addr = self.socket_users.accept()
                    client_thread = threading.Thread(target=self.handle_user, args=(sc,))
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    # loop again to check running flag
                    continue
                except Exception:
                    print("room_management accept exception:", traceback.format_exc())
                    continue
        finally:
            try:
                self.socket_users.close()
            except Exception:
                pass

    def initialization(self, id, room_name, location, capacity):
        """
        Initialize the room and start threads. (note: renamed from initailization)
        """
        self.id = int(id)
        print("Starting room pi service")
        ip = self.get_local_ip()
        port = 10000 + self.id
        self.registration_payload = {
            "op": "ACTIVATED_ROOM",
            "room_name": room_name,
            "status": self.current,
            "room_id": self.id,
            "ip": ip,
            "port": port,
            "location": location,
            "capacity": capacity
        }
        # The master will send booking updates via MQTT to rooms/<room_id>/command

        print(self.bookings)
        self.environment_thread = threading.Thread(target=self.environment_readings)
        self.environment_thread.daemon = True
        self.environment_thread.start()

        self.mqtt_subscriber_thread = threading.Thread(target=self._mqtt_subscriber_thread)
        self.mqtt_subscriber_thread.daemon = True
        self.mqtt_subscriber_thread.start()

        # start room management (this will block until stopped)
        try:
            self.room_management()
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.running = False

    def stop(self):
        """
        Clean shutdown helper. Sets running False and closes listening socket.
        """
        self.running = False
        try:
            if self.socket_users:
                self.socket_users.close()
        except Exception:
            pass
        self.mqtt_client.disconnect()

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python3 room.py <room_id> \"<room_name>\" \"<location>\" <capacity>")
        sys.exit(1)
    rp = RoomPi()
    rp.initialization(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
