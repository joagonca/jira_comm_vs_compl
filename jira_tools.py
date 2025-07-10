"""
JIRA tools
"""

import asyncio
from datetime import datetime, timedelta
import json
import os

import httpx

MAX_RESULTS = 1000
SPRINT_CUSTOM_FIELD = "customfield_10000"
STORY_POINTS_CUSTOM_FIELD = "customfield_10006"

DEBUG_DIR = "debug"

class IssueInfo:
    """Class to return issue info"""
    def __init__(self, key=None, delivered_in_sprint=None, story_points=None, issue_type=None, cycle_time=None, valid=True):
        self.key = key
        self.delivered_in_sprint = delivered_in_sprint
        self.story_points = story_points
        self.issue_type = issue_type
        self.cycle_time = cycle_time
        self.valid = valid
        self.outside_sprint_transitions = False

class JiraTools:
    """Class that handles everything JIRA"""
    def __init__(self, user, password, url, proxies, debug, max_concurrency=5):
        self.user = user
        self.password = password
        self.url = url
        self.proxies = proxies
        self.debug = debug
        self.semaphore = asyncio.Semaphore(max_concurrency)

    def store_debug_info(self, issue, data):
        """Saves debug info to disk"""
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(f"{DEBUG_DIR}/{issue}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    async def jira_request(self, url, method='GET', data=None):
        """Generic function to call JIRA APIs"""
        retries = 3
        async with self.semaphore:
            async with httpx.AsyncClient(proxy=self.proxies, timeout=60, auth=(self.user, self.password)) as client:
                for attempt in range(retries):
                    try:
                        response = await client.request(
                            method,
                            url,
                            json=data,
                            headers={'Content-Type': 'application/json'}
                        )

                        response.raise_for_status()
                        return response.json()

                    except httpx.HTTPStatusError as exc:
                        if attempt >= retries - 1:
                            raise

                        print("\r" + " " * os.get_terminal_size()[0], end="", flush=True)
                        print(f"\rRetrying after error {exc.response.status_code}...", end="", flush=True)
                        await asyncio.sleep(30)

    async def get_all_issues(self, project_key, teams, skew, interval, custom_jql):
        """Get all issues for a specific project"""
        issues_combo = []
        issues_url = f'{self.url}/search'

        skew_str = ""
        if skew > 0:
            if interval > 0:
                # Interval mode: start from (interval + skew - 1) months ago, end at interval months ago
                start_month = interval + skew - 1
                end_month = interval - 1
                skew_str = f" AND status changed FROM New AND updated >= startOfMonth(-{start_month}) AND updated <= endOfMonth(-{end_month})"
            else:
                # Original behavior: last skew months
                skew_str = f" AND status changed FROM New AND updated >= startOfMonth(-{skew-1})"

        teams_str = ""
        if teams != "":
            teams_str = f" AND Team in ({teams})"

        start_at = 0
        total = 1

        jql = ""
        if custom_jql != "":
            jql = f"{custom_jql}{teams_str}{skew_str}"
        else:
            jql = f"project={project_key} AND type in (Story, Defect, Task) AND assignee is not EMPTY{teams_str}{skew_str}"

        while start_at < total:
            response = await self.jira_request(issues_url,
                                    'POST',
                                    data={
                                        'jql': jql,
                                        'maxResults': MAX_RESULTS,
                                        'startAt': start_at,
                                        'fields': [
                                            'key'
                                        ]
                                    })

            total = response['total']
            start_at += MAX_RESULTS

            issues_combo =  issues_combo + response['issues']

        return issues_combo

    def parse_sprint_string(self, sprint_string):
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

    def calculate_cycle_time(self, work_start, work_end, pending_duration):
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

    async def check_issue_resolution_in_sprint(self, iss):
        """Validates if issue was solved in the sprint"""
        changelog_url = f'{self.url}/issue/{iss["key"]}?expand=changelog'
        changelog_response = await self.jira_request(changelog_url)
        issue_type = changelog_response["fields"]["issuetype"]["name"]

        issue_info = IssueInfo(key=iss["key"], valid=False)

        if self.debug:
            self.store_debug_info(iss["key"], changelog_response)

        sprints_raw = changelog_response["fields"].get(SPRINT_CUSTOM_FIELD, [])
        if sprints_raw is None:
            return issue_info

        parsed_sprints = [self.parse_sprint_string(s) for s in sprints_raw if isinstance(s, str)]

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

        # Match each transition to a sprint
        for t in transitions:
            ts = t["timestamp"].replace(tzinfo=None)
            sprint = next((s for s in parsed_sprints if s.get("startDate") and s.get("endDate") and s["startDate"] <= ts <= s["endDate"]), None)
            t["state"] = sprint["state"] if sprint else None
            t["sprint"] = sprint["name"] if sprint else None

        start_sprint = ""
        end_sprint = ""
        consider = False

        pending_duration = 0
        pending_start = None
        work_start = None
        work_end = None
        outside_sprint_transitions = False

        for t in transitions:
            if t['to'] == "In Progress":
                start_sprint = t['sprint']
                if work_start is None:
                    work_start = t['timestamp']

                if t['state'] == "CLOSED":
                    consider = True

                if t['sprint'] is None:
                    outside_sprint_transitions = True

            if t['to'] == "Resolved":
                end_sprint = t['sprint']
                work_end = t['timestamp']
                consider = True

                if t['sprint'] is None:
                    outside_sprint_transitions = True

            if t['to'] == "Closed":
                if t['sprint'] is None:
                    outside_sprint_transitions = True

            if t['to'] == "Pending":
                pending_start = t['timestamp']
            if t['from'] == "Pending":
                pending_duration += (t['timestamp'] - pending_start).total_seconds()

        story_points = changelog_response["fields"].get(STORY_POINTS_CUSTOM_FIELD, 1.0)
        if story_points is None:
            story_points = 1.0

        cycle_time = self.calculate_cycle_time(work_start, work_end, pending_duration)

        if start_sprint != "" and consider:
            issue_info.story_points = story_points
            issue_info.issue_type = issue_type
            issue_info.cycle_time = cycle_time
            issue_info.delivered_in_sprint = start_sprint == end_sprint
            issue_info.valid = True

        issue_info.outside_sprint_transitions = outside_sprint_transitions

        return issue_info
