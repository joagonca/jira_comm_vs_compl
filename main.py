"""
Get completed vs. delivered
"""

import argparse
from datetime import datetime
import time
import requests

PROXIES = {}

JIRA_URL = ""
MAX_RESULTS = 1000

JIRA_USERNAME = ""
JIRA_PASSWORD = ""

TEAMS_STRING = ""

SPRINT_CUSTOM_FIELD = "customfield_10000"

DELIVERED_IN_SPRINT = 0
CARRYOVER_IN_SPRINT = 0
TOTAL_ISSUES = 0

def jira_request(url, method='GET', data=None):
    """Generic function to call JIRA APIs"""
    headers = {
        'Content-Type': 'application/json'
    }

    status = 0
    response = None

    while status != 200:
        response = requests.request(method,
                                    url,
                                    headers=headers,
                                    json=data,
                                    auth=(JIRA_USERNAME, JIRA_PASSWORD),
                                    proxies=PROXIES,
                                    timeout=60)

        status = response.status_code
        if status != 200:
            print(f"\rTimed out, sleeping for 30 seconds...", end="", flush=True)
            time.sleep(30)

    return response.json()

def get_all_issues(project_key):
    """Get all issues for a specific project"""
    global TOTAL_ISSUES

    issues_combo = []
    issues_url = f'{JIRA_URL}/search'

    start_at = 0
    total = 1

    while start_at < total:
        response = jira_request(issues_url,
                                'POST',
                                data={
                                    'jql': f"project={project_key} AND Team in ({TEAMS_STRING}) AND (type=Story OR type=Defect OR type=Task) AND Sprint is not EMPTY",
                                    'maxResults': MAX_RESULTS,
                                    'startAt': start_at,
                                    'fields': [
                                        'key'
                                    ]
                                })

        total = response['total']
        start_at += MAX_RESULTS

        issues_combo =  issues_combo + response['issues']

    TOTAL_ISSUES = total
    return issues_combo

def parse_sprint_string(sprint_string):
    """Parsing the custom field that contains sprint information"""
    info = {}
    for part in sprint_string.strip('[]').split(','):
        if '=' in part:
            k, v = part.split('=', 1)
            info[k.strip()] = v.strip()

    if 'startDate' in info:
        info['startDate'] = datetime.strptime(info['startDate'], "%Y-%m-%dT%H:%M:%S.%fZ")
    if 'endDate' in info:
        info['endDate'] = datetime.strptime(info['endDate'], "%Y-%m-%dT%H:%M:%S.%fZ")
    return info

def check_issue_resolution_in_sprint(issue):
    """Validates if issue was solved in the sprint"""
    global DELIVERED_IN_SPRINT
    global CARRYOVER_IN_SPRINT

    changelog_url = f'{JIRA_URL}/issue/{issue["key"]}?expand=changelog'
    changelog_response = jira_request(changelog_url)

    sprints_raw = changelog_response["fields"].get(SPRINT_CUSTOM_FIELD, [])
    parsed_sprints = [parse_sprint_string(s) for s in sprints_raw if isinstance(s, str)]

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
        t["sprint"] = sprint["name"] if sprint else None

    start_sprint = ""
    end_sprint = ""
    for t in transitions:
#        print(f"{t['timestamp']} | {t['from']} ➜ {t['to']} | Sprint: {t['sprint']}")
        if t['to'] == "In Progress":
            start_sprint = t['sprint']
        if t['to'] == "Resolved":
            end_sprint = t['sprint']

    if start_sprint != "":
        if start_sprint == end_sprint:
            DELIVERED_IN_SPRINT += 1
        else:
            CARRYOVER_IN_SPRINT += 1

    return False

parser = argparse.ArgumentParser(
    prog='jira_stats',
    description='Get JIRA stats for teams',
    epilog='CFK ♥ 2025'
)

parser.add_argument('--proxy',
                    dest='proxy',
                    help='If a proxy is to be used to reach out to JIRA')

parser.add_argument('-u', '--url',
                    dest='url',
                    required=True,
                    help='JIRA API URL')

parser.add_argument('-p', '--project',
                    dest='project',
                    required=True,
                    help='JIRA Project key to target')

parser.add_argument('-t', '--teams',
                    dest='teams',
                    required=True,
                    help='JIRA Teams to filter')

parser.add_argument('-s', '--secret',
                    dest='secret',
                    required=True,
                    help='file with your user and password information (1st line: user 2nd line: password)')

args = parser.parse_args()

JIRA_URL = args.url

if args.proxy is not None:
    PROXIES = {
        'http': f'{args.proxy}',
        'https': f'{args.proxy}',
    }

with open(args.secret, encoding='utf-8') as f:
    JIRA_USERNAME = f.readline().strip()
    JIRA_PASSWORD = f.readline().strip()

with open(args.teams, encoding='utf-8') as f:
    TEAMS_STRING = f.readline().strip()

try:
    # Fetch all issues from the project
    print("Fetching issues...")
    issues = get_all_issues(args.project)

    i = 0
    for issue in issues:
        i += 1
        print(f"\r{i}/{TOTAL_ISSUES}", end="", flush=True)
        check_issue_resolution_in_sprint(issue)
    
    print()
    ratio = DELIVERED_IN_SPRINT / (DELIVERED_IN_SPRINT + CARRYOVER_IN_SPRINT)
    print(f"Ratio of CD: {ratio}")

except requests.exceptions.RequestException as e:
    print(f"Error making request to Jira: {e}")
