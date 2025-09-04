"""
Get completed vs. delivered
"""

import asyncio
from pathlib import Path
import sys

from tqdm.asyncio import tqdm

from arg_parser import create_argument_parser
from jira_tools import JiraTools
from state_manager import State

async def main():
    """Main function"""
    parser = create_argument_parser()
    args = parser.parse_args()

    jira_url = args.url

    jira_token = ""
    with open(args.secret, encoding='utf-8') as f:
        jira_token = f.readline().strip()

    teams_string = ""
    teams_as_file = Path(args.teams)
    if teams_as_file.is_file():
        with open(args.teams, encoding='utf-8') as f:
            teams_string = f.readline().strip()
    else:
        teams_string = args.teams

    jira = JiraTools(jira_token, jira_url, args.proxy, args.debug)

    state = State.load_state()
    if state is not None and state.command_matches(args):
        issues = state.issues
        print("Loaded state!")
    elif state is not None:
        print("Command differs from saved state. Starting fresh...")
        State.clear_state()
        state = None

    if state is None:
        print("Fetching issues...")
        try:
            issues = await jira.get_all_issues(args.project, teams_string, args.skew, args.interval, args.jql)
        except Exception as e: # pylint: disable=broad-except
            print(f"Error fetching issues from Jira: {e}")
            return
        state = State(issues, args)

    tasks = [jira.check_issue_resolution_in_sprint(issue) for issue in issues if issue["key"] not in state.parsed_issues]

    try:
        for routine in tqdm(asyncio.as_completed(tasks), initial=len(issues)-len(tasks), total=len(issues), file=sys.stdout):
            issue_info = await routine

            if issue_info.valid:
                if issue_info.delivered_in_sprint:
                    state.add_delivered(issue_info.story_points, issue_info.query_month)
                else:
                    state.add_carryover(issue_info.story_points, issue_info.query_month)

                if issue_info.cycle_time > 0:
                    state.add_issue_cycle_time(issue_info.key, issue_info.issue_type, issue_info.cycle_time, issue_info.story_points, issue_info.query_month)

            if issue_info.in_progress_days is not None:
                state.add_aging_item(issue_info.key, issue_info.issue_type, issue_info.in_progress_days, issue_info.is_aged, issue_info.story_points)

            state.add_parsed_issue(issue_info.key)
            state.persist_state()
    except Exception as e: # pylint: disable=broad-except
        print(f"Error processing issues: {e}")
        return

    if state.get_total_valid_issues() == 0:
        print("No issues found.")
    else:
        state.print_stats()
        State.clear_state()

if __name__ == "__main__":
    asyncio.run(main())
