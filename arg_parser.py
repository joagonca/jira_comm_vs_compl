"""
Argument parser
"""

import argparse
import sys
from pathlib import Path

def create_argument_parser() -> argparse.ArgumentParser:
    """Creates and configures an argument parser"""
    parser = argparse.ArgumentParser(
        prog='jira_stats',
        description='Get JIRA stats for teams',
        epilog='CFK ♥ 2025'
    )

    parser.add_argument('--debug', '-d',
                        dest='debug',
                        action='count',
                        default=0,
                        help='Debug level: -d for basic, -dd for verbose')

    parser.add_argument('--proxy',
                        dest='proxy',
                        help='If a proxy is to be used to reach out to JIRA')

    parser.add_argument('-u', '--url',
                        dest='url',
                        required=True,
                        help='JIRA API URL')

    parser.add_argument('-a', '--auth',
                        dest='auth',
                        required=False,
                        help='file with your JIRA API token (single line)')

    parser.add_argument('-p', '--project',
                        dest='project',
                        required=True,
                        help='JIRA Project key to target')

    parser.add_argument('-t', '--teams',
                        dest='teams',
                        default="",
                        help='JIRA Teams to filter (either a file or a string)')

    parser.add_argument('-s', '--skew',
                        dest='skew',
                        default=0,
                        type=int,
                        required=False,
                        help='define how far back in months you want to check (since two months ago: -2)')

    parser.add_argument('-i', '--interval',
                        dest='interval',
                        default=0,
                        type=int,
                        required=False,
                        help='define how many months back to start the interval (interval start: -i 3 -s 4 means last 4 months starting 3 months ago)')

    parser.add_argument('--jql',
                        dest='jql',
                        default="",
                        help='JQL query to use (still supports the Skew and Teams argument)')

    return parser


def prompt_for_value(arg_name: str, description: str, default_value: str | None = None) -> str:
    """Prompt user for a missing argument value with optional default"""
    if default_value is not None:
        prompt = f"{description} ({default_value}): "
    else:
        prompt = f"{description}: "

    try:
        while True:
            value = input(prompt).strip()
            if not value and default_value is not None:
                return default_value
            if not value:
                print(f"Error: {arg_name} is required and cannot be empty. Please try again.")
                continue
            return value
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)


def parse_args_interactive():
    """Parse arguments with interactive prompting for missing required values"""
    parser = create_argument_parser()

    # Parse arguments but check if skew/interval were explicitly provided
    skew_provided = any(arg in sys.argv for arg in ['-s', '--skew'])
    interval_provided = any(arg in sys.argv for arg in ['-i', '--interval'])

    args = parser.parse_args()

    # Handle auth file logic
    if not args.auth:
        # Check if default token.txt exists
        if Path('token.txt').is_file():
            args.auth = 'token.txt'
        else:
            # Default file doesn't exist, prompt user
            args.auth = prompt_for_value(
                'auth',
                '-a/--auth: File with your JIRA API token (single line)',
                'token.txt'
            )

    # Prompt for skew and interval if not provided via command line
    if not skew_provided:
        skew_input = prompt_for_value(
            'skew',
            '-s/--skew: How far back in months you want to check (since N months ago)',
            '0'
        )
        try:
            args.skew = int(skew_input)
        except ValueError:
            print(f"Error: Invalid value for skew: {skew_input}. Using default 0.")
            args.skew = 0

    if not interval_provided:
        interval_input = prompt_for_value(
            'interval',
            '-i/--interval: How many months back to start the interval',
            '0'
        )
        try:
            args.interval = int(interval_input)
        except ValueError:
            print(f"Error: Invalid value for interval: {interval_input}. Using default 0.")
            args.interval = 0

    return args
