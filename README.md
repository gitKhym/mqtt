# GROUP 14: Group Assigment

## TEAM INFORMATION:

The team is integrated by:

Khayam Alpay | s4018445

Pablo Lorenzo Martin | s4190903

Zen Jet Yew | s3928350

For the organization of the project we have created a github project board becaus it is more familiar to all of us as we all have worked prevously with it.
On the project board they are described the main features tthat the project must integrate, every feature is divided on different tasks so it would be easier to split the job among the 3 of us. Also they were ordered by priority so we could focus on the most important features first.

## WORK DIVISION

The division of work has been progresive everybody has been asigning task to themselves when once the previous task was completed so everybody could work at their own path, this work policy were agreed between all the members of the group so we all have the feeling we all have worked the same amount of time on the project. The details of the division are:

- Khayam Alpay: Admin functions, communications and debugging
- Pablo Lorenzo Martin: Room Pi implementation, Agent pi implementation and testing
- Zen Jet Yew: Testing and documentation.

There are some parts of the project that have not been implemented and we are really ashamed for that.

## Instructions

1. Clone the repository on each PI. Edit each PI's config such that
   `MQTT_IP = {Ip of the PI you're running master.py on}`
   `SOCKET_HOST = {Ip of the PI you're running master.py on}`

2. Run `python database.py` on the Master Pi.
3. Run `master.py` and `master_web.py` on the Master Pi
4. Run `agent.py` and `agent_web.py` on an Agent Pi
5. Run `room.py {id} "{room name}" "{location}" {capacity}` on a Room Pi to register that Pi as a single room

You can access the admin web page on `{master ip}:8001`, credentials are email: `admin@test.com` pass: `admin`

You can access the agent web page through its local network `localhost:7001`, credentials are email: `student1@test.com` or `student2@test.com` pass: `student`

## System architecture

## Challenges encountered

Among all the development of the system we have encounter multiple problems and challenges that we had to solve. The most important one was the usage of new and different tools and functionalities. The challenges encountered:

- Implementation of the MQTT Admin -> Pi's system
- Definition of the Fault state on room pi
- Implementation of the new enhancements
- Appliying desing pattern on the classes
- Serialization of messages
- At some points of the development, team communication.

With all of that we have been capable of cretaing a functional web application with most of the features asked.

## Lessons learned

During the development of the project we all have been able to learn more about the functionalities of the IoT systems, not only how they interact with the environment, but how they communicate between each other. Also we have learnt:

- The use of databases on the storage of enironmental data
- How a distributed system is configured.
- The functionalities of the MQTT comunications and publisher subscriber model.

## System Architecture

The system involves a central **Master Pi** coordinating multiple **Agent Pis** (user/staff interfaces) and **Room Pis** (classroom displays/sensors).

### Core Components & Responsibilities:

1.  **Master Pi (`master.py`, `master_web.py`):**
    - **Central Hub:** Acts as the primary server, managing all core business logic, user authentication, room states, booking schedules and accessing the database.
    - **Web Interface:** Hosts the admin site (`master_web.py`) to control and monitor rooms.

2.  **Agent Pi (`agent.py`, `agent_web.py`):**
    - **User Interface:** Each Agent Pi serves as a personal web interface (`agent_web.py`) for individual users (students/teachers) and security.
    - **Client-Side Logic:** Manages user-specific actions such as registration, login, room search, booking, and cancellations.
    - **Master Interaction:** Communicates exclusively with the Master Pi using Socket Programming for all backend operations, acting as a client.

3.  **Room Pi (`room.py`):**
    - **Classroom Interface:** Dedicated to a single classroom, functioning as a display terminal and sensor hub.
    - **MQTT Integration:** Publishes sensor data and status updates to the Master Pi via MQTT and subscribes to commands from the Master Pi.

### Communication Layer:

- **Socket Programming and MQTT**

### Data Management:

- **Centralized SQLite Database (`database.db`):** All persistent data (user profiles, room details, bookings, sensor history, logs, announcements) is stored in a single SQLite database.
- **Master-Only Access:** Only the Master Pi has direct read/write access to the database, enforcing a single point of truth and simplifying data consistency management.

### Role Management:

- The system supports distinct roles: **Admin**, **Users** (students/teachers), and **Security Staff**, with access privileges enforced at the Master Pi level.

### Technologies Used:

- **Python:** Primary programming language.
- **Flask:** Web framework for both Master and Agent web interfaces.
- **SQLite:** Lightweight relational database for data persistence.
- **Paho-MQTT:** Python client library for MQTT communication.
- **Socket Module:** For TCP/IP socket communication.
