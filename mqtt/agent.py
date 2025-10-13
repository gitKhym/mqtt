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

class Agent:
    def __init__(self):
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.running = True
        self.mqtt_subscriber_thread = None
        self.socket_client_thread = None

    def _on_mqtt_connect(self, client: Client, userdata: Any, flags: ConnectFlags, rc: ReasonCode, properties: Optional[Properties]) -> None:
        if rc == 0:
            print(f"MQTT | Agent connected to MQTT")
            client.subscribe(config.TOPIC_ALL)
            print(f"MQTT | Agent subscribed to topic: {config.TOPIC_ALL}")
        else:
            print(f"MQTT | Agent failed to connect to MQTT")

    def _on_mqtt_message(self, client: Client, userdata: Any, msg: MQTTMessage):
        # TODO: Process incoming MQTT messages here
        pass

    def _mqtt_subscriber_thread(self):
        try:
            self.mqtt_client.connect(config.MQTT_IP, config.MQTT_PORT, 60)
            self.mqtt_client.loop_forever()
        except Exception as e:
            print(f"MQTT | Error in MQTT subscriber thread: {e}")
        finally:
            self.mqtt_client.disconnect()
            print("MQTT | Agent MQTT subscriber stopped.")

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

        self.mqtt_subscriber_thread.daemon = True
        self.socket_client_thread.daemon = True

        self.mqtt_subscriber_thread.start()
        self.socket_client_thread.start()
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
