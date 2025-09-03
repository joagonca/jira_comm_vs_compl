"""
State manager
"""

from pathlib import Path
import pickle

import numpy

from utils import seconds_to_pretty, AGING_THRESHOLDS, JIRA_CONFIG

class State:
    """Class to store current state"""
    def __init__(self, iss, command_args=None):
        self.issues = iss
        self.delivered = self.carryover = 0
        self.delivered_sp = self.carryover_sp = 0
        self.parsed_issues = {}
        self.cycle_time_per_type = {}
        self.cycle_time_per_sp = {}
        self.aging_items = []
        self.effort_per_type = {}
        self.command_args = command_args

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

        if issue_type in self.effort_per_type:
            self.effort_per_type[issue_type] += duration
        else:
            self.effort_per_type[issue_type] = duration

        sp_key = -1 if story_points is None or story_points == 0 else int(story_points)
        if sp_key in self.cycle_time_per_sp:
            self.cycle_time_per_sp[sp_key].append([issue_key, duration])
        else:
            self.cycle_time_per_sp[sp_key] = [[issue_key, duration]]

    def add_parsed_issue(self, issue_key):
        """Adds a parsed issue to the dict"""
        self.parsed_issues[issue_key] = True

    def add_aging_item(self, issue_key, issue_type, in_progress_days, is_aged, story_points):
        """Adds an aging item to tracking"""
        self.aging_items.append({
            'key': issue_key,
            'type': issue_type,
            'days': in_progress_days,
            'is_aged': is_aged,
            'story_points': story_points
        })

    def command_matches(self, current_args):
        """Check if current command arguments match the saved ones"""
        if self.command_args is None:
            return False
        
        relevant_attrs = ['url', 'project', 'teams', 'skew', 'interval', 'jql']
        
        for attr in relevant_attrs:
            if getattr(current_args, attr, None) != getattr(self.command_args, attr, None):
                return False
        
        return True

    def get_total_valid_issues(self):
        """Returns a count of the total of valid issues"""
        return self.delivered + self.carryover

    def get_total_sps(self):
        """Returns a total of SPs worked on"""
        return self.delivered_sp + self.carryover_sp

    def persist_state(self):
        """Persists state to disk"""
        with open(JIRA_CONFIG['STATE_FILE'], "wb") as fb:
            pickle.dump(self, fb)

    def print_stats(self):
        """Prints current stats"""
        ratio_issue = self.delivered / self.get_total_valid_issues()
        ratio_sp = (self.delivered_sp / self.get_total_sps()) if self.get_total_sps() > 0 else 0

        print()
        print(f"Valid issues: {self.get_total_valid_issues()}")
        print(f"Ratio of Comm vs. Delv. (by issue count): {(ratio_issue * 100):.2f}%")
        print(f"Ratio of Comm vs. Delv. (by story points): {(ratio_sp * 100):.2f}%")

        self.print_aging_report()

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

        self.print_rework_ratio()

    def print_rework_ratio(self):
        """Prints rework ratio (fixing vs building new)"""
        defect_effort = self.effort_per_type.get("Defect", 0) + self.effort_per_type.get("Bug", 0)
        
        story_effort = self.effort_per_type.get("Story", 0)
        total_effort = defect_effort + story_effort
        
        if total_effort > 0:
            rework_ratio = (defect_effort / total_effort) * 100
            print(f"Rework Ratio (fixing vs. building new): {rework_ratio:.2f}%")
        else:
            print("Rework Ratio: No data available (no Stories, Defects, or Bugs with cycle time)")

    def print_aging_report(self):
        """Prints work item aging report"""
        if not self.aging_items:
            print()
            print("Work Item Aging: No items currently in progress")
            return

        print()
        print("Work Item Aging (items currently 'In Progress'):")
        
        aged_items = [item for item in self.aging_items if item['is_aged']]
        total_in_progress = len(self.aging_items)
        
        if aged_items:
            print(f"  Total aged items: {len(aged_items)} out of {total_in_progress} in progress")
            print()
            
            aged_by_type = {}
            for item in aged_items:
                item_type = item['type']
                if item_type not in aged_by_type:
                    aged_by_type[item_type] = []
                aged_by_type[item_type].append(item)
            
            for item_type, items in aged_by_type.items():
                print(f"  {item_type} (threshold: {self.get_aging_threshold(item_type)} days):")
                for item in sorted(items, key=lambda x: x['days'], reverse=True):
                    print(f"    {item['key']}: {item['days']:.1f} days in progress")
                print()
        else:
            print(f"  No aged items found ({total_in_progress} items in progress)")
            print()

    def get_aging_threshold(self, issue_type):
        """Gets aging threshold for issue type"""
        return AGING_THRESHOLDS.get(issue_type, 14)

    @staticmethod
    def load_state():
        """Load state from disk"""
        state_file = JIRA_CONFIG['STATE_FILE']
        existing_state = Path(state_file)
        if existing_state.is_file():
            with open(state_file, "rb") as f:
                return pickle.load(f)

        return None

    @staticmethod
    def clear_state():
        """Deletes state file"""
        Path(JIRA_CONFIG['STATE_FILE']).unlink()
