"""
Random utilities and configuration
"""

import math

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

def seconds_to_pretty(seconds):
    """Makes seconds look pretty in the console"""
    days = math.ceil(seconds // (24 * 3600))
    seconds %= (24 * 3600)
    hours = math.ceil(seconds // 3600)
    seconds %= 3600
    minutes = math.ceil(seconds // 60)
    seconds %= 60

    return f"{days}d, {hours:02d}h{minutes:02d}"
