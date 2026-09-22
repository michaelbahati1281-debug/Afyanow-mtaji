document.addEventListener('DOMContentLoaded', () => {
  const csrf = () => {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  };

  document.querySelectorAll('form.confirm-form').forEach(form => {
    form.addEventListener('submit', (e) => {
      const msg = form.dataset.confirm || 'Are you sure?';
      if (!window.confirm(msg)) {
        e.preventDefault();
      }
    });
  });

  const datePicker = document.querySelector('[data-date-picker]');
  const slotContainer = document.querySelector('[data-time-slots]');
  const hiddenDate = document.querySelector('[data-hidden-date]');
  const hiddenTime = document.querySelector('[data-hidden-time]');

  if (datePicker && slotContainer && hiddenTime) {
    function loadSlots(dateStr) {
      const providerId = datePicker.dataset.providerId;
      fetch(`/patient/availability/${providerId}?date=${dateStr}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(r => r.json())
        .then(data => {
          slotContainer.innerHTML = '';
          if (!data.slots || data.slots.length === 0) {
            slotContainer.innerHTML = '<p class="muted small">No available slots on this date.</p>';
            hiddenTime.value = '';
            return;
          }
          data.slots.forEach(slot => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'time-slot';
            btn.textContent = slot;
            btn.addEventListener('click', () => {
              slotContainer.querySelectorAll('.time-slot').forEach(b => b.classList.remove('selected'));
              btn.classList.add('selected');
              hiddenTime.value = slot;
            });
            slotContainer.appendChild(btn);
          });
        })
        .catch(() => {
          slotContainer.innerHTML = '<p class="muted small">Could not load availability.</p>';
        });
    }

    datePicker.querySelectorAll('.day-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        datePicker.querySelectorAll('.day-chip').forEach(c => c.classList.remove('selected'));
        chip.classList.add('selected');
        if (hiddenDate) hiddenDate.value = chip.dataset.date;
        loadSlots(chip.dataset.date);
      });
    });
  }
});