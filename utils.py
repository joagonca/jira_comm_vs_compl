"""
Random utilities and configuration
"""

import math
from colorama import Fore, Style, init

init(autoreset=True)

JIRA_CONFIG = {
    'MAX_RESULTS': 1000,
    'SPRINT_CUSTOM_FIELD': "customfield_10000",
    'STORY_POINTS_CUSTOM_FIELD': "customfield_10006",
    'DEBUG_DIR': "debug",
    'STATE_FILE': ".state",
    'DEFAULT_CONCURRENCY': 5,
    'REQUEST_TIMEOUT': 60,
    'RETRY_COUNT_MULTIPLIER': 3,
    'RETRY_DELAY': 30
}

AGING_THRESHOLDS = {
    "Story": 14,
    "Defect": 7, 
    "Bug": 7,
    "Task": 10
}

COLOR_THEMES = {
    'success': Fore.GREEN,
    'warning': Fore.YELLOW,
    'error': Fore.RED,
    'info': Fore.CYAN,
    'header': Fore.MAGENTA + Style.BRIGHT,
    'metric': Fore.BLUE,
    'highlight': Fore.WHITE + Style.BRIGHT
}

def seconds_to_pretty(seconds):
    """Makes seconds look pretty in the console"""
    days = math.ceil(seconds // (24 * 3600))
    seconds %= (24 * 3600)
    hours = math.ceil(seconds // 3600)
    seconds %= 3600
    minutes = math.ceil(seconds // 60)
    seconds %= 60

    return f"{days}d, {hours:02d}h{minutes:02d}"

def colorize_percentage(percentage, good_threshold=85, warning_threshold=75):
    """Colorize percentage based on thresholds"""
    if percentage >= good_threshold:
        return f"{Fore.GREEN}{percentage:.2f}%{Style.RESET_ALL}"
    elif percentage >= warning_threshold:
        return f"{Fore.YELLOW}{percentage:.2f}%{Style.RESET_ALL}"
    else:
        return f"{Fore.RED}{percentage:.2f}%{Style.RESET_ALL}"

def colorize_aging_status(is_aged):
    """Colorize aging status indicator"""
    if is_aged:
        return f"{Fore.RED}⚠ AGED{Style.RESET_ALL}"
    else:
        return f"{Fore.GREEN}✓ OK{Style.RESET_ALL}"

def colorize_metric_value(value, metric_type='default'):
    """Colorize metric values based on type"""
    if metric_type == 'count':
        return f"{Fore.CYAN}{value}{Style.RESET_ALL}"
    elif metric_type == 'time':
        return f"{Fore.BLUE}{value}{Style.RESET_ALL}"
    elif metric_type == 'header':
        return f"{Fore.MAGENTA}{Style.BRIGHT}{value}{Style.RESET_ALL}"
    else:
        return f"{Fore.WHITE}{value}{Style.RESET_ALL}"

def colorize_issue_key(key):
    """Colorize issue key"""
    return f"{Fore.CYAN}{Style.BRIGHT}{key}{Style.RESET_ALL}"
