import sqlite3
from models.user import User
from models.room import Room
from models.booking import Booking
from models.sensor_data import SensorData
from typing import Optional

class Database:
    def __init__(self, db_file):
        self.conn = self.create_connection(db_file)

    def create_connection(self, db_file):
        conn = sqlite3.connect(db_file, check_same_thread=False)
        return conn

    def create_table(self, create_table_sql):
        cur = self.conn.cursor()
        cur.execute(create_table_sql)

    def close(self):
        if self.conn:
            self.conn.close()

    def create_user(self, user: User):
        sql = '''INSERT INTO users(email,password,full_name,user_id,role)
                  VALUES(?,?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (user.email, user.password, user.full_name, user.user_id, user.role))
        self.conn.commit()
        return cur.lastrowid

    def create_room(self, room: Room):
        sql = '''INSERT INTO rooms(room_name,location,capacity,status)
                  VALUES(?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (room.room_name, room.location, room.capacity, room.status))
        self.conn.commit()
        return cur.lastrowid

    def create_booking(self, booking: Booking):
        sql = '''INSERT INTO bookings(user_id,room_id,start_time,end_time,token,token_used)
                  VALUES(?,?,?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (booking.user_id, booking.room_id, booking.start_time, booking.end_time, booking.token, booking.token_used))
        self.conn.commit()
        return cur.lastrowid

    def create_sensor_data(self, sensor_data: SensorData):
        sql = '''INSERT INTO sensor_data(room_id,timestamp,temperature,humidity,pressure)
                  VALUES(?,?,?,?,?)'''
        cur = self.conn.cursor()
        cur.execute(sql, (sensor_data.room_id, sensor_data.timestamp, sensor_data.temperature, sensor_data.humidity, sensor_data.pressure))
        self.conn.commit()
        return cur.lastrowid

    def get_available_rooms(self, start_time: str, end_time: str):
        cur = self.conn.cursor()
        cur.execute("""SELECT * FROM rooms WHERE id NOT IN (
                            SELECT room_id FROM bookings
                            WHERE (start_time < ? AND end_time > ?)
                            AND status != 'cancelled'
                        )""", (end_time, start_time))
        rows = cur.fetchall()
        return [Room(id=row['id'], room_name=row['room_name'], location=row['location'], capacity=row['capacity'], status=row['status']) for row in rows]

    def create_log(self, user_id: int, action: str, timestamp: str, details: str = None):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO logs (user_id, action, timestamp, details) VALUES (?, ?, ?, ?)",
                    (user_id, action, timestamp, details))
        self.conn.commit()

    def get_booking_by_id(self, booking_id: int) -> Optional[Booking]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = cur.fetchone()
        if row:
            return Booking(id=row['id'], user_id=row['user_id'], room_id=row['room_id'],
                           start_time=row['start_time'], end_time=row['end_time'],
                           token=row['token'], status=row['status'], token_used=bool(row['token_used']))
        return None

    def get_booking_by_token(self, token: str) -> Optional[Booking]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM bookings WHERE token = ?", (token,))
        row = cur.fetchone()
        if row:
            return Booking(id=row['id'], user_id=row['user_id'], room_id=row['room_id'],
                           start_time=row['start_time'], end_time=row['end_time'],
                           token=row['token'], status=row['status'], token_used=bool(row['token_used']))
        return None

    def update_booking_status(self, booking_id: int, new_status: str):
        cur = self.conn.cursor()
        cur.execute("UPDATE bookings SET status = ? WHERE id = ?", (new_status, booking_id))
        self.conn.commit()

    def mark_token_used(self, booking_id: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE bookings SET token_used = TRUE WHERE id = ?", (booking_id,))
        self.conn.commit()

    def get_user_bookings(self, user_id: int) -> list[Booking]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM bookings WHERE user_id = ?", (user_id,))
        rows = cur.fetchall()
        return [Booking(id=row['id'], user_id=row['user_id'], room_id=row['room_id'],
                        start_time=row['start_time'], end_time=row['end_time'],
                        token=row['token'], status=row['status'], token_used=bool(row['token_used'])) for row in rows]

    def get_room_by_id(self, room_id: int) -> Optional[Room]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        row = cur.fetchone()
        if row:
            return Room(id=row['id'], room_name=row['room_name'], location=row['location'],
                        capacity=row['capacity'], status=row['status'])
        return None

    def get_room_by_name(self, room_name: str) -> Optional[Room]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM rooms WHERE room_name = ?", (room_name,))
        row = cur.fetchone()
        if row:
            return Room(id=row['id'], room_name=row['room_name'], location=row['location'],
                        capacity=row['capacity'], status=row['status'])
        return None

    def create_all_tables(self):
        sql_create_users_table = """CREATE TABLE IF NOT EXISTS users (
                                            id integer PRIMARY KEY,
                                            email text NOT NULL UNIQUE,
                                            password text NOT NULL,
                                            full_name text NOT NULL,
                                            user_id text NOT NULL UNIQUE,
                                            role text NOT NULL
                                        );"""

        sql_create_rooms_table = """CREATE TABLE IF NOT EXISTS rooms (
                                        id integer PRIMARY KEY,
                                        room_name text NOT NULL UNIQUE,
                                        location text NOT NULL,
                                        capacity integer NOT NULL,
                                        status text NOT NULL
                                    );"""

        sql_create_bookings_table = """CREATE TABLE IF NOT EXISTS bookings (
                                        id integer PRIMARY KEY,
                                        user_id integer NOT NULL,
                                        room_id integer NOT NULL,
                                        start_time datetime NOT NULL,
                                        end_time datetime NOT NULL,
                                        token text NOT NULL UNIQUE,
                                        token_used BOOLEAN DEFAULT FALSE,
                                        FOREIGN KEY (user_id) REFERENCES users (id),
                                        FOREIGN KEY (room_id) REFERENCES rooms (id)
                                    );"""

        sql_create_sensor_data_table = """CREATE TABLE IF NOT EXISTS sensor_data (
                                            id integer PRIMARY KEY,
                                            room_id integer NOT NULL,
                                            timestamp datetime NOT NULL,
                                            temperature real NOT NULL,
                                            humidity real NOT NULL,
                                            pressure real NOT NULL,
                                            FOREIGN KEY (room_id) REFERENCES rooms (id)
                                        );"""

        sql_create_logs_table = """CREATE TABLE IF NOT EXISTS logs (
                                        id integer PRIMARY KEY,
                                        user_id integer,
                                        action text NOT NULL,
                                        timestamp datetime NOT NULL,
                                        details text,
                                        FOREIGN KEY (user_id) REFERENCES users (id)
                                    );"""

        if self.conn is not None:
            self.create_table(sql_create_users_table)
            self.create_table(sql_create_rooms_table)
            self.create_table(sql_create_bookings_table)
            self.create_table(sql_create_sensor_data_table)
            self.create_table(sql_create_logs_table)


def seed_data(db: Database):
    # Clear existing data
    db.conn.execute("DELETE FROM users")
    db.conn.execute("DELETE FROM rooms")
    db.conn.execute("DELETE FROM bookings")
    db.conn.execute("DELETE FROM sensor_data")
    db.conn.execute("DELETE FROM logs")
    db.conn.commit()

    # Seed users
    db.create_user(User('admin@test.com', 'admin', 'Admin', '100', 'admin'))
    db.create_user(User('security@test.com', 'security', 'Security', '200', 'security'))
    db.create_user(User('student1@test.com', 'student', 'Smith', 's1234567', 'user'))
    db.create_user(User('student2@test.com', 'student', 'John', 's1111111', 'user'))

    # Seed rooms
    db.create_room(Room('Science Room', 'Building 52', 20, 'Available'))
    db.create_room(Room('Art Room', 'Building 90', 25, 'Available'))
    db.conn.commit()

def main():
    database = r"pythonsqlite.db"
    db = Database(database)
    db.create_all_tables()
    seed_data(db)
    db.close()

if __name__ == '__main__':
    main()
