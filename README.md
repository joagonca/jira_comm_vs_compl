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
*   **Custom JQL Queries:**  Support for providing custom JQL queries for advanced filtering and data retrieval.
*   **SQLite Caching:** Automatically caches issue changelog data locally to avoid redundant API calls and improve performance.

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

## Secret File Format

The secret file should contain your JIRA API token on a single line. For example:
```
your_api_token
```

To create a JIRA API token:
1. Go to your Atlassian account settings: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a label and copy the generated token
4. Save the token in your secret file

## Usage

```bash
$ python main.py -h
usage: jira_stats [-h] [--debug] [--proxy PROXY] -u URL -s SECRET -p PROJECT [-t TEAMS] [-d SKEW] [-i INTERVAL] [--jql JQL]

Get JIRA stats for teams

options:
  -h, --help            show this help message and exit
  --debug               Enable debug mode for API calls
  --proxy PROXY         If a proxy is to be used to reach out to JIRA
  -u, --url URL         JIRA API URL
  -s, --secret SECRET   file with your JIRA API token (single line)
  -p, --project PROJECT
                        JIRA Project key to target
  -t, --teams TEAMS     JIRA Teams to filter (either a file or a string)
  -d, --skew SKEW       define how far back in months you want to check (since two months ago: -2)
  -i, --interval INTERVAL
                        define how many months back to start the interval (interval start: -i 3 -d 4 means last 4 months starting 3 months ago)
  --jql JQL             JQL query to use (still supports the Skew and Teams argument)

CFK ♥ 2025
```

### Examples

**Get data for the last 2 months:**
```bash
$ python main.py -u "https://{your-subdomain}.atlassian.net/jira/rest/api/latest" -p PROJKEY -t "123, 456, 112" -s secret.txt -d 2
```

**Get data for the last 4 months starting 3 months ago (interval mode):**
```bash
$ python main.py -u "https://{your-subdomain}.atlassian.net/jira/rest/api/latest" -p PROJKEY -t "123, 456, 112" -s secret.txt -i 3 -d 4
```

## Sample Output

The tool now provides enhanced monthly breakdowns with trend analysis:

```
Monthly Commitment vs Delivery:
  2024-07:
    Issues: 25 - Ratio: 68.0%
    Story Points: 45 - Ratio: 71.1%
  2024-08:
    Issues: 30 - Ratio: 76.7%
    Story Points: 52 - Ratio: 78.8%
  2024-09:
    Issues: 28 - Ratio: 82.1%
    Story Points: 48 - Ratio: 83.3%

  Trend (Issues): ↗
  Trend (Story Points): ↗

Monthly Rework Ratios (fixing vs building new):
  2024-07: 25.3%
  2024-08: 22.1%
  2024-09: 18.7%

  Trend: ↘
```

**Trend Indicators:**
- ↗ Green up arrow: Improving performance (better commitment/delivery, higher rework)
- ↘ Red down arrow: Declining performance (worse commitment/delivery, lower rework) 
- ↘ Green down arrow: Improving rework (less fixing, more building)
- ↗ Red up arrow: Worsening rework (more fixing, less building)
- → Gray right arrow: Stable/flat trends

## Contributing 

Feel free to contribute to this project! Please follow these guidelines: 
* Fork the repository.
* Create a new branch for your feature or bug fix.
* Write tests for your changes.
* Submit a pull request.