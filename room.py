from datetime import datetime, timedelta
import socket
from sense_hat import SenseHat
import time
import config
import threading
import json
import sys
from collections import OrderedDict
import traceback

class RoomPi:
    STATUS = ["Available", "In Use", "Maintenance", "Fault"]
    COLORS = [(0,255,0), (255,255,0), (255,165,0), (255,0,0)]

    def __init__(self):
        self.current = self.STATUS[0]
        self.next_user_token = None
        self.environment_thread = None
        self.id  = None
        self.socket_users = None
        self.sense = SenseHat()
        self.running = True
        # bookings is an OrderedDict keyed by ISO starttime string -> {starttime: datetime, endtime: datetime, token: str}
        self.bookings = []
        # Lock to protect access to bookings/current/next_user_token
        self.lock = threading.RLock()

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

    def master_connect(self, message, timeout=5):
        """
        Send message (dict or JSON string) to master; returns a dict response.
        Handles socket exceptions and returns an error dict on failure.
        """
        try:
            if isinstance(message, dict):
                payload = json.dumps(message)
            else:
                payload = str(message)

            sd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sd.settimeout(timeout)
            try:
                sd.connect((config.SOCKET_HOST, config.SOCKET_PORT))
            except Exception as e:
                return {"type": "failure", "reason": f"connect error: {e}"}
            try:
                sd.sendall(payload.encode())
                data = b""
                # receive until socket closes or timeout
                while True:
                    try:
                        chunk = sd.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    except socket.timeout:
                        break
                if not data:
                    return {"type": "failure", "reason": "no response from master"}
                try:
                    resp = json.loads(data.decode())
                    return resp
                except Exception:
                    # fallback: return raw string in a dict
                    return {"type": "success", "raw": data.decode()}
            finally:
                sd.close()
        except Exception as e:
            return {"type": "failure", "reason": f"master_connect exception: {e}", "trace": traceback.format_exc()}

    def update_leds(self):
        with self.lock:
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
        with self.lock:
            for b in self.bookings:
                if booking["starttime"] < b["starttime"]:
                    self.bookings.insert(self.bookings.index(b), booking)
                    return
            

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

                with self.lock:
                    status = self.current
                    room_id = self.id

                msg_dict = {
                    "op": "SENSOR_DATA",
                    "room_id": room_id,
                    "timestamp": timestamp,
                    "temperature": temperature,
                    "humidity": humidity,
                    "pressure": pressure,
                    "status": status
                }
                resp = self.master_connect(msg_dict)
                # we ignore resp content for now; but log failures
                if resp.get("type") == "failure":
                    print(f"MASTER(SENSOR) | {resp.get('reason')}")
            except Exception:
                print("environment_readings exception:", traceback.format_exc())
            # Sleep but allow quicker shutdown by sleeping in short increments
            sleep_total = 10
            slept = 0
            while self.running and slept < sleep_total:
                time.sleep(0.5)
                slept += 0.5

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

        now = datetime.now()
        if starttime < now:
            return {"op": "LOG", "action": "booking", "room_id": self.id,
                    "type": "failure", "reason": "Cannot book for past time"}

        with self.lock:
            # Check for overlap
            
            for b in self.bookings.values():
                print(b.starttime, b.endtime)
                if not (starttime < b["starttime"] and endtime <= b["starttime"]) or not (starttime >= b["endtime"] and endtime > b["endtime"]):
                    return {"op": "LOG", "action": "booking", "room_id": self.id,
                            "type": "failure", "reason": "Time slot already booked"}

            booking_entry = {"starttime": starttime, "endtime": endtime, "token": token}
            self.insert_booking(booking_entry)

        return {"op": "LOG", "action": "booking", "type": "success", "room_id": self.id,
                "starttime": starttime.isoformat(), "endtime": endtime.isoformat(), "token": token}

    def check_in(self, msg: dict):
        token = msg.get("token")
        now = datetime.now()
        with self.lock:
            for b in self.bookings:
                if b["token"] == token and b["starttime"] <= now < b["endtime"]:
                    self.current = self.STATUS[1]  # In Use
                    self.next_user_token = token
                    self.update_leds()
                    return {"op": "LOG", "action": "check in", "room_id": self.id, "type": "success"}
        return {"op": "LOG", "action": "check in", "room_id": self.id,
                "type": "failure", "reason": "Invalid token or not within booking time"}

    def check_out(self, msg: dict):
        token = msg.get("token")
        with self.lock:
            # Must be the same user currently checked in
            if token == self.next_user_token:
                self.current = self.STATUS[0]  # Available
                self.next_user_token = None
                self.update_leds()

                # Find and remove only the first (next) booking with this token
                for key, b in self.bookings:
                    if b["token"] == token:
                        del self.bookings[key]
                        break  # remove only one booking

                return {"op": "LOG", "action": "check out", "room_id": self.id, "type": "success"}

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

            msg_dic = {}
            op = req.get("op")
            if op == "BOOK_ROOM":
                msg_dic = self.book_room(req)
            elif op == "CHECK_IN":
                msg_dic = self.check_in(req)
            elif op == "CHECK_OUT":
                msg_dic = self.check_out(req)
            else:
                msg_dic = {"op": "LOG", "action": "request", "type": "failure", "reason": "Unknown op"}

            # Send to master and wait for its confirmation
            master_resp = self.master_connect(msg_dic)
            # master_resp is a dict
            if master_resp.get("type") == "success":
                # forward master success back to client
                try:
                    sc.sendall(json.dumps(master_resp).encode())
                except Exception:
                    pass
            else:
                # master failed; still forward the reason (or the msg_dic result) so client knows
                try:
                    sc.sendall(json.dumps(master_resp).encode())
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

    def initialization(self, id):
        """
        Initialize the room and start threads. (note: renamed from initailization)
        """
        self.id = int(id)
        print("Starting room pi service")
        ip = self.get_local_ip()
        port = 10000 + self.id
        msg_dict = {
            "op": "ACTIVATED_ROOM",
            "room_name": f"Room_{self.id}",
            "status": self.current,
            "room_id": self.id,
            "ip": ip,
            "port": port
        }
        resp = self.master_connect(msg_dict)
        # accept that master returns dict; it may include pre-existing bookings
        if resp["type"] == "success":
            bookings = resp["bookings"]
            list_of_bookings = []
            for b in bookings.values():
                try:
                    starttime = datetime.fromisoformat(b["starttime"])
                    endtime = datetime.fromisoformat(b["endtime"])
                    token = b["token"]
                    booking_entry = {"starttime": starttime, "endtime": endtime, "token": token}
                    list_of_bookings.append(booking_entry)
                except Exception:
                    # skip bad entries
                    continue
        # start environment thread
        self.environment_thread = threading.Thread(target=self.environment_readings)
        self.environment_thread.daemon = True
        self.environment_thread.start()

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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 room.py <room_id>")
        sys.exit(1)
    rp = RoomPi()
    rp.initialization(sys.argv[1])
