import datetime

class Booking:
    def __init__(self, user_id, room_id, start_time, end_time, token, status='active', token_used=False, id=None):
        self.id = id
        self.user_id = user_id
        self.room_id = room_id
        self.start_time = start_time
        self.end_time = end_time
        self.token = token
        self.status = status
        self.token_used = token_used

    def __repr__(self):
        return f"<Booking(id={self.id}, user_id={self.user_id}, room_id={self.room_id}, status='{self.status}')>"