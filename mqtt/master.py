import sys
import os

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

class Master:
    def __init__(self):
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.running = True
        self.socket_server_thread = None
        self.mqtt_client_thread = None

    def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode , properties: Optional[Properties]) -> None:
        if rc == 0:
            print(f"MQTT | Master connected")
            client.subscribe(config.TOPIC_BOOKING_REQUEST)
            client.subscribe(config.TOPIC_BOOKING_RESPONSE)
            print(f"MQTT | Master subscribed to topics: {config.TOPIC_BOOKING_REQUEST}, {config.TOPIC_BOOKING_RESPONSE}")
        else:
            print(f"MQTT | Master failed to connect to MQTT")

    def _on_mqtt_message(self, client: Client, userdata: Any, msg: MQTTMessage) -> None:
        print(f"MQTT | Master received message on {msg.topic}: {msg.payload.decode()}")

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

    def _mqtt_client_thread(self):
        try:
            self.mqtt_client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
            self.mqtt_client.loop_start() # Start the MQTT loop in the background
            print(f"MQTT | Master client connected to {config.MQTT_IP}:{config.MQTT_PORT}")

            while self.running:
                time.sleep(1) # Keep the thread alive
        except Exception as e:
            print(f"MQTT | Error in MQTT client thread: {e}")
        finally:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            print("MQTT | Master MQTT client stopped.")

    def start(self):
        print("Starting Master services...")
        self.socket_server_thread = threading.Thread(target=self._socket_server_thread)
        self.mqtt_client_thread = threading.Thread(target=self._mqtt_client_thread)

        self.socket_server_thread.daemon = True
        self.mqtt_client_thread.daemon = True

        self.socket_server_thread.start()
        self.mqtt_client_thread.start()
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
