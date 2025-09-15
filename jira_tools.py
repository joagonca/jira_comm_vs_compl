"""
JIRA tools
"""

import asyncio
from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Any, Optional, Union

import httpx

from utils import AGING_THRESHOLDS, JIRA_CONFIG
from sqlite_manager import SQLiteManager

class IssueInfo:
    """Class to return issue info"""
    def __init__(self, key: Optional[str] = None, delivered_in_sprint: Optional[bool] = None,
                 story_points: Optional[Union[int, float]] = None, issue_type: Optional[str] = None,
                 cycle_time: Optional[Union[int, float]] = None, valid: bool = True,
                 in_progress_days: Optional[float] = None, is_aged: bool = False,
                 query_month: Optional[str] = None, removed_before_midpoint: bool = False):
        self.key = key
        self.delivered_in_sprint = delivered_in_sprint
        self.story_points = story_points
        self.issue_type = issue_type
        self.cycle_time = cycle_time
        self.valid = valid
        self.in_progress_days = in_progress_days
        self.is_aged = is_aged
        self.query_month = query_month
        self.removed_before_midpoint = removed_before_midpoint

class Event:
    """Base class for timeline events"""
    def __init__(self, timestamp: datetime) -> None:
        self.timestamp: datetime = timestamp

class StatusEvent(Event):
    """Represents a status transition event"""
    def __init__(self, timestamp: datetime, from_status: str, to_status: str, sprint: Optional[str] = None) -> None:
        super().__init__(timestamp)
        self.from_status: str = from_status
        self.to_status: str = to_status
        self.sprint: Optional[str] = sprint

class SprintEvent(Event):
    """Represents a sprint assignment/removal event"""
    def __init__(self, timestamp: datetime, action: str, sprint: str) -> None:
        super().__init__(timestamp)
        self.action: str = action  # 'added' or 'removed'
        self.sprint: str = sprint

class IssueClassification:
    """Result of issue classification with all metrics"""
    def __init__(self) -> None:
        self.should_exclude: bool = False
        self.delivered_in_sprint: bool = False
        self.removed_before_midpoint: bool = False
        self.cycle_time: float = 0
        self.in_progress_days: Optional[float] = None
        self.is_aged: bool = False
        self.valid: bool = False
        self.work_start: Optional[datetime] = None
        self.work_end: Optional[datetime] = None
        self.current_status: Optional[str] = None
        self.last_in_progress_start: Optional[datetime] = None
        self.pending_duration: float = 0

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
                if self.work_end is None and sprint_info.get('endDate'):
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
            now = datetime.now().replace(tzinfo=None)
            in_progress_duration = (now - self.last_in_progress_start.replace(tzinfo=None)).total_seconds()
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
        if assignment_time is not None and removal_time <= assignment_time:
            return False

        # Find sprint info and calculate midpoint
        sprint_info = next((s for s in self.parsed_sprints if s.get('name') == self.start_sprint), None)
        if not sprint_info or not sprint_info.get('startDate') or not sprint_info.get('endDate'):
            return False

        sprint_duration = sprint_info['endDate'] - sprint_info['startDate']
        midpoint = sprint_info['startDate'] + (sprint_duration / 2)

        return removal_time.replace(tzinfo=None) < midpoint

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
            timestamp = datetime.strptime(history["created"], "%Y-%m-%dT%H:%M:%S.%f%z").replace(tzinfo=None)

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
        ts = timestamp.replace(tzinfo=None)
        sprint = next((s for s in self.parsed_sprints
                      if s.get("startDate") and s.get("endDate") and
                      s["startDate"] <= ts <= s["endDate"]), None)
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

