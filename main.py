"""
Get completed vs. delivered
"""

import asyncio
from pathlib import Path
import sys

from tqdm.asyncio import tqdm

from arg_parser import parse_args_interactive
from jira_tools import JiraTools
from state_manager import State

async def main() -> None:
    """Main function"""
    args = parse_args_interactive()

    jira_url = args.url

    jira_token = ""
    with open(args.auth, encoding='utf-8') as f:
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
        try:
            issues = await jira.get_all_issues(args.project, teams_string, args.skew, args.interval, args.jql)
        except Exception as e: # pylint: disable=broad-excep
            print(f"Error fetching issues from Jira: {e}")
            return
        state = State(issues, args)
    else:
        # If state exists, get issues from state
        issues = state.issues

    tasks = [jira.check_issue_resolution_in_sprint(issue) for issue in issues if issue["key"] not in state.parsed_issues]

    try:
        for routine in tqdm(asyncio.as_completed(tasks), initial=len(issues)-len(tasks), total=len(issues), file=sys.stdout):
            issue_info = await routine

            # Process valid issues for delivered/carryover metrics
            if (issue_info.valid and not issue_info.removed_before_midpoint and
                issue_info.story_points is not None and issue_info.issue_type is not None and
                issue_info.key is not None):

                # Add to delivered/carryover metrics
                if issue_info.delivered_in_sprint:
                    state.add_delivered(issue_info.story_points, issue_info.query_month)
                else:
                    state.add_carryover(issue_info.story_points, issue_info.query_month)

                # Add cycle time metrics
                if issue_info.cycle_time is not None and issue_info.cycle_time > 0:
                    state.add_issue_cycle_time(issue_info.key, issue_info.issue_type, issue_info.cycle_time, issue_info.story_points, issue_info.query_month)

            # Process aging metrics for in-progress issues
            if (issue_info.in_progress_days is not None and
                issue_info.issue_type is not None and
                issue_info.story_points is not None and
                issue_info.key is not None):
                state.add_aging_item(issue_info.key, issue_info.issue_type, issue_info.in_progress_days, issue_info.is_aged, issue_info.story_points)

            # Always track that we processed this issue
            if issue_info.key is not None:
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
