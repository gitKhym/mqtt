class Room:
    def __init__(self, room_name, status='Available', id=None):
        self.id = id
        self.room_name = room_name
        self.status = status

    def __repr__(self):
        return f"<Room(id={self.id}, room_name='{self.room_name}', status='{self.status}')>"
