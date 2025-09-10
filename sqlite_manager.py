"""SQLite manager for storing JIRA issue changelog data."""

import sqlite3
import json
from typing import Dict, Any, Optional


class SQLiteManager:
    """Manages SQLite storage for JIRA issue changelog data."""
    
    def __init__(self, db_path: str = "jira_issues.db"):
        """Initialize SQLite manager with database path."""
        self.db_path = db_path
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """Create database and table if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS issue_changelog (
                    issue_key TEXT PRIMARY KEY,
                    api_payload TEXT NOT NULL
                )
            """)
            conn.commit()
    
    def store_issue(self, issue_key: str, api_payload: Dict[str, Any], end_sprint: str) -> bool:
        """Store issue in database only if it has an end_sprint.
        
        Args:
            issue_key: JIRA issue key (e.g., 'PROJ-123')
            api_payload: Complete API response from the changelog request
            end_sprint: The end sprint identifier
            
        Returns:
            True if stored, False if not stored (no end_sprint)
        """
        if not end_sprint or end_sprint == "":
            return False
            
        payload_json = json.dumps(api_payload)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO issue_changelog (issue_key, api_payload)
                VALUES (?, ?)
            """, (issue_key, payload_json))
            conn.commit()
            
        return True
    
    def get_issue(self, issue_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve issue payload from database.
        
        Args:
            issue_key: JIRA issue key
            
        Returns:
            API payload dict if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT api_payload FROM issue_changelog WHERE issue_key = ?
            """, (issue_key,))
            
            result = cursor.fetchone()
            if result:
                return json.loads(result[0])
            return None
    
