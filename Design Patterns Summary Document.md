
## Overview

This document outlines the Object-Oriented Programming (OOP) and design patterns implemented in the Master, Agent, and Room modules of the project. Each module contributes to a distributed IoT control system for managing and monitoring room states across multiple Raspberry Pi devices.
This document summarises the Object‑Oriented Programming (OOP) and design patterns used across Master, Agent, and Room. Together they form a small distributed IoT system for booking and monitoring rooms on Raspberry Pi devices.

What you’ll find below:
- Which patterns we used (and why)
- Where they show up in code
- Trade‑offs and alternatives we considered
## Project context

- Master: Central coordinator of bookings, status, MQTT ingestion, and socket server for web/agent clients (`master.py`).
- Agent: Client-side process that talks to Master via MQTT and TCP socket (`agent.py`).
- Room (RoomPi): Edge device process running on a room Pi; handles sensors, MQTT, and a socket server for direct commands (`room.py`).
- Web apps: Admin (`master_web.py`) and user (`agent_web.py`) Flask front-ends communicating with Master/Room.
- Messaging: MQTT via paho-mqtt with topics like `rooms/<room_id>/status`, `rooms/<room_id>/command`, and `rooms/register`.
- Persistence: SQLite via `database.py` with tables for users, rooms, bookings, sensor_data, logs, announcements.

---


## TL;DR

- Encapsulation, Abstraction, and Composition keep networking, threads, and database details tidy and testable.
- Observer (publish–subscribe) is provided by MQTT, cleanly decoupling devices and the Master.
- Worker Threads handle long‑running loops (sockets, MQTT, telemetry) without blocking the main thread.
- Separation of Concerns splits responsibilities across Master, Room, Agent, and the web apps.
- Singleton is conceptual only (one process per role); we didn’t enforce it in code.
## 1) Encapsulation

Where and how
Where it shows up
- `master.py`: Internal concerns are encapsulated in methods prefixed with `_`, e.g. `_on_mqtt_connect`, `_on_mqtt_message`, `_mqtt_subscriber_thread`, `_socket_server_thread`, `_handle_client`. Higher-level APIs expose intent-driven methods like `book_room`, `check_in`, `get_room_inf`.
- `agent.py`: MQTT and socket client logic is wrapped behind `_mqtt_subscriber_thread`, `_socket_client_thread`, with a single `start()` entrypoint.
- `room.py`: Hardware and protocol specifics are kept inside `update_leds`, `environment_readings`, `_on_mqtt_message`, `handle_user`, and `room_management`.

Why it was suitable
Why it fits
- Hides complex networking, threading, and persistence details; exposes simple actions (`start`, `stop`, booking/check-in/out).
- Reduces accidental misuse and simplifies testing and refactoring.

Challenges/alternatives
Trade‑offs / alternatives
- Standalone scripts were possible, but class-based encapsulation made concurrency and state management far easier to reason about.

---

## 2) Abstraction

Where and how
Where it shows up
- Each module abstracts a real-world entity:
  - Master abstracts the control server and coordination logic (MQTT ingest, DB writes, socket API).
  - Agent abstracts a client device bridging MQTT and TCP to the Master.
  - Room abstracts a physical room with sensors, current status, and a command interface.
- Public methods (`start`, route handlers, booking operations) abstract away low-level message formats and timing rules.

Why it was suitable
Why it fits
- Simplifies cross-module integration: callers don’t need to handle MQTT parsing or database schema details.

Challenges/alternatives
Trade‑offs / alternatives
- Without clear abstractions, shared logic would leak across layers, making evolution and testing difficult.

---

## 3) Composition

Where and how
Where it shows up
- Objects are built from collaborating components (has-a):
  - `mqtt.Client` for pub/sub
  - `threading.Thread` for background workers
  - `socket.socket` for TCP communication
  - `Database` for persistence
- Prefer composition over inheritance: Master “has” MQTT client and socket server; Room “has” Sense HAT, MQTT client, socket server.
- We favour composition over inheritance: Master “has” an MQTT client and socket server; Room “has” a Sense HAT, MQTT client, and socket server.
Why it was suitable
Why it fits
- Components can be replaced or mocked in tests (e.g., swapping in fake MQTT clients).
- Avoids rigid inheritance hierarchies and keeps responsibilities modular.

Challenges/alternatives
Trade‑offs / alternatives
- A generic CommunicationNode base class was possible, but would increase coupling and reduce flexibility.

---

## 4) Observer / Publish–Subscribe (via MQTT)

