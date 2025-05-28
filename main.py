"""
Get completed vs. delivered
"""

from datetime import datetime
from pathlib import Path
import time
import requests

from arg_parser import create_argument_parser
from state_manager import State

PROXIES = {}

JIRA_URL = ""
MAX_RESULTS = 1000

JIRA_USERNAME = ""
JIRA_PASSWORD = ""

TEAMS_STRING = ""

SPRINT_CUSTOM_FIELD = "customfield_10000"

def jira_request(url, method='GET', data=None):
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
                                    auth=(JIRA_USERNAME, JIRA_PASSWORD),
                                    proxies=PROXIES,
                                    timeout=60)

        status = response.status_code
        if status != 200:
            error_count += 1
            if error_count > 3:
                response.raise_for_status()

            print("\r                                                             ", end="", flush=True)
            print("\rErrored out, sleeping for 30 seconds...", end="", flush=True)
            time.sleep(30)
            print("\r                                                             ", end="", flush=True)

    return response.json()

def get_all_issues(project_key, skew):
    """Get all issues for a specific project"""
    issues_combo = []
    issues_url = f'{JIRA_URL}/search'

    skew_str = ""
    if skew > 0:
        skew_str = f" AND updated >= startOfMonth(-{skew-1})"

    start_at = 0
    total = 1

    while start_at < total:
        response = jira_request(issues_url,
                                'POST',
                                data={
                                    'jql': f"project={project_key} AND Team in ({TEAMS_STRING}) AND (type=Story OR type=Defect OR type=Task) AND Sprint is not EMPTY{skew_str}",
                                    'maxResults': MAX_RESULTS,
                                    'startAt': start_at,
                                    'fields': [
                                        'key'
                                    ]
                                })

        total = response['total']
        start_at += MAX_RESULTS

        issues_combo =  issues_combo + response['issues']

    return issues_combo, total

def parse_sprint_string(sprint_string):
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

def check_issue_resolution_in_sprint(iss):
    """Validates if issue was solved in the sprint"""
    changelog_url = f'{JIRA_URL}/issue/{iss["key"]}?expand=changelog'
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
        t["state"] = sprint["state"] if sprint else None
        t["sprint"] = sprint["name"] if sprint else None

    start_sprint = ""
    end_sprint = ""
    consider = False
    for t in transitions:
        if t['to'] == "In Progress":
            start_sprint = t['sprint']
            if t['state'] == "CLOSED":
                consider = True

        if t['to'] == "Resolved":
            end_sprint = t['sprint']
            consider = True

    if start_sprint != "" and consider:
        if start_sprint == end_sprint:
            return 1
        else:
            return 0

    return -1

###
# MAIN
###

parser = create_argument_parser()
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

teams_as_file = Path(args.teams)
if teams_as_file.is_file():
    with open(args.teams, encoding='utf-8') as f:
        TEAMS_STRING = f.readline().strip()
else:
    TEAMS_STRING = args.teams

###
# LOADING STATE
###

STATE = State.load_state()

DELIVERED_IN_SPRINT = 0
CARRYOVER_IN_SPRINT = 0
TOTAL_ISSUES = 0

parsed_issues = {}

if STATE is not None:
    issues = STATE.issues
    parsed_issues = STATE.parsed_issues
    TOTAL_ISSUES = len(issues)
    DELIVERED_IN_SPRINT = STATE.delivered
    CARRYOVER_IN_SPRINT = STATE.carryover
    print("Loaded state!")

###
# MAIN
###

try:
    if STATE is None:
        print("Fetching issues...")
        issues, TOTAL_ISSUES = get_all_issues(args.project, args.skew)
        STATE = State(issues)

    i = 0
    for issue in issues:
        i += 1
        print(f"\rProgress: {i}/{TOTAL_ISSUES} | Valid: {DELIVERED_IN_SPRINT + CARRYOVER_IN_SPRINT}", end="", flush=True)
        if issue["key"] in parsed_issues:
            continue

        resolution = check_issue_resolution_in_sprint(issue)
        if resolution == 1:
            DELIVERED_IN_SPRINT += 1
        elif resolution == 0:
            CARRYOVER_IN_SPRINT += 1

        parsed_issues[issue["key"]] = True
        STATE.persist_state(parsed_issues, DELIVERED_IN_SPRINT, CARRYOVER_IN_SPRINT)

    if DELIVERED_IN_SPRINT + CARRYOVER_IN_SPRINT == 0:
        print("No issues found.")
    else:
        print()
        ratio = DELIVERED_IN_SPRINT / (DELIVERED_IN_SPRINT + CARRYOVER_IN_SPRINT)
        print(f"Ratio of CD: {(ratio * 100):.2f}%")
        State.clear_state()

except requests.exceptions.RequestException as e:
    print(f"Error making request to Jira: {e}")
