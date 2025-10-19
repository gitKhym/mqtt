function fetchRooms() {
  fetch("/api/rooms")
    .then((response) => response.json())
    .then((data) => {
      const rooms = data.rooms;
      const userRole = data.user_role;
      const container = document.getElementById("rooms-container");
      const existingRoomCards = new Set();

      // Update existing room cards or create new ones
      Object.entries(rooms).forEach(([room_id, room]) => {
        let roomCard = document.getElementById(`room-card-${room_id}`);
        if (!roomCard) {
          // Create new card if it doesn't exist
          roomCard = document.createElement("div");
          roomCard.id = `room-card-${room_id}`;
          roomCard.className = "card shadow-sm mb-4 border-0";
          container.appendChild(roomCard);
        }
        existingRoomCards.add(room_id);

        const bookingsHtml =
          room.bookings && room.bookings.length > 0
            ? `
                    <table class="table table-sm mt-3">
                        <thead>
                            <tr>
                                <th scope="col">Booked By</th>
                                <th scope="col">Time Frame</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${room.bookings
                              .map(
                                (booking) => `
                                <tr>
                                    <td>${booking.full_name}</td>
                                    <td>${booking.start_time} – ${booking.end_time}</td>
                                </tr>
                            `,
                              )
                              .join("")}
                        </tbody>
                    </table>
                `
            : `
                    <div class="text-center p-3 bg-light-subtle rounded mt-2 border">
                        <p class="text-muted mb-0">No bookings for today.</p>
                    </div>
                `;

        const statusClass =
          room.status === "Available"
            ? "bg-success-subtle text-success-emphasis"
            : room.status === "Booked"
              ? "bg-warning-subtle text-warning-emphasis"
              : room.status === "Occupied"
                ? "bg-danger-subtle text-danger-emphasis"
                : "bg-secondary-subtle text-secondary-emphasis";

        let securityDropdownHtml = '';
        if (userRole === "Security") {
            securityDropdownHtml = `
                <div class="mt-3">
                    <form action="/booking" method="POST" class="d-flex align-items-center">
                        <input type="hidden" name="room_id" value="${room_id}">
                        <label for="status-select-${room_id}" class="form-label me-2 mb-0">Change Status:</label>
                        <select class="form-select form-select-sm" id="status-select-${room_id}" name="new_status" onchange="this.form.submit()">
                            <option value="Available" ${room.status === "Available" ? "selected" : ""}>Available</option>
                            <option value="In Use" ${room.status === "In Use" ? "selected" : ""}>In Use</option>
                            <option value="Maintenance" ${room.status === "Maintenance" ? "selected" : ""}>Maintenance</option>
                            <option value="Fault" ${room.status === "Fault" ? "selected" : ""}>Fault</option>
                        </select>
                    </form>
                </div>
            `;
        }

        roomCard.innerHTML = `
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <div class="mb-2">
                                <h5 class="card-title fw-bold mb-0">${room.room_name}</h5>
                                <small class="text-muted">
                                    ${room.location} | Capacity: ${room.capacity}
                                </small>
                            </div>
                            <span class="badge fs-6 ${statusClass}">${room.status}</span>
                        </div>

                        ${securityDropdownHtml}

                        <div class="d-flex justify-content-around text-center my-3 border-top border-bottom py-3">
                            <div>
                                <div class="fw-bold mt-1">${room.temperature} °C</div>
                                <div class="text-muted small">Temperature</div>
                            </div>
                            <div>
                                <div class="fw-bold mt-1">${room.humidity} %</div>
                                <div class="text-muted small">Humidity</div>
                            </div>
                            <div>
                                <div class="fw-bold mt-1">${room.pressure} hPa</div>
                                <div class="text-muted small">Pressure</div>
                            </div>
                        </div>

                        <div>
                            <h5 class="card-subtitle mb-2 text-muted">Today's Bookings</h5>
                            ${bookingsHtml}
                        </div>
                    </div>
                `;
      });

      // Remove room cards that no longer exist
      Array.from(container.children).forEach((card) => {
        if (!existingRoomCards.has(card.id.replace("room-card-", ""))) {
          card.remove();
        }
      });

      if (Object.keys(rooms).length === 0) {
        container.innerHTML =
          '<div class="alert alert-info text-center">No rooms available at the moment.</div>';
      }
    })
    .catch((error) => {
      console.error("Error fetching rooms:", error);
      document.getElementById("rooms-container").innerHTML =
        '<div class="alert alert-danger text-center">Could not load room data. Please try again later.</div>';
    });
}

document.addEventListener("DOMContentLoaded", () => {
  fetchRooms();
  setInterval(fetchRooms, 10000);

  const staticBookingForm = document.getElementById("static-booking-form");
  if (staticBookingForm) {
    staticBookingForm.addEventListener("submit", function () {
      const button = this.querySelector('button[type="submit"]');
      button.disabled = true;
      button.textContent = "Booking...";
    });
  }
});

