# Jira Automation Documentation Generator

This tool parses **Jira Automation** export files (JSON) and converts them into human-readable documentation. It can generate a local **Markdown** file or upload the documentation directly to **Confluence Cloud** using the Atlassian Document Format (ADF) for rich formatting.

## 🚀 Features

* **Three Output Modes:**
    1.  **Markdown File:** Generates a local `.md` file for offline viewing or version control.
    2.  **Confluence (Single Page):** Consolidates all automation rules onto a single "Master List" Confluence page.
    3.  **Confluence (Multi-Page):** Creates a separate Confluence page for every individual automation rule.
* **Rich Formatting:** Parses complex automation logic including:
    * Triggers (Scheduled, Webhooks, Field Changes, etc.)
    * Conditions (JQL, IF/ELSE blocks, User conditions)
    * Actions (Create Issue, Send Email, Edit Issue, ScriptRunner)
    * Smart Value Branches and Related Issue branches.
* **Metadata Extraction:** Captures ID, State (Enabled/Disabled), Author, and Actor details.

## 🛠️ Prerequisites

* Python 3.8+
* A Jira Cloud or Datacenter instance (to export automations) and, subsequently, an exported JSON file of your Jira Automation rules.
* A Confluence Cloud (Datacenter unsupported as target) instance (if using Confluence upload modes).
* A Confluence Cloud email/token of an account with permissions to create/edit pages in the target space.

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd create-automation-docs
    ```

2.  **Install required Python packages:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Prepare the Input Directory:**
    Ensure you have a directory named `input` in the root of the project.
    ```bash
    mkdir input
    ```

## ⚙️ Configuration

1.  **Get your Jira Automation Export:**
    * Go to **Jira Settings** > **System** > **Global Automation**.
    * Click the **...** (three dots) menu in the top right and select **Export**.
    * Save the downloaded JSON file as `*.json`.

2.  **Set up Environment Variables:**
    * Copy the example configuration file:
        ```bash
        cp config/example.env .env
        ```
    * Open `.env` and fill in your details:

| Variable | Description | Required For |
| :--- | :--- | :--- |
| `SCRIPT_MODE` | Options: `MARKDOWN`, `CONFLUENCE_MULTI`, `CONFLUENCE_SINGLE` | All |
| `INPUT_FILE_PATH` | Path to your JSON export (default: `input/jira_automations.json`) | All |
| `OUTPUT_MARKDOWN_FILE` | Filename for the output (default: `automations.md`) | `MARKDOWN` |
| `CONFLUENCE_URL` | Base URL (e.g., `https://your-site.atlassian.net`) | `CONFLUENCE_*` |
| `CONFLUENCE_USERNAME` | Your email address used to log in to Atlassian. | `CONFLUENCE_*` |
| `CONFLUENCE_API_TOKEN` | Your API Token. [Create one here](https://id.atlassian.com/manage/api-tokens). | `CONFLUENCE_*` |
| `CONFLUENCE_SPACE_KEY` | The Key of the Space where pages will be created (e.g., `DS`, `IT`). | `CONFLUENCE_*` |
| `CONFLUENCE_PARENT_PAGE_ID` | The ID of the page under which the docs will be created. | `CONFLUENCE_*` |
| `PAGE_TITLE_PREFIX` | Prefix added to page titles (e.g., `[AUTO]`). | `CONFLUENCE_*` |
| `CONFLUENCE_SINGLE_PAGE_TITLE` | The title of the summary page in Single Mode. | `CONFLUENCE_SINGLE` |

## 🏃 Usage

Run the script using Python:

```bash
python main.py
```

## Output Explanation
### Mode: MARKDOWN
The script will parse the JSON and create a file (defined in OUTPUT_MARKDOWN_FILE) in the root directory. 
This file contains formatted tables and lists describing your automations.

### Mode: CONFLUENCE_SINGLE
The script connects to Confluence and creates (or updates) a single page defined by CONFLUENCE_SINGLE_PAGE_TITLE. 
All automations are listed sequentially on this page, separated by horizontal rules.

### Mode: CONFLUENCE_MULTI
The script iterates through every rule in the JSON.
It creates a child page for each rule under the CONFLUENCE_PARENT_PAGE_ID.
The Page Title format is: [PREFIX] Rule Name (ID: <RuleID>).

> **_NOTE:_** Including the ID in the title prevents naming conflicts if you have two rules with the same name.

## 📝 Troubleshooting
*"Error: 'rules' key not found":* Ensure you exported the rules from the Global automation administration page, or ensure the JSON structure matches standard Jira exports.
*Confluence Authentication Error:* Double-check your API Token. It is not your login password. You must generate it from the Atlassian ID management page.

## 📄 License
use away, i dont care. Do take notice of the licenses of the dependencies though.