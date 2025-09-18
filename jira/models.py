"""
JIRA data models and classes
"""

from datetime import datetime
from typing import Optional, Union


class IssueInfo:
    """Class to return issue info"""
    def __init__(self, key: Optional[str] = None, delivered_in_sprint: Optional[bool] = None,
                 story_points: Optional[Union[int, float]] = None, issue_type: Optional[str] = None,
                 cycle_time: Optional[Union[int, float]] = None, valid: bool = True,
                 in_progress_days: Optional[float] = None, is_aged: bool = False,
                 query_month: Optional[str] = None, removed_before_midpoint: bool = False):
        self.key = key
        self.delivered_in_sprint = delivered_in_sprint
        self.story_points = story_points
        self.issue_type = issue_type
        self.cycle_time = cycle_time
        self.valid = valid
        self.in_progress_days = in_progress_days
        self.is_aged = is_aged
        self.query_month = query_month
        self.removed_before_midpoint = removed_before_midpoint


class Event:
    """Base class for timeline events"""
    def __init__(self, timestamp: datetime) -> None:
        self.timestamp: datetime = timestamp


class StatusEvent(Event):
    """Represents a status transition event"""
    def __init__(self, timestamp: datetime, from_status: str, to_status: str, sprint: Optional[str] = None) -> None:
        super().__init__(timestamp)
        self.from_status: str = from_status
        self.to_status: str = to_status
        self.sprint: Optional[str] = sprint


class SprintEvent(Event):
    """Represents a sprint assignment/removal event"""
    def __init__(self, timestamp: datetime, action: str, sprint: str) -> None:
        super().__init__(timestamp)
        self.action: str = action  # 'added' or 'removed'
        self.sprint: str = sprint


class IssueClassification:
    """Result of issue classification with all metrics"""
    def __init__(self) -> None:
        self.should_exclude: bool = False
        self.delivered_in_sprint: bool = False
        self.removed_before_midpoint: bool = False
        self.cycle_time: float = 0
        self.in_progress_days: Optional[float] = None
        self.is_aged: bool = False
        self.valid: bool = False
        self.work_start: Optional[datetime] = None
        self.work_end: Optional[datetime] = None
        self.current_status: Optional[str] = None
        self.last_in_progress_start: Optional[datetime] = None
        self.pending_duration: float = 0