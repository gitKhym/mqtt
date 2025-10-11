from typing import OrderedDict
import socket
from sense_hat import SenseHat
import time
import config 
import threading
import json
import json
import sys
from paho.mqtt.reasoncodes import ReasonCode
from paho.mqtt.client import Client, MQTTMessage, ConnectFlags
from paho.mqtt.properties import Properties

class RoomPi:
    STATUS = ["Available", "In Use", "Maintenance", "Fault"]
    COLORS = [(0,255,0), (255,255,0), (255,165,0), (255,0,0)]

    def __init__(self):
        self.current = self.STATUS[0]
        self.next_user_token = None
        self.enevironment_thread = None
        self.id  = None
        self.socket_users = None 
        self.sense = SenseHat()
        self.running = True
        self.bookings = {}

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No tiene que existir el host, solo fuerza a usar la interfaz activa
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def master_connect(self, message):
        sd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sd.connect((config.SOCKET_HOST, config.SOCKET_PORT))
        except Exception as e:
            print(f"SOCKET (Room) | ERROR: {e}")
            sys.exit(1)
        sd.sendall(message.encode())
        ans = sd.recv(4096).decode
        sd.close()
        return ans

    def update_leds(self):
        color = self.COLORS[self.STATUS.index(self.current)]
        self.sense.clear(color)

    def insert_booking(self, booking):
         # Insert the new booking in the correct position to maintain sorted order by starttime
        inserted = False
        newDict = {}
        for b in self.bookings:
            if not inserted and booking["starttime"] < b["starttime"]:
                bkey = f"booking_{booking['starttime']}"
                newDict[bkey] = booking
                inserted = True
            key = f"booking_{b['starttime']}"
            newDict[key] = b
        if not inserted:
            bkey = f"booking_{booking['starttime']}"
            newDict[bkey] = booking
        self.bookings = newDict

    def environment_readings(self):
        while self.running:
            temperature = self.sense.get_temperature()
            humidity = self.sense.get_humidity()
            pressure = self.sense.get_pressure()
            timestamp = int(time.time())
            self.update_leds()

            msg_dict = {
                "op": "SENSOR_DATA",
                "room_id": self.id,
                "timestamp": timestamp,
                "temperature": temperature,
                "humidity": humidity,
                "pressure": pressure
            }
            msg = json.dumps(msg_dict)
            self.master_connect(msg)
            time.sleep(10)  # Send data every 10 seconds

    def book_room(self, msg):
        '''msg = {
            "op": "BOOK_ROOM",
            "datetime": datetime,
            "duration": duration,
            "token": token
        }'''
        datetime = msg["datetime"]
        duration = msg["duration"]
        token = msg["token"]
        now = time.time()
        if datetime < now:
            return {"op":"LOG", "type": "failure", "reason": "Cannot book for past time"}
        booked = False
        for b in self.bookings.values():
            if not (datetime + duration <= b["starttime"] or datetime >= b["starttime"] + (b["endtime"] - b["datetime"])):
                booked = True
                break
        if booked:
            return {"op":"LOG", "type": "failure", "reason": "Time slot already booked"}
        self.insert_booking({"starttime": datetime, "endtime": datetime + duration, "token": token})
        return {"op":"LOG", "type": "booking-success", "room_id": self.id, "starttime": datetime, "endtime": datetime + duration, "token": token} 

    def check_in(self, msg):
        '''msg = {
            "op": "CHECK_IN",
            "token": token
        }'''
        token = msg["token"]
        now = time.time()
        for b in self.bookings.values:
            if b["token"] == token and b["starttime"] <= now < b["endtime"]:
                self.current = self.STATUS[1]  # Set status to "In Use"
                self.next_user_token = token
                self.update_leds()
                return {"op":"LOG", "type": "check-in-success"}
        return {"op":"LOG",  "type": "failure", "reason": "Invalid token or not within booking time"}

    def check_out(self, msg):
        '''msg = {
            "op": "CHECK_OUT",
            "token": token
        }'''
        token = msg["token"]
        if token == self.next_user_token:
            self.current = self.STATUS[0]  # Set status to "Available"
            self.next_user_token = None
            self.update_leds()
            self.bookings = {b for b in self.bookings.values if b["token"] != token}  # Remove booking
            return {"op":"LOG", "type": "check-out-success"}
        return {"op":"LOG",  "type": "failure", "reason": "Invalid token or not checked in"}
        

    def handle_user(self, sc):
        req = sc.recv(1024).decode()
        req = json.loads(req)
        msg_dic = {}
        if req["op"] == "BOOK_ROOM":
            msg_dic = self.book_room(req)
        elif req["op"] == "CHECK_IN":
            msg_dic = self.check_in(req)
        elif req["op"] == "CHECK_OUT":
            msg_dic = self.check_out(req)
        msg = json.dumps(msg_dic)
        ans = self.master_connect(msg)
          
    def room_management(self):
        '''Acts like a server that listens to user requests host = ip, port = 10000 + room_id'''
        ip = self.get_local_ip()
        port = 10000 + self.id

        self.socket_users = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_users.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_users.bind((ip, port))
        self.socket_users.listen(5)

        while self.running:
            sc, client_addr = self.socket_users.accept()
            client_thread = threading.Thread(target=self.handle_user, args=(sc))
 

    def initailization(self, id):
        self.id = int(id)
        print("Starting room pi service")
        ip = self.get_local_ip()
        port = 10000 + self.id
        msg_dict = {
            "op": "ACTIVATED_ROOM",
            "room_id": self.id,
            "ip": ip,
            "port": port
        }
        msg = json.dumps(msg_dict)
        self.bookings = json.loads(self.master_connect(msg))
        #HERE GOES THE MQTT THREAD

        self.enevironment_thread = threading.Thread(target=self.environment_readings)
        self.enevironment_thread.daemon = True
        self.enevironment_thread.start()

        self.room_management()
        

if __name__ == "__main__":
    rp = RoomPi()
    rp.initailization(sys.argv[1])