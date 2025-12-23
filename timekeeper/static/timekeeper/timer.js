class TimerCountdown {
    constructor(element) {
        this.element = element;
        this.countdownEl = element.querySelector('.timer__countdown');
        this.animationId = null;
        this.currentDisplay = '';
        this.init();
    }

    init() {
        this.buildDigitStructure();
        this.update();
    }

    buildDigitStructure() {
        this.countdownEl.innerHTML = '';
        this.countdownEl.classList.add('timer__countdown--sliding');

        this.digitSlots = [];
        const format = this.getInitialFormat();

        for (let i = 0; i < format.length; i++) {
            const char = format[i];
            if (char === ':') {
                const separator = document.createElement('span');
                separator.className = 'timer__separator';
                separator.textContent = ':';
                this.countdownEl.appendChild(separator);
                this.digitSlots.push(null);
            } else {
                const slot = this.createDigitSlot();
                this.countdownEl.appendChild(slot.container);
                this.digitSlots.push(slot);
            }
        }
    }

    createDigitSlot() {
        const container = document.createElement('span');
        container.className = 'timer__digit-slot';

        const track = document.createElement('span');
        track.className = 'timer__digit-track';

        for (let i = 0; i <= 9; i++) {
            const digit = document.createElement('span');
            digit.className = 'timer__digit';
            digit.textContent = i;
            track.appendChild(digit);
        }

        container.appendChild(track);

        return { container, track, currentValue: 0 };
    }

    setDigit(slot, value) {
        if (slot.currentValue === value) return;

        slot.currentValue = value;
        const offsetPercent = value * -10;
        slot.track.style.transform = `translateY(${offsetPercent}%)`;
    }

    getInitialFormat() {
        const remaining = this.calculateRemainingSeconds();
        const absSeconds = Math.abs(remaining);
        const hours = Math.floor(absSeconds / 3600);
        return hours > 0 ? '00:00:00' : '00:00';
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

    calculateRemainingSeconds() {
        if (!this.isActive()) {
            return this.getPauseTimeSeconds() || 0;
        }

        const endTimeMs = this.getEndTimeMs();
        if (!endTimeMs) return 0;

        const now = Date.now();
        return Math.ceil((endTimeMs - now) / 1000);
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

        return { formatted, isNegative };
    }

    update() {
        const remaining = this.calculateRemainingSeconds();
        const { formatted, isNegative } = this.formatTime(remaining);

        if (formatted.length !== this.digitSlots.length) {
            this.buildDigitStructure();
        }

        let slotIndex = 0;
        for (let i = 0; i < formatted.length; i++) {
            const char = formatted[i];
            const slot = this.digitSlots[i];

            if (char === ':') {
                continue;
            }

            if (slot) {
                const digitValue = parseInt(char, 10);
                this.setDigit(slot, digitValue);
            }
        }

        this.element.classList.toggle('timer--expired', remaining <= 0);
        this.element.classList.toggle('timer--paused', !this.isActive());
        this.element.classList.toggle('timer--negative', isNegative);

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
        if (el._timerCountdown) {
            el._timerCountdown.destroy();
        }
        el._timerCountdown = new TimerCountdown(el);
    });
}

document.addEventListener('DOMContentLoaded', initTimers);
document.addEventListener('htmx:afterSwap', initTimers);
