import os

# MQTT Configuration
SOCKET_HOST = "192.168.1.128"
MQTT_PORT = 1883
TOPIC_ALL = "classroom/all"
TOPIC_SECURITY = "classroom/security"
TOPIC_BOOKING_REQUEST = "classroom/bookings/requests"
TOPIC_BOOKING_RESPONSE = "classroom/bookings/responses"

# Socket Configuration
SOCKET_HOST = "192.168.1.128"
SOCKET_PORT = 12345

# TODO: Database Configuration 
DB_HOST = "localhost"
DB_USER = "user"
DB_PASSWORD = "password"
DB_NAME = "classroom_db"

# Log file
LOG_FILE = os.path.join(os.path.dirname(__file__), "master_pi", "master.log")
