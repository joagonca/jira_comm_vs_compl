# jira_comm_vs_compl

[![Status](https://img.shields.io/badge/status-active-success.svg)]([link_to_your_project_or_repo](https://github.com/crazyfacka/jira_comm_vs_compl))
[![Python Version](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)

## Description

`jira_comm_vs_compl` is a command-line Python application that retrieves and analyzes JIRA data to provide insights into team performance and issue resolution.  It allows you to query JIRA for issues within a specific project, filter by team, and analyze data over a specified time period.  This tool is designed for quick data extraction and reporting without requiring a GUI.

## Data calculated

* **Committed vs. Delivered:** Grouped by all issues or story points
* **Average cycle time:** Grouped per issue type, with top and bottom 1%, and standard deviation

## Features

*   **Command-line Interface:** Easily run and integrate into scripts.
*   **JIRA Integration:**  Connects to your JIRA instance via the API.
*   **Team Filtering:**  Filter issues by JIRA team(s).
*   **Time Skew Analysis:** Analyze data over a configurable time period (e.g., the last two months).
*   **Interval Analysis:** Analyze data over a specific time interval with start offset (e.g., last 4 months starting 3 months ago).
*   **Custom JQL Queries:**  Support for providing custom JQL queries for advanced filtering and data retrieval.

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

The secret file should contain your JIRA username on the first line and your JIRA password on the second line. For example:
```
your_username
your_password
```

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
  -s, --secret SECRET   file with your user and password information (1st line: user 2nd line: password)
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

## Contributing 

Feel free to contribute to this project! Please follow these guidelines: 
* Fork the repository.
* Create a new branch for your feature or bug fix.
* Write tests for your changes.
* Submit a pull request.