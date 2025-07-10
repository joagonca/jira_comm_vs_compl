"""
State manager
"""

from pathlib import Path
import pickle

import numpy

from utils import seconds_to_pretty

STATE_FILE = ".state"

class State:
    """Class to store current state"""
    def __init__(self, iss):
        self.issues = iss
        self.delivered = self.carryover = 0
        self.delivered_sp = self.carryover_sp = 0
        self.parsed_issues = {}
        self.cycle_time_per_type = {}
        self.cycle_time_per_sp = {}
        self.outside_sprint_per_type = {}

    def add_delivered(self, story_points):
        """Add a delivered issue"""
        self.delivered += 1
        self.delivered_sp += story_points

    def add_carryover(self, story_points):
        """Add a carryover issue"""
        self.carryover += 1
        self.carryover_sp += story_points

    def add_issue_cycle_time(self, issue_key, issue_type, duration, story_points=None):
        """Adds the cycle time of an issue"""
        if issue_type in self.cycle_time_per_type:
            self.cycle_time_per_type[issue_type].append([issue_key, duration])
        else:
            self.cycle_time_per_type[issue_type] = [[issue_key, duration]]

        sp_key = -1 if story_points is None or story_points == 0 else int(story_points)
        if sp_key in self.cycle_time_per_sp:
            self.cycle_time_per_sp[sp_key].append([issue_key, duration])
        else:
            self.cycle_time_per_sp[sp_key] = [[issue_key, duration]]

    def add_parsed_issue(self, issue_key):
        """Adds a parsed issue to the dict"""
        self.parsed_issues[issue_key] = True

    def add_outside_sprint_issue(self, issue_key, issue_type):
        """Adds an issue that was worked on outside of a sprint"""
        if issue_type in self.outside_sprint_per_type:
            self.outside_sprint_per_type[issue_type].append(issue_key)
        else:
            self.outside_sprint_per_type[issue_type] = [issue_key]

    def get_total_valid_issues(self):
        """Returns a count of the total of valid issues"""
        return self.delivered + self.carryover

    def get_total_sps(self):
        """Returns a total of SPs worked on"""
        return self.delivered_sp + self.carryover_sp

    def persist_state(self):
        """Persists state to disk"""
        with open(STATE_FILE, "wb") as fb:
            pickle.dump(self, fb)

    def print_outside_sprint_stats(self):
        """Prints stats for items worked outside of sprints"""
        if not self.outside_sprint_per_type:
            return

        print("Items worked outside of sprints:")
        total_outside_sprint = sum(len(issues) for issues in self.outside_sprint_per_type.values())
        print(f"Total items: {total_outside_sprint}")
        print()

        for issue_type, issues in self.outside_sprint_per_type.items():
            print(f"{issue_type} ({len(issues)}):")
            display_issues = issues[:10]
            for issue in display_issues:
                print(f"    {issue}")
            if len(issues) > 10:
                print(f"    ... and {len(issues) - 10} more")
            print()

    def print_stats(self):
        """Prints current stats"""
        ratio_issue = self.delivered / self.get_total_valid_issues()
        ratio_sp = (self.delivered_sp / self.get_total_sps()) if self.get_total_sps() > 0 else 0

        print()
        print(f"Valid issues: {self.get_total_valid_issues()}")
        print(f"Ratio of Comm vs. Delv. (by issue count): {(ratio_issue * 100):.2f}%")
        print(f"Ratio of Comm vs. Delv. (by story points): {(ratio_sp * 100):.2f}%")

        print()
        print("Average cycle time:")
        for k, v in self.cycle_time_per_type.items():
            values = numpy.array([item[1] for item in v])
            argmax = numpy.argmax(values)
            argmin = numpy.argmin(values)

            average = numpy.mean(values)
            top_1 = numpy.percentile(values, 99)
            bottom_1 = numpy.percentile(values, 1)
            std_dev = numpy.std(values)

            print(f"{k} ({len(values)}): {seconds_to_pretty(average)}")
            print(f"    Top 1% [{v[argmax][0]}]: {seconds_to_pretty(top_1)}")
            print(f"    Bottom 1% [{v[argmin][0]}]: {seconds_to_pretty(bottom_1)}")
            print(f"    Std. Deviation: {seconds_to_pretty(std_dev)}")
            print()

        print("Average cycle time by Story Points:")

        sorted_sp_keys = sorted(self.cycle_time_per_sp.keys(), key=lambda x: float('inf') if x == -1 else x)

        for sp_key in sorted_sp_keys:
            v = self.cycle_time_per_sp[sp_key]
            values = numpy.array([item[1] for item in v])
            average = numpy.mean(values)
            std_dev = numpy.std(values)

            sp_display = f"{sp_key} SPs" if sp_key != -1 else "No SPs"
            print(f"{sp_display} ({len(values)}): {seconds_to_pretty(average)} (SD: {seconds_to_pretty(std_dev)})")

        print()
        self.print_outside_sprint_stats()

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
