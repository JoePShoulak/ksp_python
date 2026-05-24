# telemetry.py

import threading

class TelemetryStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def update(self, **values):
        with self._lock:
            self._data.update(values)

    def get_snapshot(self):
        with self._lock:
            return dict(self._data)


telemetry = TelemetryStore()