function fetchRooms() {
    fetch('/api/rooms')
        .then(response => response.json())
        .then(rooms => {
            const container = document.getElementById('rooms-container');
            if (Object.keys(rooms).length > 0) {
                container.innerHTML = Object.entries(rooms).map(([room_id, room]) => {
                    const bookingsHtml = room.bookings && room.bookings.length > 0 ? `
                        <table class="table table-sm mt-3">
                            <thead>
                                <tr>
                                    <th scope="col">Booked By</th>
                                    <th scope="col">Time Frame</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${room.bookings.map(booking => `
                                    <tr>
                                        <td>${booking.full_name}</td>
                                        <td>${booking.start_time} – ${booking.end_time}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : `
                        <div class="text-center p-3 bg-light-subtle rounded mt-2 border">
                            <p class="text-muted mb-0">No bookings for today.</p>
                        </div>
                    `;

                    const statusClass = room.status === 'Available' ? 'bg-success-subtle text-success-emphasis' :
                                      room.status === 'Booked' ? 'bg-warning-subtle text-warning-emphasis' :
                                      room.status === 'Occupied' ? 'bg-danger-subtle text-danger-emphasis' :
                                      'bg-secondary-subtle text-secondary-emphasis';

                    return `
                    <div class="card shadow-sm mb-4 border-0">
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

                        <form class="booking-form mt-4" method="POST" action="/booking">
                          <input type="hidden" name="room_id" value="${room_id}">
                          <div class="row g-2">
                            <div class="col-md-6">
                              <label for="starttime_${room_id}" class="form-label">Start Time</label>
                              <input type="datetime-local" id="starttime_${room_id}" name="starttime" class="form-control" required>
                            </div>
                            <div class="col-md-4">
                              <label for="duration_${room_id}" class="form-label">Duration (hours)</label>
                              <input type="number" id="duration_${room_id}" name="duration" class="form-control" min="1" max="4" required>
                            </div>
                            <div class="col-md-2 d-flex align-items-end">
                              <button type="submit" class="btn btn-primary w-100">Book</button>
                            </div>
                          </div>
                        </form>
                      </div>
                    </div>
                    `;
                }).join('');
            } else {
                container.innerHTML = '<div class="alert alert-info text-center">No rooms available at the moment.</div>';
            }
        })
        .catch(error => {
            console.error('Error fetching rooms:', error);
            document.getElementById('rooms-container').innerHTML = '<div class="alert alert-danger text-center">Could not load room data. Please try again later.</div>';
        });
}

document.addEventListener('DOMContentLoaded', () => {
    fetchRooms();
    setInterval(fetchRooms, 10000);
});
