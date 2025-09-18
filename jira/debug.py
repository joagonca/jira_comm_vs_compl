"""
JIRA debug utilities and file operations
"""

import json
import os
from typing import Dict, Any

from utils import JIRA_CONFIG


class DebugManager:
    """Handles debug file operations and logging"""

    def __init__(self, debug_level: int):
        self.debug_level = debug_level
        self.debug_files_cleaned = False

    def store_debug_info(self, issue: str, data: Dict[str, Any]) -> None:
        """Saves debug info to disk (level 2 debug) - overwrites existing files"""
        debug_dir = JIRA_CONFIG['DEBUG_DIR']
        os.makedirs(debug_dir, exist_ok=True)
        with open(f"{debug_dir}/{issue}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def clean_debug_files(self) -> None:
        """Clean debug files before starting new run (level 1 debug)"""
        if self.debug_level >= 1 and not self.debug_files_cleaned:
            debug_dir = JIRA_CONFIG['DEBUG_DIR']
            os.makedirs(debug_dir, exist_ok=True)

            delivered_file = f"{debug_dir}/{JIRA_CONFIG['DEBUG_DELIVERED_FILE']}"
            carryover_file = f"{debug_dir}/{JIRA_CONFIG['DEBUG_CARRYOVER_FILE']}"

            # Remove existing files if they exist
            for file_path in [delivered_file, carryover_file]:
                if os.path.exists(file_path):
                    os.remove(file_path)

            self.debug_files_cleaned = True

    def append_debug_issue(self, issue_key: str, is_delivered: bool) -> None:
        """Append issue key to appropriate debug file (level 1 debug)"""
        if self.debug_level >= 1:
            self.clean_debug_files()
            debug_dir = JIRA_CONFIG['DEBUG_DIR']
            filename = JIRA_CONFIG['DEBUG_DELIVERED_FILE'] if is_delivered else JIRA_CONFIG['DEBUG_CARRYOVER_FILE']
            with open(f"{debug_dir}/{filename}", "a", encoding="utf-8") as f:
                f.write(f"{issue_key}\n")