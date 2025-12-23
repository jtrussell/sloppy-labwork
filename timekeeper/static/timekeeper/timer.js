class TimerCountdown {
    constructor(element) {
        this.element = element;
        this.countdownEl = element.querySelector('.timer__countdown');
        this.animationId = null;
        this.init();
    }

    init() {
        this.update();
    }

    getEndTimeMs() {
        return parseInt(this.element.dataset.endTimeMs, 10) || null;
    }

    getPauseTimeSeconds() {
        const val = this.element.dataset.pauseTimeRemainingSeconds;
        return val !== '' && val !== 'None' ? parseInt(val, 10) : null;
    }

    isActive() {
        return this.element.dataset.state === 'active';
    }

    formatTime(totalSeconds) {
        const isNegative = totalSeconds < 0;
        const absSeconds = Math.abs(totalSeconds);

        const hours = Math.floor(absSeconds / 3600);
        const minutes = Math.floor((absSeconds % 3600) / 60);
        const seconds = Math.floor(absSeconds % 60);

        const pad = (n) => n.toString().padStart(2, '0');

        let formatted;
        if (hours > 0) {
            formatted = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
        } else {
            formatted = `${pad(minutes)}:${pad(seconds)}`;
        }

        return isNegative ? `-${formatted}` : formatted;
    }

    calculateRemainingSeconds() {
        if (!this.isActive()) {
            return this.getPauseTimeSeconds() || 0;
        }

        const endTimeMs = this.getEndTimeMs();
        if (!endTimeMs) return 0;

        const now = Date.now();
        return Math.ceil((endTimeMs - now) / 1000);
    }

    update() {
        const remaining = this.calculateRemainingSeconds();
        this.countdownEl.textContent = this.formatTime(remaining);

        this.element.classList.toggle('timer--expired', remaining <= 0);
        this.element.classList.toggle('timer--paused', !this.isActive());

        if (this.isActive()) {
            this.animationId = requestAnimationFrame(() => this.update());
        }
    }

    start() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
        this.update();
    }

    stop() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
    }

    destroy() {
        this.stop();
    }
}

function initTimers() {
    document.querySelectorAll('.timer[data-code]').forEach((el) => {
        if (!el._timerCountdown) {
            el._timerCountdown = new TimerCountdown(el);
        }
    });
}

document.addEventListener('DOMContentLoaded', initTimers);
document.addEventListener('htmx:afterSwap', initTimers);
