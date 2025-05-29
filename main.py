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

jira = JiraTools(JIRA_USERNAME, JIRA_PASSWORD, JIRA_URL, PROXIES, args.debug)

###
# LOADING STATE
###

state = State.load_state()
if state is not None:
    issues = state.issues
    print("Loaded state!")

###
# MAIN
###

try:
    if state is None:
        print("Fetching issues...")
        issues = jira.get_all_issues(args.project, TEAMS_STRING, args.skew, args.jql)
        state = State(issues)

    TOTAL_ISSUES = len(issues)
    i = 0
    for issue in issues:
        i += 1
        print(f"\rProgress: {i}/{TOTAL_ISSUES} | Valid: {state.get_total_valid_issues()}", end="", flush=True)
        if issue["key"] in state.parsed_issues:
            continue

        issue_info = jira.check_issue_resolution_in_sprint(issue)
        if issue_info is not None:
            if issue_info.delivered_in_sprint:
                state.add_delivered(issue_info.story_points)
            else:
                state.add_carryover(issue_info.story_points)

            state.add_issue_cycle_time(issue_info.issue_type, issue_info.cycle_time)

        state.add_parsed_issue(issue["key"])
        state.persist_state()

    if state.get_total_valid_issues() == 0:
        print("No issues found.")
    else:
        state.print_stats()
        State.clear_state()

except requests.exceptions.RequestException as e:
    print(f"Error making request to Jira: {e}")
