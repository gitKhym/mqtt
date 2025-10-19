import sqlite3
import time
import datetime
from models.user import User
from models.room import Room
from models.booking import Booking
from models.sensor_data import SensorData

class Database:
    def __init__(self, db_file):
        self.conn = self.create_connection(db_file)

    def create_connection(self, db_file):
        conn = sqlite3.connect(db_file, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create_table(self, create_table_sql):
        cur = self.conn.cursor()
        cur.execute(create_table_sql)

    def close(self):
        if self.conn:
            self.conn.close()

    def create_user(self, user: User):
        sql = '''INSERT INTO users(email,password,full_name,user_id,user_token,role)
                  VALUES(?,?,?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (user.email, user.password, user.full_name, user.user_id, user.user_token, user.role))
        self.conn.commit()
        return cur.lastrowid

    def create_room(self, room: Room):
        sql = '''INSERT INTO rooms(room_name, location, capacity, status)
                  VALUES(?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (room.room_name, room.location, room.capacity, room.status))
        self.conn.commit()
        return cur.lastrowid

    def create_booking(self, booking: Booking):
        sql = '''INSERT INTO bookings(user_id,room_id,start_time,end_time,token)
                  VALUES(?,?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (booking.user_id, booking.room_id, booking.start_time, booking.end_time, booking.token))
        self.conn.commit()
        return cur.lastrowid

    def create_sensor_data(self, sensor_data: SensorData):
        sql = '''INSERT INTO sensor_data(room_id,timestamp,temperature,humidity,pressure)
                  VALUES(?,?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (sensor_data.room_id, sensor_data.timestamp, sensor_data.temperature, sensor_data.humidity, sensor_data.pressure))
        self.conn.commit()
        return cur.lastrowid

    def create_log(self, user_id, action, details):
        sql = '''INSERT INTO logs(user_id,action,timestamp,details)
                  VALUES(?,?,?,?)'''
        cur = self.conn.cursor()
        now = datetime.datetime.fromtimestamp(time.time())
        cur.execute(sql, (user_id, action, now, details))
        self.conn.commit()
        return cur.lastrowid

    def create_all_tables(self):
        sql_create_users_table = """CREATE TABLE IF NOT EXISTS users (
                                            id integer PRIMARY KEY autoincrement,
                                            email text NOT NULL UNIQUE,
                                            password text NOT NULL,
                                            full_name text NOT NULL,
                                            user_id text NOT NULL UNIQUE,
                                            user_token VARCHAR(50) NOT NULL,
                                            role text NOT NULL
                                        );"""

        sql_create_rooms_table = """CREATE TABLE IF NOT EXISTS rooms (
                                        id integer PRIMARY KEY autoincrement,
                                        room_name text NOT NULL UNIQUE,
                                        location text,
                                        capacity integer,
                                        status text NOT NULL
                                    );"""

        sql_create_bookings_table = """CREATE TABLE IF NOT EXISTS bookings (
                                        id integer PRIMARY KEY autoincrement,
                                        user_id integer NOT NULL,
                                        room_id integer NOT NULL,
                                        start_time datetime NOT NULL,
                                        end_time datetime NOT NULL,
                                        token text NOT NULL,
                                        status text DEFAULT 'Booked',
                                        FOREIGN KEY (user_id) REFERENCES users (id),
                                        FOREIGN KEY (room_id) REFERENCES rooms (id)
                                    );"""

        sql_create_sensor_data_table = """CREATE TABLE IF NOT EXISTS sensor_data (
                                            id integer PRIMARY KEY  autoincrement,
                                            room_id integer NOT NULL,
                                            timestamp datetime NOT NULL,
                                            temperature real NOT NULL,
                                            humidity real NOT NULL,
                                            pressure real NOT NULL,
                                            FOREIGN KEY (room_id) REFERENCES rooms (id)
                                        );"""

        sql_create_logs_table = """CREATE TABLE IF NOT EXISTS logs (
                                        id integer PRIMARY KEY autoincrement,
                                        user_id integer,
                                        action text NOT NULL,
                                        timestamp datetime NOT NULL,
                                        details text,
                                        FOREIGN KEY (user_id) REFERENCES users (id)
                                    );"""

        sql_create_announcements_table = """CREATE TABLE IF NOT EXISTS announcements (
                                            id integer PRIMARY KEY autoincrement,
                                            admin_id integer NOT NULL,
                                            message text NOT NULL,
                                            timestamp datetime NOT NULL,
                                            target_audience text NOT NULL,
                                            FOREIGN KEY (admin_id) REFERENCES users (id)
                                        );"""

        if self.conn is not None:
            self.create_table(sql_create_users_table)
            self.create_table(sql_create_rooms_table)
            self.create_table(sql_create_bookings_table)
            self.create_table(sql_create_sensor_data_table)
            self.create_table(sql_create_logs_table)
            self.create_table(sql_create_announcements_table)


def seed_data(db: Database):
    # Clear existing data
    db.conn.execute("DELETE FROM users")
    db.conn.execute("DELETE FROM rooms")
    db.conn.execute("DELETE FROM bookings")
    db.conn.execute("DELETE FROM sensor_data")
    db.conn.execute("DELETE FROM logs")
    db.conn.commit()

    # Seed users
    db.create_user(User('admin@test.com', 'admin', 'Admin', '100', 'admin', 'admin'))
    db.create_user(User('security@test.com', 'security', 'Security', '200', 'security', 'security'))
    db.create_user(User('student1@test.com', 'student', 'Smith', 's1234567', 'user'))
    db.create_user(User('student2@test.com', 'student', 'John', 's1111111', 'user'))

    # Seed rooms
    # db.create_room(Room('Science Room', 'Building 52', 20, 'Available'))
    # db.create_room(Room('Art Room', 'Building 90', 25, 'Available'))
    db.conn.commit()

def main():
    database = r"database.db"
    db = Database(database)
    db.create_all_tables()
    seed_data(db)
    db.close()

if __name__ == '__main__':
    main()
