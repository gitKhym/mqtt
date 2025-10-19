from enum import Enum

class Status(Enum):
    AVAILABLE = "Available"
    OCCUPIED = "Occupied"
    MAINTENANCE = "Maintenance"
    FAULT = "Fault"
    BOOKED = "Booked"
    CHECKED_IN = "Checked in"
    CHECKED_OUT = "Checked out"
    CANCELLED = "Cancelled"