Where and how
Where it shows up
- MQTT decouples producers and consumers:
  - Master subscribes to `rooms/+/status` (sensor and status payloads) and `rooms/register` (room activation and metadata).
  - Master publishes to `rooms/<room_id>/command` for operations like `UPDATE_STATUS`, `CHECK_IN`, `CHECK_OUT`, and booking updates.
  - Room publishes `SENSOR_DATA` on `rooms/<room_id>/status` and registers itself on `rooms/register`.
  - Agent can subscribe to broadcast/control topics as needed.

Why it was suitable
Why it fits
- Built-in decoupling, fan-out, and asynchronous delivery make MQTT ideal for IoT topologies with intermittent devices.

Challenges/alternatives
Trade‑offs / alternatives
- A pure socket approach would require long-lived connections and manual fan-out management; MQTT eliminates that complexity.

---

## 5) Worker Thread pattern (Threading)

Where and how
Where it shows up
- Long-running loops are moved off the main thread:
  - Master: `_socket_server_thread` and `_mqtt_subscriber_thread` run concurrently.
  - Agent: `_mqtt_subscriber_thread` and `_socket_client_thread` handle background communication.
  - Room: `environment_readings` periodically publishes telemetry; MQTT subscriber runs in its own thread; `room_management` accepts client connections.

Why it was suitable
Why it fits
- Keeps the system responsive; prevents one blocking loop from stalling the whole process.

Challenges/alternatives
Trade‑offs / alternatives
- `asyncio` was an option, but threading integrates cleanly with paho-mqtt and existing socket code with minimal refactor cost.

---

## 6) Singleton (conceptual)

Where and how
Where it shows up
- Operationally, each Pi runs a single Master or Agent process; only one RoomPi instance should manage a room id.
- Not enforced in code, but deployment model ensures one controlling instance per role.

Why it was suitable
Why it fits
- Prevents contention over shared ports/resources and avoids duplicate controllers issuing conflicting commands.

Challenges/alternatives
Trade‑offs / alternatives
- Enforcing a formal Singleton in code wasn’t necessary; process-level control and service managers (systemd) act as the guardrail.

---

## 7) Separation of Concerns

Where and how
Where it shows up
- Clear role boundaries:
  - Master: global coordination, DB, MQTT ingress, and socket protocol.
  - Agent: user/edge client bridging MQTT and TCP.
  - Room: device state, local socket handling, and sensor integration.
  - Web apps: presentation and HTTP endpoints, delegating to Master and Room via sockets.

Why it was suitable
Why it fits
- Enables independent testing and iteration; changes to one concern rarely ripple into another.

Challenges/alternatives
Trade‑offs / alternatives
- A monolithic script would become unmanageable as the feature set and number of rooms grow.

---

## Concrete examples mapped to code

- Master MQTT observer
  - `_on_mqtt_connect` subscribes to `rooms/+/status` and `rooms/register`.
  - `_on_mqtt_message` persists `SENSOR_DATA` and updates active room status; handles registration payloads.
- Master booking lifecycle
  - `book_room`, `check_in`, `check_out`, `cancel_booking` update DB and publish `UPDATE_STATUS` to `rooms/<id>/command`.
- Room command handling (`_on_mqtt_message`)
  - Responds to `BOOK_ROOM`, `CANCEL_BOOKING`, `CHECK_IN`, `CHECK_OUT`, and `UPDATE_STATUS`; updates LEDs via `update_leds`.
- Room telemetry worker
  - `environment_readings` periodically publishes `{ op: SENSOR_DATA, ... }` to `rooms/<id>/status` and updates LEDs.
- Agent worker threads
  - `_mqtt_subscriber_thread` and `_socket_client_thread` run concurrently; `start()` orchestrates lifecycle.

---

## Challenges encountered and choices made

- Time windows and state transitions
  - Booking/check-in/out logic required careful boundary handling; tests enforce correct transitions and timing checks.
- Robustness vs complexity
  - Stuck with threads instead of `asyncio` for simpler integration with paho-mqtt and existing sockets.
- Decoupling via MQTT
  - Avoided direct socket broadcasting; MQTT’s pub/sub reduced coupling and improved scalability.


---

## Deliberately not used

- Template Method
  - Removed by design to keep behaviour flexible across Master/Agent/Room without a forced hook sequence.
- Heavy inheritance
  - Favouring composition keeps modules loosely coupled and easier to test.
- Hard Singletons
  - Deployment conventions (one process per role) were sufficient; global Singletons would reduce testability.