class JiraTools:
    """Class that handles everything JIRA"""
    def __init__(self, token: str, url: str, proxies: Optional[str], debug: bool, max_concurrency: Optional[int] = None):
        self.token = token
        self.url = url
        self.proxies = proxies
        self.debug = debug
        self.max_concurrency = max_concurrency or JIRA_CONFIG['DEFAULT_CONCURRENCY']
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        self.sqlite_manager = SQLiteManager()
        self.debug_files_cleaned = False

    def store_debug_info(self, issue: str, data: Dict[str, Any]) -> None:
        """Saves debug info to disk (level 2 debug) - overwrites existing files"""
        debug_dir = JIRA_CONFIG['DEBUG_DIR']
        os.makedirs(debug_dir, exist_ok=True)
        with open(f"{debug_dir}/{issue}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def clean_debug_files(self) -> None:
        """Clean debug files before starting new run (level 1 debug)"""
        if self.debug >= 1 and not self.debug_files_cleaned:
            debug_dir = JIRA_CONFIG['DEBUG_DIR']
            os.makedirs(debug_dir, exist_ok=True)

            delivered_file = f"{debug_dir}/{JIRA_CONFIG['DEBUG_DELIVERED_FILE']}"
            carryover_file = f"{debug_dir}/{JIRA_CONFIG['DEBUG_CARRYOVER_FILE']}"

            # Remove existing files if they exist
            for file_path in [delivered_file, carryover_file]:
                if os.path.exists(file_path):
                    os.remove(file_path)

            self.debug_files_cleaned = True

    def append_debug_issue(self, issue_key: str, is_delivered: bool) -> None:
        """Append issue key to appropriate debug file (level 1 debug)"""
        if self.debug >= 1:
            self.clean_debug_files()
            debug_dir = JIRA_CONFIG['DEBUG_DIR']
            filename = JIRA_CONFIG['DEBUG_DELIVERED_FILE'] if is_delivered else JIRA_CONFIG['DEBUG_CARRYOVER_FILE']
            with open(f"{debug_dir}/{filename}", "a", encoding="utf-8") as f:
                f.write(f"{issue_key}\n")


    async def jira_request(self, url: str, method: str = 'GET', data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generic function to call JIRA APIs"""
        retries = JIRA_CONFIG['RETRY_COUNT_MULTIPLIER'] * self.max_concurrency
        async with self.semaphore:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.token}'
            }
            async with httpx.AsyncClient(proxy=self.proxies, timeout=JIRA_CONFIG['REQUEST_TIMEOUT']) as client:
                for attempt in range(retries):
                    try:
                        response = await client.request(
                            method,
                            url,
                            json=data,
                            headers=headers
                        )

                        response.raise_for_status()
                        return response.json()

                    except httpx.HTTPStatusError as exc:
                        if attempt >= retries - 1:
                            raise

                        print("\r" + " " * os.get_terminal_size()[0], end="", flush=True)
                        print(f"\rRetrying after error {exc.response.status_code}...", end="", flush=True)
                        await asyncio.sleep(JIRA_CONFIG['RETRY_DELAY'])

                # If we've exhausted all retries without success, raise a more specific error
                raise httpx.RequestError("All retry attempts failed")

    async def get_all_issues(self, project_key: str, teams: str, skew: int, interval: int, custom_jql: str) -> List[Dict[str, Any]]:
        """Get all issues for a specific project, partitioned by month"""
        issues_combo = []

        # Determine the monthly partitions
        if skew > 0:
            if interval > 0:
                # Interval mode: start from (interval + skew - 1) months ago, end at interval months ago
                start_month = interval + skew - 1
                end_month = interval
                monthly_partitions = self.generate_monthly_partitions(start_month, end_month)
            else:
                # Original behavior: last skew months
                monthly_partitions = self.generate_monthly_partitions(skew - 1, 0)
        else:
            # No date filtering, use single query
            monthly_partitions = [None]

        # Fetch issues for each monthly partition
        total_partitions = len(monthly_partitions)
        for i, month_filter in enumerate(monthly_partitions, 1):
            if total_partitions > 1:
                month_display = month_filter['month_key'] if month_filter else 'all'
                print(f"\rFetching issues for {month_display} [{i}/{total_partitions}]...", end="", flush=True)

            month_issues = await self.get_issues_for_month(project_key, teams, custom_jql, month_filter)
            # Add month info to each issue for tracking
            for issue in month_issues:
                issue['query_month'] = month_filter['month_key'] if month_filter else 'all'
            issues_combo.extend(month_issues)

        # Clear the progress line after completion
        if total_partitions > 1:
            print("\r" + " " * 50, end="", flush=True)
            print("\rFetching issues completed.", flush=True)

        return issues_combo

    def generate_monthly_partitions(self, start_month: int, end_month: int) -> List[Dict[str, Any]]:
        """Generate monthly partition filters"""
        partitions = []
        for month_offset in range(start_month, end_month - 1, -1):
            # Calculate the year and month for this offset
            now = datetime.now()
            target_year = now.year
            target_month = now.month - month_offset

            # Handle year rollover
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            while target_month > 12:
                target_month -= 12
                target_year += 1

            month_key = f"{target_year}-{target_month:02d}"
            partitions.append({
                'month_key': month_key,
                'start_month': month_offset,
                'end_month': month_offset
            })
        return partitions

    async def get_issues_for_month(self, project_key: str, teams: str, custom_jql: str, month_filter: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get issues for a specific month partition"""
        issues_combo = []
        issues_url = f'{self.url}/search'

        skew_str = ""
        if month_filter:
            skew_str = f" AND status changed FROM New AND updated >= startOfMonth(-{month_filter['start_month']}) AND updated <= endOfMonth(-{month_filter['end_month']})"

        teams_str = ""
        if teams != "":
            teams_str = f" AND Team in ({teams})"

        start_at = 0
        total = 1

        jql = ""
        if custom_jql != "":
            jql = f"{custom_jql}{teams_str}{skew_str}"
        else:
            jql = f"project={project_key} AND type in (Story, Defect, Bug, Task) AND assignee is not EMPTY{teams_str}{skew_str}"

        while start_at < total:
            response = await self.jira_request(issues_url,
                                    'POST',
                                    data={
                                        'jql': jql,
                                        'maxResults': JIRA_CONFIG['MAX_RESULTS'],
                                        'startAt': start_at,
                                        'fields': [
                                            'key'
                                        ]
                                    })

            total = response['total']
            start_at += JIRA_CONFIG['MAX_RESULTS']

            issues_combo = issues_combo + response['issues']

        return issues_combo

    def parse_sprint_string(self, sprint_string: str) -> Dict[str, Any]:
        """Parsing the custom field that contains sprint information"""
        info = {}
        for part in sprint_string.strip('[]').split(','):
            if '=' in part:
                k, v = part.split('=', 1)
                info[k.strip()] = v.strip()

        if info['state'] == "FUTURE":
            info['startDate'] = info['endDate'] = None
        else:
            if 'startDate' in info:
                info['startDate'] = datetime.strptime(info['startDate'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=None)
            if 'endDate' in info:
                info['endDate'] = datetime.strptime(info['endDate'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=None)

        return info


    async def check_issue_resolution_in_sprint(self, iss: Dict[str, Any]) -> IssueInfo:
        """Validates if issue was solved in the sprint using simplified classifier"""
        issue_info = IssueInfo(key=iss["key"], valid=False, query_month=iss.get('query_month'))

        # Check if issue exists in SQLite first
        changelog_response = self.sqlite_manager.get_issue(iss["key"])
        from_database = True

        if changelog_response is None:
            # Issue not in database, make API call
            changelog_url = f'{self.url}/issue/{iss["key"]}?expand=changelog'
            changelog_response = await self.jira_request(changelog_url)
            from_database = False

        if self.debug >= 2:
            self.store_debug_info(iss["key"], changelog_response)

        sprints_raw = changelog_response["fields"].get(JIRA_CONFIG['SPRINT_CUSTOM_FIELD'], [])
        if sprints_raw is None:
            return issue_info

        # Parse sprints and create classifier
        parsed_sprints = [self.parse_sprint_string(s) for s in sprints_raw if isinstance(s, str)]
        classifier = IssueClassifier(parsed_sprints)

        # Get classification using simplified logic
        classification = classifier.classify_issue(changelog_response)

        # Store issue in SQLite if it was resolved and came from API
        # Only store issues completed more than DB_STORAGE_BUFFER_DAYS ago to avoid storing issues that might be reopened
        if (not from_database and
            classification.work_end is not None and
            classification.work_end < datetime.now().replace(tzinfo=None) - timedelta(days=JIRA_CONFIG['DB_STORAGE_BUFFER_DAYS'])):
            # Use end_sprint from classification for storage
            end_sprint = ""
            for sprint in parsed_sprints:
                if (sprint.get("startDate") and sprint.get("endDate") and
                    sprint["startDate"] <= classification.work_end.replace(tzinfo=None) <= sprint["endDate"]):
                    end_sprint = sprint.get("name", "")
                    break
            self.sqlite_manager.store_issue(iss["key"], changelog_response, end_sprint)

        # Get story points
        story_points = changelog_response["fields"].get(JIRA_CONFIG['STORY_POINTS_CUSTOM_FIELD'], 1.0)
        if story_points is None:
            story_points = 1.0

        issue_type = changelog_response["fields"]["issuetype"]["name"]

        # Populate IssueInfo from classification
        if classification.valid:
            issue_info.story_points = story_points
            issue_info.issue_type = issue_type
            issue_info.cycle_time = classification.cycle_time
            issue_info.delivered_in_sprint = classification.delivered_in_sprint
            issue_info.removed_before_midpoint = classification.removed_before_midpoint
            issue_info.valid = True

            # Level 1 debug: Write to delivered/carryover files
            if not classification.removed_before_midpoint:
                self.append_debug_issue(iss["key"], classification.delivered_in_sprint)

        # Handle in-progress issues
        if classification.in_progress_days is not None:
            issue_info.in_progress_days = classification.in_progress_days
            issue_info.is_aged = classification.is_aged
            issue_info.issue_type = issue_type
            issue_info.story_points = story_points

        return issue_info
