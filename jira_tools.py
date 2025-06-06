"""
JIRA tools
"""

from datetime import datetime, timedelta
import json
import os
import time

import requests

MAX_RESULTS = 1000
SPRINT_CUSTOM_FIELD = "customfield_10000"
STORY_POINTS_CUSTOM_FIELD = "customfield_10006"

DEBUG_DIR = "debug"

class IssueInfo:
    """Class to return issue info"""
    def __init__(self, delivered_in_sprint, story_points, issue_type, cycle_time):
        self.delivered_in_sprint = delivered_in_sprint
        self.story_points = story_points
        self.issue_type = issue_type
        self.cycle_time = cycle_time

class JiraTools:
    """Class that handles everything JIRA"""
    def __init__(self, user, password, url, proxies, debug):
        self.user = user
        self.password = password
        self.url = url
        self.proxies = {} if proxies is None else proxies
        self.debug = debug

    def store_debug_info(self, issue, data):
        """Saves debug info to disk"""
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(f"{DEBUG_DIR}/{issue}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def jira_request(self, url, method='GET', data=None):
        """Generic function to call JIRA APIs"""
        headers = {
            'Content-Type': 'application/json'
        }

        status = 0
        error_count = 0
        response = None

        while status != 200:
            response = requests.request(method,
                                        url,
                                        headers=headers,
                                        json=data,
                                        auth=(self.user, self.password),
                                        proxies=self.proxies,
                                        timeout=60)

            status = response.status_code
            if status != 200:
                error_count += 1
                if error_count > 3:
                    response.raise_for_status()

                print("\r" + " " * os.get_terminal_size()[0], end="", flush=True)
                print("\rErrored out, sleeping for 30 seconds...", end="", flush=True)
                time.sleep(30)

        return response.json()

    def get_all_issues(self, project_key, teams, skew, custom_jql):
        """Get all issues for a specific project"""
        issues_combo = []
        issues_url = f'{self.url}/search'

        skew_str = ""
        if skew > 0:
            skew_str = f" AND updated >= startOfMonth(-{skew-1})"

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
            response = self.jira_request(issues_url,
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

    def check_issue_resolution_in_sprint(self, iss):
        """Validates if issue was solved in the sprint"""
        changelog_url = f'{self.url}/issue/{iss["key"]}?expand=changelog'
        changelog_response = self.jira_request(changelog_url)
        issue_type = changelog_response["fields"]["issuetype"]["name"]

        if self.debug:
            self.store_debug_info(iss["key"], changelog_response)

        sprints_raw = changelog_response["fields"].get(SPRINT_CUSTOM_FIELD, [])
        if sprints_raw is None:
            return None

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

        for t in transitions:
            if t['to'] == "In Progress":
                start_sprint = t['sprint']
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

        story_points = changelog_response["fields"].get(STORY_POINTS_CUSTOM_FIELD, 1.0)
        if story_points is None:
            story_points = 1.0

        cycle_time = self.calculate_cycle_time(work_start, work_end, pending_duration)

        if start_sprint != "" and consider:
            if start_sprint == end_sprint:
                return IssueInfo(True, story_points, issue_type, cycle_time)
            else:
                return IssueInfo(False, story_points, issue_type, cycle_time)

        return None
