# jira_comm_vs_compl

[![Status](https://img.shields.io/badge/status-active-success.svg)]([link_to_your_project_or_repo](https://github.com/crazyfacka/jira_comm_vs_compl))
[![Python Version](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)

## Description

`jira_comm_vs_compl` is a command-line Python application that retrieves and analyzes JIRA data to provide insights into team performance and issue resolution.  It allows you to query JIRA for issues within a specific project, filter by team, and analyze data over a specified time period.  This tool is designed for quick data extraction and reporting without requiring a GUI.

## Data calculated

* **Committed vs. Delivered:** Grouped by all issues or story points
  - **Monthly Breakdown:** Shows commitment vs delivery ratios for each month
  - **Trend Analysis:** Mathematical trend indicators (↗ improving, ↘ declining, → stable)
* **Work Item Aging:** Track items currently "In Progress" for too long based on thresholds:
  - Story: 14 days
  - Defect: 7 days
  - Bug: 7 days
  - Task: 10 days
* **Average cycle time:** Grouped per issue type, with top and bottom 1%, and standard deviation
* **Rework Ratio:** Time spent fixing (defects/bugs) vs building new (stories)
  - **Monthly Breakdown:** Shows rework ratios for each month
  - **Trend Analysis:** Mathematical trend indicators for rework patterns over time

## Features

*   **Command-line Interface:** Easily run and integrate into scripts.
*   **JIRA Integration:**  Connects to your JIRA instance via the API.
*   **Team Filtering:**  Filter issues by JIRA team(s).
*   **Time Skew Analysis:** Analyze data over a configurable time period (e.g., the last two months).
*   **Interval Analysis:** Analyze data over a specific time interval with start offset (e.g., last 4 months starting 3 months ago).
*   **Monthly Partitioning:** Queries are automatically partitioned by month for precise monthly metrics.
*   **Progress Indicators:** Visual feedback during monthly query execution with format `[1/3]`.
*   **Trend Analysis:** Mathematical linear regression analysis using numpy for commitment and rework trends.
*   **Colorized Output:** Color-coded arrows and percentages for easy trend visualization.
*   **Excel Export:** Professional Excel reports with formatted tables, status color coding, and interactive charts (5 chart types).
*   **Custom JQL Queries:**  Support for providing custom JQL queries for advanced filtering and data retrieval.
*   **SQLite Caching:** Automatically caches issue changelog data locally to avoid redundant API calls and improve performance.
*   **Debug Levels:** Two-level debugging system for troubleshooting and analysis:
    - **Level 1 (`-d`):** Creates `debug/delivered.txt` and `debug/carryover.txt` with issue keys
    - **Level 2 (`-dd`):** Level 1 + stores complete API responses as JSON files

## Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/crazyfacka/jira_comm_vs_compl
    cd jira-comm-vs-compl
    ```

2.  **Create a virtual environment (recommended):**

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # venv\Scripts\activate  # On Windows
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

## Configuration

### Configuration File Format

You can create a `config.txt` file in INI format to store your JIRA settings:

```ini
[jira]
url = https://your-subdomain.atlassian.net/jira/rest/api/latest
token = your_api_token_here
```

### Secret File Format (Alternative)

Alternatively, you can use a separate file containing your JIRA API token on a single line:
```
your_api_token
```

### Creating a JIRA API Token

To create a JIRA API token:
1. Go to your Atlassian account settings: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a label and copy the generated token
4. Save the token in either `config.txt` or a separate auth file

## Usage

The application now supports interactive prompting for missing arguments and automatic file detection for convenience.

### Command Line Arguments

```bash
$ python main.py -h
usage: jira_stats [-h] [--debug] [--proxy PROXY] [-u URL] [-a AUTH] -p PROJECT [-t TEAMS] [-s SKEW] [-i INTERVAL] [--jql JQL] [-o OUTPUT]

Get JIRA stats for teams

options:
  -h, --help            show this help message and exit
  --debug, -d           Debug level: -d for basic, -dd for verbose
  --proxy PROXY         If a proxy is to be used to reach out to JIRA
  -u, --url URL         JIRA API URL
  -a, --auth AUTH       file with your JIRA API token (single line)
  -p, --project PROJECT
                        JIRA Project key to target
  -t, --teams TEAMS     JIRA Teams to filter (either a file or a string)
  -s, --skew SKEW       define how far back in months you want to check (since two months ago: -2)
  -i, --interval INTERVAL
                        define how many months back to start the interval (interval start: -i 3 -s 4 means last 4 months starting 3 months ago)
  --jql JQL             JQL query to use (still supports the Skew and Teams argument)
  -o, --output OUTPUT   directory path for Excel export (optional, generates filename automatically)

CFK ♥ 2025
```

### Interactive Mode & File Detection

The application automatically detects configuration files and prompts for missing arguments:

**Configuration File Support:**
- **`config.txt`**: INI format configuration file that can contain URL and API token
- If this file exists, the URL and authentication become optional via command line
- Configuration file uses standard INI format with `[jira]` section

**Interactive Prompts:**
- If required arguments are missing (and no configuration exists), the application will prompt you interactively
- Default values are shown in parentheses - press Enter to use them
- Use Ctrl+C to cancel the operation

**Priority Order:**
1. Command-line arguments (highest priority)
2. Configuration file (`config.txt`)
3. Interactive prompts with defaults (lowest priority)

### Examples

**Get data for the last 2 months:**
```bash
$ python main.py -u "https://{your-subdomain}.atlassian.net/jira/rest/api/latest" -p PROJKEY -t "123, 456, 112" -a secret.txt -s 2
```

**Get data for the last 4 months starting 3 months ago (interval mode):**
```bash
$ python main.py -u "https://{your-subdomain}.atlassian.net/jira/rest/api/latest" -p PROJKEY -t "123, 456, 112" -a secret.txt -i 3 -s 4
```

**Export to Excel:**
```bash
$ python main.py -p PROJKEY -t "123, 456" -a secret.txt -s 3 -o /path/to/output
```

The `-o` flag exports metrics to a professionally formatted Excel file with:
- **Overall Summary Sheet**: All metrics with status color coding
- **Monthly Breakdown Sheets**: Individual sheets for each month
- **Visualizations Sheet**: interactive charts (requires 2+ months of data):

**Filename format**: `{PROJECT_KEY}_{START_MONTH}_to_{END_MONTH}_metrics.xlsx`

## Sample Output

The tool now provides enhanced monthly breakdowns with trend analysis:

```
Valid issues: 30
Ratio of Comm vs. Delv. (by issue count): 100.00%
Ratio of Comm vs. Delv. (by story points): 100.00%

Monthly Commitment vs Delivery:
  2025-07:
    Issues: 16 - Ratio: 100.00%
    Story Points: 52.0 - Ratio: 100.00%
  2025-08:
    Issues: 14 - Ratio: 100.00%
    Story Points: 39.0 - Ratio: 100.00%

  Trend (Issues): →
  Trend (Story Points): →

Monthly Rework Ratios (fixing vs building new):
  2025-07: 0.00%
  2025-08: 0.00%

  Trend: →

Work Item Aging: No items currently in progress

Average cycle time:
Story (26): 6d, 11h22
    Top 1% [PROJ-1186]: 8d, 20h20
    Bottom 1% [PROJ-1416]: 2d, 12h11
    Std. Deviation: 1d, 21h34

Task (4): 3d, 00h53
    Top 1% [PROJ-1451]: 8d, 02h37
    Bottom 1% [PROJ-1462]: 0d, 05h45
    Std. Deviation: 3d, 06h14

Average cycle time by Story Points:
1 SPs (5): 2d, 21h06 (SD: 2d, 22h23)
2 SPs (4): 5d, 09h38 (SD: 1d, 12h32)
3 SPs (15): 6d, 13h04 (SD: 1d, 19h37)
5 SPs (5): 7d, 12h37 (SD: 0d, 15h15)
8 SPs (1): 8d, 16h13 (SD: 0d, 00h00)

Rework Ratio (fixing vs. building new): 0.00%
```

**Trend Indicators:**
- ↗ Green up arrow: Improving performance (better commitment/delivery, higher rework)
- ↘ Red down arrow: Declining performance (worse commitment/delivery, lower rework) 
- ↘ Green down arrow: Improving rework (less fixing, more building)
- ↗ Red up arrow: Worsening rework (more fixing, less building)
- → Gray right arrow: Stable/flat trends

## Debug Features

The application supports two levels of debugging to help with troubleshooting and analysis:

### Level 1 Debug (`-d`)
```bash
$ python main.py -u "https://{your-subdomain}.atlassian.net/jira/rest/api/latest" -p PROJKEY -t "123, 456" -a secret.txt -s 2 -d
```

Creates two text files in the `debug/` directory:
- **`delivered.txt`**: One issue key per line for issues delivered in the same sprint they were started
- **`carryover.txt`**: One issue key per line for issues that carried over to different sprints

### Level 2 Debug (`-dd`)
```bash
$ python main.py -u "https://{your-subdomain}.atlassian.net/jira/rest/api/latest" -p PROJKEY -t "123, 456" -a secret.txt -s 2 -dd
```

Includes Level 1 debug files plus:
- **Individual JSON files**: Complete API responses for each processed issue (e.g., `PROJ-1234.json`)
- Useful for deep analysis of changelog data and sprint transitions

**Debug files location:** All debug files are created in a `debug/` directory in the current working directory.

## Contributing 

Feel free to contribute to this project! Please follow these guidelines: 
* Fork the repository.
* Create a new branch for your feature or bug fix.
* Write tests for your changes.
* Submit a pull request.