"""
JIRA HTTP client and API operations
"""

import asyncio
from datetime import datetime, timedelta, timezone
import os
from typing import Dict, List, Any, Optional

import httpx

from .models import IssueInfo
from .classifier import IssueClassifier
from .debug import DebugManager
from utils import JIRA_CONFIG
from sqlite_manager import SQLiteManager


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
        self.debug_manager = DebugManager(debug)

    def store_debug_info(self, issue: str, data: Dict[str, Any]) -> None:
        """Saves debug info to disk (level 2 debug) - overwrites existing files"""
        self.debug_manager.store_debug_info(issue, data)

    def clean_debug_files(self) -> None:
        """Clean debug files before starting new run (level 1 debug)"""
        self.debug_manager.clean_debug_files()

    def append_debug_issue(self, issue_key: str, is_delivered: bool) -> None:
        """Append issue key to appropriate debug file (level 1 debug)"""
        self.debug_manager.append_debug_issue(issue_key, is_delivered)

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

    def extract_team_names_from_issues(self, issues: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extract team names from fetched issues"""
        team_map = {}
        
        for issue in issues:
            team_field = issue.get('fields', {}).get('Team')
            
            if isinstance(team_field, list):
                for team in team_field:
                    if isinstance(team, dict) and 'id' in team and 'name' in team:
                        team_id = str(team['id'])
                        if team_id not in team_map:
                            team_map[team_id] = team['name']
            elif isinstance(team_field, dict) and 'id' in team_field and 'name' in team_field:
                team_id = str(team_field['id'])
                if team_id not in team_map:
                    team_map[team_id] = team_field['name']
                
        return team_map

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
            if total_partitions >= 1:
                month_display = month_filter['month_key'] if month_filter else 'all'
                print(f"\rFetching issues for {month_display} [{i}/{total_partitions}]...", end="", flush=True)

            month_issues = await self.get_issues_for_month(project_key, teams, custom_jql, month_filter)
            # Add month info to each issue for tracking
            for issue in month_issues:
                issue['query_month'] = month_filter['month_key'] if month_filter else 'all'
            issues_combo.extend(month_issues)

        # Clear the progress line after completion
        if total_partitions >= 1:
            print("\r" + " " * 50, end="", flush=True)
            print("\rFetching issues completed.", flush=True)

        return issues_combo

    def generate_monthly_partitions(self, start_month: int, end_month: int) -> List[Dict[str, Any]]:
        """Generate monthly partition filters"""
        partitions = []
        for month_offset in range(start_month, end_month - 1, -1):
            # Calculate the year and month for this offset
            now = datetime.now(timezone.utc)
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
                                            'key',
                                            'Team'
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
            for date_field in ['startDate', 'endDate', 'completeDate']:
                if info.get(date_field):
                    try:
                        info[date_field] = datetime.strptime(info[date_field], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        info[date_field] = None
                else:
                    info[date_field] = None

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
            classification.work_end < datetime.now(timezone.utc) - timedelta(days=JIRA_CONFIG['DB_STORAGE_BUFFER_DAYS'])):
            # Use end_sprint from classification for storage
            end_sprint = ""
            for sprint in parsed_sprints:
                end_date = sprint.get("completeDate") or sprint.get("endDate")
                if (sprint.get("startDate") and end_date and
                    sprint["startDate"].date() <= classification.work_end.date() <= end_date.date()):
                    end_sprint = sprint.get("name", "")
                    break

            if end_sprint and end_sprint != "":
                self.sqlite_manager.store_issue(iss["key"], changelog_response)

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