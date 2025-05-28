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
        self.parsed_issues = {}

    def persist_state(self, pi, delivered, carryover):
        """Persists state to disk"""
        self.parsed_issues = pi
        self.delivered = delivered
        self.carryover = carryover

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
