from enum import Enum

class Status(Enum):
    AVAILABLE = "Available"
    OCCUPIED = "Occupied"
    MAINTENANCE = "Maintenance"
    FAULT = "Fault"
    BOOKED = "Booked"
    CHECKED_IN = "checked in"
    CHECKED_OUT = "checked out"
    CANCELLED = "Cancelled"
