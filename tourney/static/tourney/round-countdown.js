class RoundCountdown {
  constructor(element) {
    this.element = element;
    this.displayElement = element.querySelector('.countdown-display');
    this.endTimestamp = parseInt(element.dataset.endTimestamp, 10);
    this.animationFrameId = null;

    if (this.endTimestamp && this.displayElement) {
      this.start();
    }
  }

  start() {
    const updateCountdown = () => {
      const now = Date.now();
      const remaining = this.endTimestamp - now;

      if (remaining <= 0) {
        this.displayElement.textContent = 'Time Expired';
        this.displayElement.classList.add('countdown-expired');
        return;
      }

      this.displayElement.textContent = this.formatTime(remaining);
      this.animationFrameId = requestAnimationFrame(updateCountdown);
    };

    updateCountdown();
  }

  formatTime(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    const parts = [];

    if (days > 0) {
      parts.push(days);
    }

    if (days > 0 || hours > 0) {
      parts.push(hours.toString().padStart(days > 0 ? 2 : 1, '0'));
    }

    parts.push(minutes.toString().padStart(2, '0'));
    parts.push(seconds.toString().padStart(2, '0'));

    return parts.join(':');
  }

  stop() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const countdownElements = document.querySelectorAll('.round-countdown');
  const countdowns = [];

  countdownElements.forEach(element => {
    countdowns.push(new RoundCountdown(element));
  });

  window.addEventListener('beforeunload', () => {
    countdowns.forEach(countdown => countdown.stop());
  });
});
