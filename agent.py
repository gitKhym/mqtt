import sys
import os
from typing import Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paho.mqtt.reasoncodes import ReasonCode
from paho.mqtt.client import Client, MQTTMessage, ConnectFlags
from paho.mqtt.properties import Properties
import socket
import paho.mqtt.client as mqtt
import time
import threading
import config
from sense_hat import SenseHat
import json

class Agent:
    def __init__(self):
        self.sense = SenseHat()
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.running = True
        self.mqtt_subscriber_thread = None
        self.socket_client_thread = None
        self.periodic_status_check_thread = None
        self.rooms = {}  

    def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode, properties: Optional[Properties]) -> None:
        if rc == 0:
            print(f"MQTT | Agent connected to MQTT")
            client.subscribe(config.TOPIC_ALL)
            client.subscribe(f"{config.TOPIC_ROOM_COMMAND_PREFIX}#") # Subscribe to all room command topics
            print(f"MQTT | Agent subscribed to topic: {config.TOPIC_ALL} and {config.TOPIC_ROOM_COMMAND_PREFIX}#")
        else:
            print(f"MQTT | Agent failed to connect to MQTT")

    def _on_mqtt_message(self, client: Client, userdata: Any, msg: MQTTMessage):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            print(f"MQTT | Received message on topic {msg.topic}: {payload}")

            if msg.topic.startswith(config.TOPIC_ROOM_COMMAND_PREFIX):
                print(f"MQTT | Message topic starts with room command prefix: {config.TOPIC_ROOM_COMMAND_PREFIX}")
                room_id = msg.topic.split('/')[-2] # Assuming topic format rooms/<room_id>/command
                print(f"MQTT | Extracted room_id: {room_id}")
                if 'status' in payload:
                    status = payload['status']
                    self.rooms[room_id] = {"status": status} # Update local room status cache
                    print(f"MQTT | Room {room_id} status changed to: {status}")
                    self._check_for_fault_rooms()
                else:
                    print(f"MQTT | Payload does not contain 'status' key.")
            else:
                print(f"MQTT | Message topic {msg.topic} does not start with room command prefix.")
        except json.JSONDecodeError:
            print(f"MQTT | Could not decode JSON from message: {msg.payload}")
        except Exception as e:
            print(f"MQTT | Error processing MQTT message: {e}")

    def _check_for_fault_rooms(self):
        # Check if any room in the local cache is in 'Fault' status
        if any(room["status"] == "Fault" for room in self.rooms.values()):
            self._trigger_fault_warning()
        else:
            self._clear_warning()

    def _trigger_fault_warning(self):
        print("SenseHAT | Triggering fault warning...")
        red = (255, 0, 0)
        off = (0, 0, 0)
        X = red
        O = off
        
        # Red 'X' pattern
        fault_image = [
            X, O, O, O, O, O, O, X,
            O, X, O, O, O, O, X, O,
            O, O, X, O, O, X, O, O,
            O, O, O, X, X, O, O, O,
            O, O, O, X, X, O, O, O,
            O, O, X, O, O, X, O, O,
            O, X, O, O, O, O, X, O,
            X, O, O, O, O, O, O, X
        ]
        
        self.sense.set_pixels(fault_image)
        # Flash the warning
        for _ in range(5): # Flash 5 times
            self.sense.set_pixels(fault_image)
            time.sleep(0.5)
            self.sense.clear()
            time.sleep(0.5)
        self.sense.set_pixels(fault_image) # Leave it on after flashing

    def _clear_warning(self):
        print("SenseHAT | Clearing warning...")
        self.sense.clear() # Clear the Sense HAT display

    def _mqtt_subscriber_thread(self):
        try:
            self.mqtt_client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
            self.mqtt_client.loop_forever()
        except Exception as e:
            print(f"MQTT | Error in MQTT subscriber thread: {e}")
        finally:
            self.mqtt_client.disconnect()
            print("MQTT | Agent MQTT subscriber stopped.")

    def _periodic_status_check_thread(self):
        while self.running:
            time.sleep(10) # Check every 10 seconds
            if not self.running: break
            print("PERIODIC_CHECK | Requesting all room statuses from Master Pi...")
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((config.SOCKET_HOST, config.SOCKET_PORT))
                    message = json.dumps({"op": "GET_ALL_ROOM_STATUSES"})
                    s.sendall(message.encode())
                    
                    total_data = []
                    while True:
                        data = s.recv(4096)
                        if not data:
                            break
                        total_data.append(data.decode())
                    response_str = "".join(total_data)
                    response = json.loads(response_str)

                    if response.get("type") == "success" and "rooms" in response:
                        print(f"PERIODIC_CHECK | Received room statuses: {response['rooms']}")
                        # Update local cache and check for fault rooms
                        for room_id, room_data in response["rooms"].items():
                            self.rooms[room_id] = {"status": room_data["status"]}
                        self._check_for_fault_rooms()
                    else:
                        print(f"PERIODIC_CHECK | Failed to get room statuses: {response.get('reason', 'Unknown error')}")
            except Exception as e:
                print(f"PERIODIC_CHECK | Error during periodic status check: {e}")

    def _socket_client_thread(self):
        # NOTE: Test functionality
        while self.running:
            time.sleep(5)
            if not self.running: break
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.connect((config.SOCKET_HOST, config.SOCKET_PORT))
                    message = "Hello from Agent Pi"
                    s.sendall(message.encode())
                    data = s.recv(1024)
                    print(f"SOCKET | Agent sent: {message}")
                    print(f"SOCKET | Agent received: {data.decode()}")
                except Exception as e:
                    print(f"SOCKET (Agent) | ERROR: {e}")
            time.sleep(5) # Wait before next attempt
        print("Agent server stopped")

    def start(self):
        print("Starting Agent services...")
        self.mqtt_subscriber_thread = threading.Thread(target=self._mqtt_subscriber_thread)
        self.socket_client_thread = threading.Thread(target=self._socket_client_thread)
        self.periodic_status_check_thread = threading.Thread(target=self._periodic_status_check_thread)

        self.mqtt_subscriber_thread.daemon = True
        self.socket_client_thread.daemon = True
        self.periodic_status_check_thread.daemon = True

        self.mqtt_subscriber_thread.start()
        self.socket_client_thread.start()
        self.periodic_status_check_thread.start()
        print("Agent services started.")

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping Agent...")
        finally:
            self.stop()

    def stop(self):
        print("Agent services stopped.")

if __name__ == "__main__":
    agent_pi = Agent()
    agent_pi.start()
