"""
Random utilities
"""

import math

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
