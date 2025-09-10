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

    def store_debug_info(self, issue: str, data: Dict[str, Any]) -> None:
        """Saves debug info to disk"""
        debug_dir = JIRA_CONFIG['DEBUG_DIR']
        os.makedirs(debug_dir, exist_ok=True)
        with open(f"{debug_dir}/{issue}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

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
                end_month = interval - 1
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
                info['startDate'] = datetime.strptime(info['startDate'], "%Y-%m-%dT%H:%M:%S.%fZ")
            if 'endDate' in info:
                info['endDate'] = datetime.strptime(info['endDate'], "%Y-%m-%dT%H:%M:%S.%fZ")

        return info

    def calculate_cycle_time(self, work_start: Optional[datetime], work_end: Optional[datetime], pending_duration: Union[int, float]) -> Union[int, float]:
        """"Calculates item cycle time, taking into account weekends"""
        if work_start is None or work_end is None:
            return 0

        total_seconds = (work_end - work_start).total_seconds()

        weekend_seconds = 0
        current_date = work_start
        while current_date <= work_end:
            if current_date.weekday() >= 5:
                weekend_seconds += 24 * 60 * 60
            current_date += timedelta(days=1)

        return total_seconds - weekend_seconds - pending_duration

    def parse_issue_transitions(self, changelog_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract status transitions from changelog"""
        transitions = []
        for history in changelog_response["changelog"]["histories"]:
            timestamp = datetime.strptime(history["created"], "%Y-%m-%dT%H:%M:%S.%f%z")
            for item in history["items"]:
                if item["field"] == "status":
                    transitions.append({
                        "from": item.get("fromString"),
                        "to": item.get("toString"),
                        "timestamp": timestamp
                    })
        return transitions

    def parse_sprint_changes(self, changelog_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract sprint field changes from changelog"""
        sprint_changes = []
        for history in changelog_response["changelog"]["histories"]:
            timestamp = datetime.strptime(history["created"], "%Y-%m-%dT%H:%M:%S.%f%z")
            for item in history["items"]:
                if item["field"] == JIRA_CONFIG['SPRINT_CUSTOM_FIELD']:
                    from_sprints = self.parse_sprint_list(item.get("fromString", ""))
                    to_sprints = self.parse_sprint_list(item.get("toString", ""))
                    
                    # Determine what changed
                    added_sprints = [s for s in to_sprints if s not in from_sprints]
                    removed_sprints = [s for s in from_sprints if s not in to_sprints]
                    
                    for sprint in added_sprints:
                        sprint_changes.append({
                            "action": "added",
                            "sprint": sprint,
                            "timestamp": timestamp
                        })
                    
                    for sprint in removed_sprints:
                        sprint_changes.append({
                            "action": "removed", 
                            "sprint": sprint,
                            "timestamp": timestamp
                        })
        return sprint_changes
    
    def parse_sprint_list(self, sprint_string: str) -> List[str]:
        """Parse sprint names from comma-separated string"""
        if not sprint_string:
            return []
        # Handle both comma-separated names and sprint object strings
        sprint_names = []
        for part in sprint_string.split(','):
            part = part.strip()
            if 'name=' in part:
                # Extract name from sprint object string like "name=Sprint 1"
                name_start = part.find('name=') + 5
                name_end = part.find(',', name_start)
                if name_end == -1:
                    name_end = part.find(']', name_start)
                if name_end == -1:
                    name_end = len(part)
                sprint_names.append(part[name_start:name_end].strip())
            elif part and not part.startswith('['):
                # Simple comma-separated name
                sprint_names.append(part)
        return sprint_names

    def match_transitions_to_sprints(self, transitions: List[Dict[str, Any]], parsed_sprints: List[Dict[str, Any]]) -> None:
        """Match each transition to a sprint based on timing"""
        for t in transitions:
            ts = t["timestamp"].replace(tzinfo=None)
            sprint = next((s for s in parsed_sprints if s.get("startDate") and s.get("endDate") and s["startDate"] <= ts <= s["endDate"]), None)
            t["state"] = sprint["state"] if sprint else None
            t["sprint"] = sprint["name"] if sprint else None

    def calculate_aging_metrics(self, current_status: Optional[str], last_in_progress_start: Optional[datetime], issue_type: str) -> tuple[Optional[float], bool]:
        """Calculate aging metrics for items currently in progress"""
        if current_status != "In Progress" or last_in_progress_start is None:
            return None, False

        now = datetime.now().replace(tzinfo=None)
        in_progress_duration = (now - last_in_progress_start.replace(tzinfo=None)).total_seconds()
        in_progress_days = in_progress_duration / (24 * 3600)
        
        threshold = AGING_THRESHOLDS.get(issue_type, 14)
        is_aged = in_progress_days > threshold
        
        return in_progress_days, is_aged

    def determine_sprint_delivery(self, transitions: List[Dict[str, Any]], sprint_changes: List[Dict[str, Any]], parsed_sprints: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Determine sprint delivery status and timing from transitions and sprint changes"""
        start_sprint = ""
        end_sprint = ""
        consider = False
        pending_duration = 0
        pending_start = None
        work_start = None
        work_end = None
        last_in_progress_start = None
        current_status = None
        removed_before_midpoint = False
        sprint_assignment_time = None
        sprint_removal_time = None

        # Process status transitions
        for t in transitions:
            if t['to'] == "In Progress":
                start_sprint = t['sprint']
                last_in_progress_start = t['timestamp']
                if work_start is None:
                    work_start = t['timestamp']

                if t['state'] == "CLOSED":
                    consider = True

            if t['to'] == "Resolved":
                end_sprint = t['sprint']
                work_end = t['timestamp']
                consider = True

            if t['to'] == "Pending":
                pending_start = t['timestamp']
            if t['from'] == "Pending":
                pending_duration += (t['timestamp'] - pending_start).total_seconds()
            
            current_status = t['to']

        # Process sprint changes to find assignment/removal relative to work period
        if work_start and start_sprint:
            # Find when the issue was assigned to the starting sprint
            for change in sprint_changes:
                if change['action'] == 'added' and change['sprint'] == start_sprint:
                    if change['timestamp'] <= work_start:
                        # Issue was assigned to sprint before work started (normal case)
                        sprint_assignment_time = change['timestamp']
                    elif work_end and change['timestamp'] <= work_end:
                        # Issue was assigned to sprint after work started but before completion
                        sprint_assignment_time = change['timestamp']
                        start_sprint = change['sprint']  # Update start sprint to actual assignment

            # Find if the issue was removed from the starting sprint before midpoint
            for change in sprint_changes:
                if (change['action'] == 'removed' and 
                    change['sprint'] == start_sprint and 
                    sprint_assignment_time and 
                    change['timestamp'] > sprint_assignment_time):
                    
                    sprint_removal_time = change['timestamp']
                    
                    # Check if removal was before sprint midpoint
                    sprint_info = next((s for s in parsed_sprints if s.get('name') == start_sprint), None)
                    if sprint_info and sprint_info.get('startDate') and sprint_info.get('endDate'):
                        sprint_duration = sprint_info['endDate'] - sprint_info['startDate']
                        midpoint = sprint_info['startDate'] + (sprint_duration / 2)
                        removed_before_midpoint = change['timestamp'].replace(tzinfo=None) < midpoint
                    break

        return {
            'start_sprint': start_sprint,
            'end_sprint': end_sprint,
            'consider': consider,
            'work_start': work_start,
            'work_end': work_end,
            'pending_duration': pending_duration,
            'last_in_progress_start': last_in_progress_start,
            'current_status': current_status,
            'removed_before_midpoint': removed_before_midpoint,
            'sprint_assignment_time': sprint_assignment_time,
            'sprint_removal_time': sprint_removal_time
        }

    async def check_issue_resolution_in_sprint(self, iss: Dict[str, Any]) -> IssueInfo:
        """Validates if issue was solved in the sprint"""
        issue_info = IssueInfo(key=iss["key"], valid=False, query_month=iss.get('query_month'))
        
        # Check if issue exists in SQLite first
        changelog_response = self.sqlite_manager.get_issue(iss["key"])
        from_database = True
        
        if changelog_response is None:
            # Issue not in database, make API call
            changelog_url = f'{self.url}/issue/{iss["key"]}?expand=changelog'
            changelog_response = await self.jira_request(changelog_url)
            from_database = False
        
        issue_type = changelog_response["fields"]["issuetype"]["name"]

        if self.debug:
            self.store_debug_info(iss["key"], changelog_response)

        sprints_raw = changelog_response["fields"].get(JIRA_CONFIG['SPRINT_CUSTOM_FIELD'], [])
        if sprints_raw is None:
            return issue_info

        parsed_sprints = [self.parse_sprint_string(s) for s in sprints_raw if isinstance(s, str)]
        transitions = self.parse_issue_transitions(changelog_response)
        sprint_changes = self.parse_sprint_changes(changelog_response)
        self.match_transitions_to_sprints(transitions, parsed_sprints)
        
        delivery_info = self.determine_sprint_delivery(transitions, sprint_changes, parsed_sprints)
        
        # Store issue in SQLite if it has an end_sprint and came from API (not from database)
        if not from_database:
            self.sqlite_manager.store_issue(iss["key"], changelog_response, delivery_info['end_sprint'])
        
        story_points = changelog_response["fields"].get(JIRA_CONFIG['STORY_POINTS_CUSTOM_FIELD'], 1.0)
        if story_points is None:
            story_points = 1.0

        cycle_time = self.calculate_cycle_time(delivery_info['work_start'], delivery_info['work_end'], delivery_info['pending_duration'])
        in_progress_days, is_aged = self.calculate_aging_metrics(delivery_info['current_status'], delivery_info['last_in_progress_start'], issue_type)

        if delivery_info['start_sprint'] != "" and delivery_info['consider']:
            issue_info.story_points = story_points
            issue_info.issue_type = issue_type
            issue_info.cycle_time = cycle_time
            issue_info.delivered_in_sprint = delivery_info['start_sprint'] == delivery_info['end_sprint']
            issue_info.removed_before_midpoint = delivery_info['removed_before_midpoint']
            issue_info.valid = True

        if delivery_info['current_status'] == "In Progress":
            issue_info.in_progress_days = in_progress_days
            issue_info.is_aged = is_aged
            issue_info.issue_type = issue_type
            issue_info.story_points = story_points

        return issue_info
