import sys
import os

# Add project root to sys.path for relative imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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


class Master:
    def __init__(self):
        self.mqtt_client = mqtt.Client()
        self.running = True
        self.socket_server_thread = None
        self.mqtt_publisher_thread = None

        DB_FILE = os.path.join(os.path.dirname(__file__), '..', 'database.db')
        self.db = Database(DB_FILE)


    def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode , properties: Optional[Properties]) -> None:
        pass

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
            return "Unknown command"

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        ip = addr[0]
        port = addr[1]
        address = f"{ip}:{port}"

        with conn:
            while self.running:
                try:
                    conn.settimeout(1.0) 
                    data = conn.recv(1024)
                    if not data:
                        break
                    message = data.decode().strip()
                    
                    response = self._process_command(message)
                    conn.sendall(response.encode())
                except Exception as e:
                    response = f"Error: {e}"
                    conn.sendall(response.encode())
                    break

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

    def _mqtt_publisher_thread(self):
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

    def start(self):
        self.socket_server_thread = threading.Thread(target=self._socket_server_thread)
        self.mqtt_publisher_thread = threading.Thread(target=self._mqtt_publisher_thread)

        self.socket_server_thread.daemon = True
        self.mqtt_publisher_thread.daemon = True

        self.socket_server_thread.start()
        self.mqtt_publisher_thread.start()

        while self.running:
            time.sleep(1)
        self.stop()

    def stop(self):
        self.running = False

if __name__ == "__main__":
    master = Master()
    master.start()
