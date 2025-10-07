import sqlite3

class Database:
    def __init__(self, db_file):
        self.conn = self.create_connection(db_file)

    def create_connection(self, db_file):
        conn = sqlite3.connect(db_file)
        return conn

    def create_table(self, create_table_sql):
        c = self.conn.cursor()
        c.execute(create_table_sql)

    def close(self):
        if self.conn:
            self.conn.close()


def main():
    database = r"pythonsqlite.db"

    sql_create_users_table = """ CREATE TABLE IF NOT EXISTS users (
                                        id integer PRIMARY KEY,
                                        email text NOT NULL UNIQUE,
                                        password text NOT NULL,
                                        full_name text NOT NULL,
                                        student_staff_id text NOT NULL UNIQUE
                                    ); """

    sql_create_rooms_table = """CREATE TABLE IF NOT EXISTS rooms (
                                    id integer PRIMARY KEY,
                                    name text NOT NULL UNIQUE,
                                    location text,
                                    capacity integer,
                                    status text NOT NULL
                                );"""

    sql_create_bookings_table = """CREATE TABLE IF NOT EXISTS bookings (
                                    id integer PRIMARY KEY,
                                    user_id integer NOT NULL,
                                    room_id integer NOT NULL,
                                    start_time datetime NOT NULL,
                                    end_time datetime NOT NULL,
                                    token text NOT NULL UNIQUE,
                                    status text NOT NULL,
                                    FOREIGN KEY (user_id) REFERENCES users (id),
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

    db = Database(database)

    if db.conn is not None:
        db.create_table(sql_create_users_table)
        db.create_table(sql_create_rooms_table)
        db.create_table(sql_create_bookings_table)
        db.create_table(sql_create_logs_table)
        db.close()

if __name__ == '__main__':
    main()
