"""
Get completed vs. delivered
"""

from pathlib import Path
import requests

from arg_parser import create_argument_parser
from jira_tools import JiraTools
from state_manager import State

parser = create_argument_parser()
args = parser.parse_args()

JIRA_URL = args.url

PROXIES = {}
if args.proxy is not None:
    PROXIES = {
        'http': f'{args.proxy}',
        'https': f'{args.proxy}',
    }

JIRA_USERNAME = ""
JIRA_PASSWORD = ""
with open(args.secret, encoding='utf-8') as f:
    JIRA_USERNAME = f.readline().strip()
    JIRA_PASSWORD = f.readline().strip()

TEAMS_STRING = ""
teams_as_file = Path(args.teams)
if teams_as_file.is_file():
    with open(args.teams, encoding='utf-8') as f:
        TEAMS_STRING = f.readline().strip()
else:
    TEAMS_STRING = args.teams

STORY_POINTS = args.story_points

jira = JiraTools(JIRA_USERNAME, JIRA_PASSWORD, JIRA_URL, PROXIES, args.debug)

###
# LOADING STATE
###

state = State.load_state()

DELIVERED_IN_SPRINT = 0
CARRYOVER_IN_SPRINT = 0
TOTAL_ISSUES = 0

parsed_issues = {}

if state is not None:
    issues = state.issues
    parsed_issues = state.parsed_issues
    TOTAL_ISSUES = len(issues)
    DELIVERED_IN_SPRINT = state.delivered
    CARRYOVER_IN_SPRINT = state.carryover
    print("Loaded state!")

###
# MAIN
###

try:
    if state is None:
        print("Fetching issues...")
        issues, TOTAL_ISSUES = jira.get_all_issues(args.project, TEAMS_STRING, args.skew)
        state = State(issues)

    i = 0
    for issue in issues:
        i += 1
        print(f"\rProgress: {i}/{TOTAL_ISSUES} | Valid: {DELIVERED_IN_SPRINT + CARRYOVER_IN_SPRINT}", end="", flush=True)
        if issue["key"] in parsed_issues:
            continue

        resolution = jira.check_issue_resolution_in_sprint(issue)
        if resolution == 1:
            DELIVERED_IN_SPRINT += 1
        elif resolution == 0:
            CARRYOVER_IN_SPRINT += 1

        parsed_issues[issue["key"]] = True
        state.persist_state(parsed_issues, DELIVERED_IN_SPRINT, CARRYOVER_IN_SPRINT)

    if DELIVERED_IN_SPRINT + CARRYOVER_IN_SPRINT == 0:
        print("No issues found.")
    else:
        print()
        ratio = DELIVERED_IN_SPRINT / (DELIVERED_IN_SPRINT + CARRYOVER_IN_SPRINT)
        print(f"Ratio of CD: {(ratio * 100):.2f}%")
        State.clear_state()

except requests.exceptions.RequestException as e:
    print(f"Error making request to Jira: {e}")
