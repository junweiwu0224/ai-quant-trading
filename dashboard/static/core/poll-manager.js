(function attachPollManager(global) {
    'use strict';

    const PollManager = {
        _timers: {},

        register(name, callback, interval) {
            this.cancel(name);
            this._timers[name] = { callback, interval, timer: null, paused: false };
            this._timers[name].timer = setInterval(() => {
                if (!this._timers[name]?.paused) callback();
            }, interval);
        },

        cancel(name) {
            const t = this._timers[name];
            if (t) {
                clearInterval(t.timer);
                delete this._timers[name];
            }
        },

        pause(name) {
            if (this._timers[name]) this._timers[name].paused = true;
        },

        resume(name) {
            if (this._timers[name]) this._timers[name].paused = false;
        },

        pauseAll() {
            for (const t of Object.values(this._timers)) t.paused = true;
        },

        resumeAll() {
            for (const t of Object.values(this._timers)) t.paused = false;
        },

        destroy() {
            for (const name of Object.keys(this._timers)) this.cancel(name);
        },
    };

    global.PollManager = PollManager;
})(window);
