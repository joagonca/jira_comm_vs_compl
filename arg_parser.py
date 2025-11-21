"""
Argument parser
"""

import argparse
import configparser
import sys
from pathlib import Path

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


def load_config():
    """Load configuration from config.txt file if it exists"""
    config_file = Path('config.txt')
    if not config_file.is_file():
        return {}

    config = configparser.ConfigParser()
    try:
        config.read('config.txt')
        # Return a dictionary with the configuration values
        config_dict = {}
        if config.has_section('jira'):
            if config.has_option('jira', 'url'):
                config_dict['url'] = config.get('jira', 'url')
            if config.has_option('jira', 'token'):
                config_dict['token'] = config.get('jira', 'token')
        return config_dict
    except (configparser.Error, OSError) as e:
        print(f"Warning: Error reading config.txt: {e}")
        return {}



def parse_args_interactive():
    """Parse arguments with interactive prompting for missing required values"""
    # Load configuration from config.txt if it exists
    config = load_config()
    url_from_config = config.get('url')
    token_from_config = config.get('token')

    # Create parser with conditional URL requirement
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
                        required=url_from_config is None,  # Only required if no config url
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

    parser.add_argument('-o', '--output',
                        dest='output',
                        default=None,
                        help='Excel file path for exporting metrics (optional)')

    # Parse arguments but check if skew/interval were explicitly provided
    skew_provided = any(arg in sys.argv for arg in ['-s', '--skew'])
    interval_provided = any(arg in sys.argv for arg in ['-i', '--interval'])

    args = parser.parse_args()

    # Set URL from config if it wasn't provided via command line
    if not args.url and url_from_config:
        args.url = url_from_config

    # Handle auth logic and always set args.jira_token
    if not args.auth:
        # If we have a token from config, use it directly
        if token_from_config:
            args.jira_token = token_from_config
            args.auth = None  # No file needed
        else:
            # No auth source found, prompt user for file
            args.auth = prompt_for_value(
                'auth',
                '-a/--auth: File with your JIRA API token (single line)',
                'token.txt'
            )

    # If we have an auth file, read the token from it
    if args.auth:
        with open(args.auth, encoding='utf-8') as f:
            args.jira_token = f.readline().strip()

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
