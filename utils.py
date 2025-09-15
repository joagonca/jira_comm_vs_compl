"""
Random utilities and configuration
"""

import math
from typing import Union
from colorama import Fore, Style, init

init(autoreset=True)

JIRA_CONFIG = {
    'MAX_RESULTS': 1000,
    'SPRINT_CUSTOM_FIELD': "customfield_10000",
    'STORY_POINTS_CUSTOM_FIELD': "customfield_10006",
    'DEBUG_DIR': "debug",
    'DEBUG_DELIVERED_FILE': "delivered.txt",
    'DEBUG_CARRYOVER_FILE': "carryover.txt",
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
    'header': Fore.MAGENTA + Style.BRIGHT
}

def seconds_to_pretty(seconds: Union[int, float]) -> str:
    """Makes seconds look pretty in the console"""
    days = math.ceil(seconds // (24 * 3600))
    seconds %= (24 * 3600)
    hours = math.ceil(seconds // 3600)
    seconds %= 3600
    minutes = math.ceil(seconds // 60)
    seconds %= 60

    return f"{days}d, {hours:02d}h{minutes:02d}"

def colorize_percentage(percentage: Union[int, float], good_threshold: Union[int, float] = 85, warning_threshold: Union[int, float] = 75) -> str:
    """Colorize percentage based on thresholds"""
    if percentage >= good_threshold:
        return f"{Fore.GREEN}{percentage:.2f}%{Style.RESET_ALL}"
    elif percentage >= warning_threshold:
        return f"{Fore.YELLOW}{percentage:.2f}%{Style.RESET_ALL}"
    else:
        return f"{Fore.RED}{percentage:.2f}%{Style.RESET_ALL}"

def colorize_aging_status(is_aged: bool) -> str:
    """Colorize aging status indicator"""
    if is_aged:
        return f"{Fore.RED}⚠ AGED{Style.RESET_ALL}"
    else:
        return f"{Fore.GREEN}✓ OK{Style.RESET_ALL}"

def colorize_metric_value(value: Union[str, int, float], metric_type: str = 'default') -> str:
    """Colorize metric values based on type"""
    if metric_type == 'count':
        return f"{Fore.CYAN}{value}{Style.RESET_ALL}"
    elif metric_type == 'time':
        return f"{Fore.BLUE}{value}{Style.RESET_ALL}"
    elif metric_type == 'header':
        return f"{Fore.MAGENTA}{Style.BRIGHT}{value}{Style.RESET_ALL}"
    else:
        return f"{Fore.WHITE}{value}{Style.RESET_ALL}"

def colorize_issue_key(key: str) -> str:
    """Colorize issue key"""
    return f"{Fore.CYAN}{Style.BRIGHT}{key}{Style.RESET_ALL}"

def colorize_trend_arrow(slope: Union[int, float], threshold: Union[int, float] = 0.01) -> str:
    """Colorize trend arrow based on slope (for commitment/delivery trends)"""
    if slope > threshold:  # Significant upward trend (good)
        return f"{COLOR_THEMES['success']}↗{Style.RESET_ALL}"
    elif slope < -threshold:  # Significant downward trend (bad)
        return f"{COLOR_THEMES['error']}↘{Style.RESET_ALL}"
    else:  # Relatively flat
        return f"{COLOR_THEMES['info']}→{Style.RESET_ALL}"

def colorize_rework_trend_arrow(slope: Union[int, float], threshold: Union[int, float] = 1.0) -> str:
    """Colorize rework trend arrow based on slope (inverted logic - lower rework is better)"""
    if slope > threshold:  # Significant upward trend in rework (bad)
        return f"{COLOR_THEMES['error']}↗{Style.RESET_ALL}"
    elif slope < -threshold:  # Significant downward trend in rework (good)
        return f"{COLOR_THEMES['success']}↘{Style.RESET_ALL}"
    else:  # Relatively flat
        return f"{COLOR_THEMES['info']}→{Style.RESET_ALL}"

def colorize_rework_percentage(percentage: Union[int, float], bad_threshold: Union[int, float] = 30, warning_threshold: Union[int, float] = 15) -> str:
    """Colorize rework percentage (inverted logic - lower rework is better)"""
    if percentage >= bad_threshold:  # High rework ratio (bad)
        return f"{Fore.RED}{percentage:.2f}%{Style.RESET_ALL}"
    elif percentage >= warning_threshold:  # Medium rework ratio (warning)
        return f"{Fore.YELLOW}{percentage:.2f}%{Style.RESET_ALL}"
    else:  # Low rework ratio (good)
        return f"{Fore.GREEN}{percentage:.2f}%{Style.RESET_ALL}"
