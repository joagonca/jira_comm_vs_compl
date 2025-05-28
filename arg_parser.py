"""
Argument parser
"""

import argparse

def create_argument_parser():
    """Creates and configures an argument parser"""
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
                        default="",
                        help='JIRA Teams to filter (either a file or a string)')

    parser.add_argument('-s', '--secret',
                        dest='secret',
                        required=True,
                        help='file with your user and password information (1st line: user 2nd line: password)')

    parser.add_argument('-d', '--skew',
                        dest='skew',
                        default=0,
                        type=int,
                        required=False,
                        help='define how far back in months you want to check (since two months ago: -2)')

    return parser
