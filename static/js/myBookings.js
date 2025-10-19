function fetchBookings() {
    fetch('/api/my-bookings')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(bookings => {
            const container = document.getElementById('bookings-container');
            if (bookings && bookings.length > 0) {
                container.innerHTML = bookings.map(b => `
                    <div class="booking-card">
                        <div class="row align-items-center">
                            <div class="col-md-8">
                                <div class="booking-header">Room ${b.room_id}</div>
                                <div class="text-muted">
                                    <small>
                                        <strong>Date:</strong> ${b.date} |
                                        <strong>Start:</strong> ${b.start_time} |
                                        <strong>End:</strong> ${b.end_time} |
                                        <strong>Status:</strong> ${b.status}
                                        ${b.status === 'Booked' ? `| <strong>Token:</strong> ${b.booking_access_token}` : ''}
                                    </small>
                                </div>
                            </div>
                            <div class="col-md-4 text-end">
                                <form method="POST" action="/my-bookings">
                                    <input type="hidden" name="room_id" value="${b.room_id}">
                                    <input type="hidden" name="booking_id" value="${b.booking_id}">
                                    <input type="hidden" name="full_date" value="${b.full_start_time}">
                                    <input type="hidden" name="end_time" value="${b.full_end_time}">
                                    ${b.status === 'Booked' ? `<input type="hidden" name="booking_access_token" value="${b.booking_access_token}">` : ''}
                                   
                                    ${b.status === 'Booked' ? `
                                        <button name="action" value="check_in" class="btn btn-success btn-sm">Check In</button>
                                        <button name="action" value="cancel" class="btn btn-danger btn-sm">Cancel</button>
                                    ` : ''}
                                    ${b.status === 'checked in' ? `
                                        <button name="action" value="check_out" class="btn btn-primary btn-sm">Check Out</button>
                                    ` : ''}
                                </form>
                            </div>
                        </div>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<div class="alert alert-info text-center">You have no bookings.</div>';
            }
        })
        .catch(error => {
            console.error('Error fetching bookings:', error);
            const container = document.getElementById('bookings-container');
            container.innerHTML = '<div class="alert alert-danger text-center">Could not load bookings. Please try again later.</div>';
        });
}

document.addEventListener('DOMContentLoaded', () => {
    fetchBookings();
    setInterval(fetchBookings, 10000);
});
