import datetime

class Announcement:
    def __init__(self, user_id, content, timestamp=None, room_id=None, id=None):
        self.id = id
        self.user_id = user_id
        self.content = content
        self.timestamp = timestamp or datetime.datetime.now()
        self.room_id = room_id

    def __repr__(self):
        return f"<Announcement(id={self.id}, user_id={self.user_id}, room_id={self.room_id})>"
