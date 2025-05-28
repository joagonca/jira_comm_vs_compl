"""
State manager
"""

from pathlib import Path
import pickle

STATE_FILE = ".state"

class State:
    """Class to store current state"""
    def __init__(self, iss):
        self.issues = iss
        self.delivered = self.carryover = 0
        self.delivered_sp = self.carryover_sp = 0
        self.parsed_issues = {}
        self.cycle_time_per_type = {}

    def persist_state(self, pi, cycle, delivered, carryover, delivered_sp, carryover_sp):
        """Persists state to disk"""
        self.parsed_issues = pi
        self.cycle_time_per_type = cycle
        self.delivered = delivered
        self.carryover = carryover
        self.delivered_sp = delivered_sp
        self.carryover_sp = carryover_sp

        with open(STATE_FILE, "wb") as fb:
            pickle.dump(self, fb)

    @staticmethod
    def load_state():
        """Load state from disk"""
        existing_state = Path(STATE_FILE)
        if existing_state.is_file():
            with open(".state", "rb") as f:
                return pickle.load(f)

        return None

    @staticmethod
    def clear_state():
        """Deletes state file"""
        Path(STATE_FILE).unlink()
