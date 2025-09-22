"""
JIRA issue classification and state management logic
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from .models import Event, StatusEvent, SprintEvent, IssueClassification
from utils import AGING_THRESHOLDS, JIRA_CONFIG


class IssueState:
    """State machine for tracking issue progression"""
    def __init__(self, parsed_sprints: List[Dict[str, Any]]) -> None:
        self.parsed_sprints: List[Dict[str, Any]] = parsed_sprints
        self.work_start: Optional[datetime] = None
        self.work_end: Optional[datetime] = None
        self.current_status: Optional[str] = None
        self.last_in_progress_start: Optional[datetime] = None
        self.pending_duration: float = 0
        self.pending_start: Optional[datetime] = None
        self.start_sprint: str = ""
        self.end_sprint: str = ""
        self.was_resolved: bool = False
        self.sprint_assignments: Dict[str, datetime] = {}  # sprint_name -> assignment_timestamp
        self.sprint_removals: Dict[str, datetime] = {}     # sprint_name -> removal_timestamp

    def handle_status_change(self, event: StatusEvent) -> None:
        """Process a status change event"""
        if event.to_status == "In Progress":
            if self.work_start is None:
                self.work_start = event.timestamp
                self.start_sprint = event.sprint or ""
            self.last_in_progress_start = event.timestamp

            # Check if this transition happened in a closed sprint (for legacy compatibility)
            sprint_info = next((s for s in self.parsed_sprints if s.get('name') == event.sprint), None)
            if sprint_info and sprint_info.get('state') == 'CLOSED':
                self.was_resolved = True  # Treat work in closed sprint as resolved
                # For closed sprint work, use the end date of the sprint as work_end if not already set
                if self.work_end is None and sprint_info.get('completeDate'):
                    self.work_end = sprint_info['completeDate']
                elif self.work_end is None and sprint_info.get('endDate'):
                    self.work_end = sprint_info['endDate']
                self.end_sprint = event.sprint or ""

        elif event.to_status == "Resolved":
            self.work_end = event.timestamp
            self.end_sprint = event.sprint or ""
            self.was_resolved = True

        elif event.to_status == "Pending":
            self.pending_start = event.timestamp
        elif event.from_status == "Pending" and self.pending_start is not None:
            self.pending_duration += (event.timestamp - self.pending_start).total_seconds()

        self.current_status = event.to_status

    def handle_sprint_change(self, event: SprintEvent) -> None:
        """Process a sprint assignment/removal event"""
        if event.action == "added":
            self.sprint_assignments[event.sprint] = event.timestamp
        elif event.action == "removed":
            self.sprint_removals[event.sprint] = event.timestamp

    def get_final_classification(self, issue_type: str) -> IssueClassification:
        """Generate final classification based on accumulated state"""
        classification = IssueClassification()

        # Basic timing metrics
        classification.work_start = self.work_start
        classification.work_end = self.work_end
        classification.current_status = self.current_status
        classification.last_in_progress_start = self.last_in_progress_start
        classification.pending_duration = self.pending_duration

        # Calculate cycle time (matching original logic with weekend exclusion)
        if self.work_start is not None and self.work_end is not None:
            total_seconds = (self.work_end - self.work_start).total_seconds()

            # Exclude weekends (exact logic as original calculate_cycle_time method)
            weekend_seconds = 0
            current_date = self.work_start
            while current_date <= self.work_end:
                if current_date.weekday() >= 5:  # Saturday (5) or Sunday (6)
                    weekend_seconds += 24 * 60 * 60
                current_date += timedelta(days=1)

            # Return result in seconds (matching original method)
            classification.cycle_time = max(0, total_seconds - weekend_seconds - self.pending_duration)
        else:
            classification.cycle_time = 0

        # Calculate aging metrics for in-progress issues
        if self.current_status == "In Progress" and self.last_in_progress_start is not None:
            now = datetime.now(timezone.utc)
            in_progress_duration = (now - self.last_in_progress_start).total_seconds()
            classification.in_progress_days = in_progress_duration / (24 * 3600)

            # Determine if issue is aged based on type threshold
            threshold = AGING_THRESHOLDS.get(issue_type, 14)
            classification.is_aged = classification.in_progress_days > threshold

        # Determine validity and exclusions
        has_sprint_work = self.start_sprint and self.was_resolved

        if has_sprint_work:
            classification.valid = True
            classification.delivered_in_sprint = self.start_sprint == self.end_sprint

            # Check for mid-sprint removal
            classification.removed_before_midpoint = self._was_removed_before_midpoint()

            # Exclude if removed before midpoint
            if classification.removed_before_midpoint:
                classification.should_exclude = True

        return classification

    def _was_removed_before_midpoint(self) -> bool:
        """Check if issue was removed from starting sprint before midpoint"""
        if not self.start_sprint or self.start_sprint not in self.sprint_removals:
            return False

        removal_time = self.sprint_removals[self.start_sprint]
        assignment_time = self.sprint_assignments.get(self.start_sprint)

        # Only consider removals that happened after assignment
        if assignment_time is not None and removal_time.date() <= assignment_time.date():
            return False

        # Find sprint info and calculate midpoint
        sprint_info = next((s for s in self.parsed_sprints if s.get('name') == self.start_sprint), None)
        if not sprint_info or not sprint_info.get('startDate'):
            return False

        end_date = sprint_info.get('completeDate') or sprint_info.get('endDate')
        if not end_date:
            return False

        sprint_duration = end_date - sprint_info['startDate']
        midpoint = sprint_info['startDate'] + (sprint_duration / 2)

        return removal_time.date() < midpoint.date()


class IssueClassifier:
    """Centralized issue classification logic"""
    def __init__(self, parsed_sprints: List[Dict[str, Any]]) -> None:
        self.parsed_sprints: List[Dict[str, Any]] = parsed_sprints

    def classify_issue(self, changelog_response: Dict[str, Any]) -> IssueClassification:
        """Single method that determines all metrics for an issue"""
        # Extract issue type
        issue_type = changelog_response["fields"]["issuetype"]["name"]

        # Extract timeline events
        events = self._extract_timeline_events(changelog_response)

        # Process events through state machine
        state = IssueState(self.parsed_sprints)
        for event in events:
            if isinstance(event, StatusEvent):
                state.handle_status_change(event)
            elif isinstance(event, SprintEvent):
                state.handle_sprint_change(event)

        return state.get_final_classification(issue_type)

    def _extract_timeline_events(self, changelog_response: Dict[str, Any]) -> List[Event]:
        """Extract all relevant events in chronological order"""
        events = []

        for history in changelog_response["changelog"]["histories"]:
            timestamp = datetime.strptime(history["created"], "%Y-%m-%dT%H:%M:%S.%f%z")

            for item in history["items"]:
                if item["field"] == "status":
                    # Match to sprint at this timestamp
                    sprint = self._get_sprint_at_time(timestamp)
                    events.append(StatusEvent(
                        timestamp=timestamp,
                        from_status=item.get("fromString", ""),
                        to_status=item.get("toString", ""),
                        sprint=sprint
                    ))

                elif item["field"] == JIRA_CONFIG['SPRINT_CUSTOM_FIELD']:
                    # Parse sprint changes
                    from_sprints = self._parse_sprint_list(item.get("fromString", ""))
                    to_sprints = self._parse_sprint_list(item.get("toString", ""))

                    # Generate add/remove events
                    for sprint in to_sprints:
                        if sprint not in from_sprints:
                            events.append(SprintEvent(timestamp, "added", sprint))

                    for sprint in from_sprints:
                        if sprint not in to_sprints:
                            events.append(SprintEvent(timestamp, "removed", sprint))

        return sorted(events, key=lambda e: e.timestamp)

    def _get_sprint_at_time(self, timestamp: datetime) -> Optional[str]:
        """Get the active sprint at a given timestamp"""
        ts = timestamp
        sprint = next((s for s in self.parsed_sprints
                      if s.get("startDate") and (s.get("completeDate") or s.get("endDate")) and
                      s["startDate"].date() <= ts.date() <= (s.get("completeDate") or s["endDate"]).date()), None)
        return sprint["name"] if sprint else None

    def _parse_sprint_list(self, sprint_string: str) -> List[str]:
        """Parse sprint names from comma-separated string"""
        if not sprint_string:
            return []
        sprint_names = []
        for part in sprint_string.split(','):
            part = part.strip()
            if 'name=' in part:
                name_start = part.find('name=') + 5
                name_end = part.find(',', name_start)
                if name_end == -1:
                    name_end = part.find(']', name_start)
                if name_end == -1:
                    name_end = len(part)
                sprint_names.append(part[name_start:name_end].strip())
            elif part and not part.startswith('['):
                sprint_names.append(part)
        return sprint_names