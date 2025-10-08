import datetime

class SensorData:
    def __init__(self, room_id, temperature, humidity, pressure, timestamp=None, id=None):
        self.id = id
        self.room_id = room_id
        self.temperature = temperature
        self.humidity = humidity
        self.pressure = pressure
        self.timestamp = timestamp or datetime.datetime.now()

    def __repr__(self):
        return f"<SensorData(id={self.id}, room_id={self.room_id}, temp={self.temperature})>"
