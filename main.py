import json
import os
import re
import sys
import traceback
from typing import Any, Callable, Dict, List

# --- Load Environment Variables ---
try:
    from dotenv import load_dotenv
    load_dotenv("./config/test.env")
except ImportError:
    print("⚠️  Error: 'python-dotenv' library not found.")
    print("Please install it using: pip install python-dotenv")
    sys.exit(1)

# --- Configuration Section ---
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_PARENT_PAGE_ID = os.getenv("CONFLUENCE_PARENT_PAGE_ID")

PAGE_TITLE_PREFIX = os.getenv("PAGE_TITLE_PREFIX", "[AUTO]")
CONFLUENCE_SINGLE_PAGE_TITLE = os.getenv(
    "CONFLUENCE_SINGLE_PAGE_TITLE", "Jira Automations Master List"
)

# Toggle Mode: MARKDOWN, CONFLUENCE_MULTI, CONFLUENCE_SINGLE
MODE = os.getenv("SCRIPT_MODE", "CONFLUENCE_SINGLE").upper()

INPUT_FILE_PATH = os.getenv("INPUT_FILE_PATH", "input/jira_automations.json")
OUTPUT_MARKDOWN_FILE = os.getenv("OUTPUT_MARKDOWN_FILE", "automations.md")

# --- Import Confluence Library ---
try:
    from atlassian import Confluence
except ImportError:
    if "CONFLUENCE" in MODE:
        print("⚠️  Error: 'atlassian-python-api' library not found.")
        print("Please install it using: pip install atlassian-python-api")
        sys.exit(1)

# --- Validation ---
if "CONFLUENCE" in MODE:
    required_vars = [
        CONFLUENCE_URL,
        CONFLUENCE_USERNAME,
        CONFLUENCE_API_TOKEN,
        CONFLUENCE_SPACE_KEY
    ]
    if not all(required_vars):
        print("❌ Error: Missing Confluence configuration in .env file.")
        sys.exit(1)


# --- Step 1: Data Loading & Extraction ---

def load_automations(filepath: str) -> dict:
    """Loads the Jira automation JSON export from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except IOError as e:
        print(f"Error loading file '{filepath}': {e}")
        return None


def extract_rule_details(automation_data: dict) -> list:
    """Extracts relevant rule details from the raw JSON data."""
    if not automation_data or "rules" not in automation_data:
        print("No 'rules' key found.")
        return []

    extracted_rules = []
    for rule in automation_data.get("rules", []):
        trigger_data = rule.get('trigger', {})
        trigger_info = {
            'component_category': trigger_data.get('component'),
            'type': trigger_data.get('type'),
            'configuration': trigger_data.get('value')
        }
        components_list = []
        for comp in rule.get('components', []):
            components_list.append({
                'component_category': comp.get('component'),
                'type': comp.get('type'),
                'configuration': comp.get('value'),
                'children': comp.get('children'),
                'conditions': comp.get('conditions')
            })

        actor = rule.get('actor')
        actor_id = 'N/A'
        if isinstance(actor, dict):
            actor_id = actor.get('value', 'N/A (dict)')
        elif isinstance(actor, str):
            actor_id = actor
        else:
            actor_id = str(rule.get('actorAccountId', 'N/A'))

        extracted_rules.append({
            'id': rule.get('id'),
            'name': rule.get('name'),
            'description': rule.get('description', ''),
            'state': rule.get('state'),
            'authorAccountId': rule.get('authorAccountId'),
            'actorAccountId': actor_id,
            'trigger': trigger_info,
            'components': components_list
        })
    return extracted_rules


# --- Step 2: Formatter Helpers ---

def format_advanced_fields_markdown(advanced_fields_str: str) -> str:
    """Formats raw JSON strings for advanced fields into pretty-printed JSON."""
    if not advanced_fields_str or not isinstance(advanced_fields_str, str):
        return ""
    cleaned = advanced_fields_str.strip().replace('\r', '')
    try:
        parsed = json.loads(cleaned)
        return json.dumps(parsed, indent=4)
    except json.JSONDecodeError:
        return cleaned


def _parse_field_value(op_value: Any) -> str:
    """Parses various operation value types into a readable string."""
    if isinstance(op_value, str):
        # Replace standalone '----' with '...' to prevent markdown HR issues
        cleaned = re.sub(r'^\s*----\s*$', '...', op_value, flags=re.MULTILINE)
        if cleaned.startswith("{{") and cleaned.endswith("}}"):
            return f"`{cleaned}` (Smart Value)"
        elif '\n' in cleaned:
            return f"```\n{cleaned}\n```"
        else:
            # Escape backticks if not a smart value
            if not (cleaned.startswith("{{") and cleaned.endswith("}}")):
                cleaned = cleaned.replace('`', '\\`')
            return f'"{cleaned}"'

    elif isinstance(op_value, list):
        first = op_value[0] if op_value else {}
        val = (first or {}).get('value', 'N/A')
        return f"`{val}` (List)"

    elif isinstance(op_value, dict):
        val_type = op_value.get('type')
        val = op_value.get('value')
        if val_type in ('ID', 'KEY', 'NAME'):
            return f'"{val}"'
        elif val_type == 'COPY':
            return f"(Copy from: **{val}**)"
        elif val_type == 'SMART':
            return f"`{val}` (Smart Value)"
        elif 'copyOptions' in op_value:
            src_field = (op_value.get('sourceField') or {}).get('value')
            src_issue = op_value.get('sourceIssue')
            return f"(Copy **{src_field}** from **{src_issue}** issue)"
        elif 'issue' in op_value:
            issue_val = (op_value.get('issue') or {}).get('value')
            link_type = op_value.get('linkType')
            return f"(Link to **{issue_val}** as **{link_type}**)"

    elif op_value is None:
        return "`null`"

    return str(op_value)


# --- Step 3: Component Text Generators ---

def _format_comp_unknown(component: Dict[str, Any]) -> List[str]:
    comp_type = component.get('type', 'N/A')
    category = (
        component.get('component_category') or
        component.get('component') or
        'Unknown'
    ).title()
    return [f"**Unknown {category}:** `{comp_type}`"]


def _format_comp_email(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    to = [t.get('value', 'N/A') for t in config.get('to', [])]
    subject = config.get('subject', '')
    return [
        "**Action:** Send Email",
        f"**To:** {', '.join(to)}",
        f"**Subject:** `{subject}`"
    ]


def _format_comp_edit(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    ops_list = []
    for op in (config.get('operations') or []):
        field_name = (
            op.get('fieldId') or
            (op.get('field') or {}).get('value', 'N/A')
        )
        value_str = _parse_field_value(op.get('value'))
        ops_list.append(f"**{field_name}** = {value_str}")

    details = ["**Action:** Edit Issue"]
    if ops_list:
        details.append("**Operations:**")
        details.extend(ops_list)
    if config.get('advancedFields'):
        details.append("**Advanced Fields:**")
        md_code = format_advanced_fields_markdown(config.get('advancedFields'))
        details.append(f"```\n{md_code}\n```")
    return details


def _format_comp_assign(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    return [
        "**Action:** Assign Issue",
        f"**To:** {config.get('assignType', 'N/A')}"
    ]


def _format_comp_transition(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    dest_id = (config.get('destinationStatus') or {}).get('value', 'N/A')
    return [
        "**Action:** Transition Issue",
        f"**To Status ID:** {dest_id}"
    ]


def _format_comp_lookup(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    query = (config.get('query') or {}).get('value', 'N/A')
    return [
        "**Action:** Lookup Issues",
        f"**JQL:** `{query}`"
    ]


def _format_comp_comment(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    snippet = config.get('comment', '').split('\n', 1)[0]
    return [
        "**Action:** Add Comment",
        f"**Comment (start):** `{snippet}...`"
    ]


def _format_comp_scriptrunner(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    note = config.get('note', 'No note')
    script_cfg = config.get('scriptConfig') or {}
    script = script_cfg.get('script', 'N/A').split('\n')[0]
    return [
        "**Action:** Run ScriptRunner Script",
        f"**Note:** {note}",
        f"**Script (start):** `{script}...`"
    ]


def _format_comp_issue_cond(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    field = (config.get('selectedField') or {}).get('value', 'N/A')
    comp = config.get('comparison', 'N/A')
    val = (config.get('compareValue') or {}).get('value', 'N/A')
    val_str = ""
    if comp not in ('EMPTY', 'NOT_EMPTY') or val != 'N/A':
        val_str = f" **{val}**"
    return [
        "**Condition:** Issue Condition",
        f"**If:** Field **{field}** {comp}{val_str}"
    ]


def _format_comp_compare_cond(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    first = config.get('first', 'N/A')
    operator = config.get('operator', 'N/A')
    second = config.get('second', 'N/A')
    return [
        "**Condition:** Compare Values",
        f"**If:** `{{ {first} }}` {operator} `{second}`"
    ]


def _format_comp_related_branch(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    related_type = config.get('relatedType', 'N/A')
    details = [f"**Branch:** For Related Issues ({related_type})"]
    if related_type == 'jql':
        details.append(f"**JQL:** `{config.get('jql', '')}`")
    return details


def _format_comp_create_subtasks(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    count = len(config.get('subtasks', []))
    return ["**Action:** Create Subtasks", f"**Count:** {count} subtask(s)"]


def _format_comp_create_variable(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    name = (config.get('name') or {}).get('value', 'N/A')
    val = (config.get('query') or {}).get('value', 'N/A')
    return [
        "**Action:** Create Variable",
        f"**Name:** `{name}`",
        f"**Smart Value:** `{val}`"
    ]


def _format_comp_log_action(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    msg = config if isinstance(config, str) else 'N/A'
    return ["**Action:** Log Action", f"**Message:** `{msg}`"]


def _format_comp_create_issue(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    project_key = 'N/A'
    issue_type = 'N/A'
    nested = []
    for op in (config.get('operations') or []):
        field_name = (
            op.get('fieldId') or
            (op.get('field') or {}).get('value', 'N/A')
        )
        val = _parse_field_value(op.get('value'))
        if field_name.lower() == 'project':
            project_key = val
        elif field_name.lower() == 'issuetype':
            issue_type = val
        else:
            nested.append(f"**{field_name}** = {val}")

    details = [
        "**Action:** Create Issue",
        f"**Project:** {project_key}",
        f"**Issue Type:** {issue_type}"
    ]
    if nested:
        details.append("**Other Fields:**")
        details.extend(nested)
    if config.get('advancedFields'):
        md = format_advanced_fields_markdown(config.get('advancedFields'))
        details.append("**Advanced Fields:**")
        details.append(f"```\n{md}\n```")
    return details


def _format_comp_clone_issue(component: Dict[str, Any]) -> List[str]:
    # Reuse logic since clone structure mirrors create structure
    details = _format_comp_create_issue(component)
    details[0] = "**Action:** Clone Issue"
    return details


def _format_comp_related_cond(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    op = config.get('operator', 'allmatch')
    type_ = config.get('relatedType', 'any')
    details = [
        "**Condition:** Related Issues Condition",
        f"**Check:** {op.upper()} of **{type_}** issues"
    ]
    if config.get('compareJql'):
        details.append(f"**Must Match:** matches JQL: `{config.get('compareJql')}`")
    else:
        conds = component.get('conditions', [])
        if not conds:
            details.append("**Must Match:** (No condition specified)")
        else:
            for c in conds:
                cc = c.get('value') or {}
                ct = c.get('type')
                s = f"Unknown: {ct}"
                if ct == 'jira.issue.condition':
                    f = (cc.get('selectedField') or {}).get('value', 'N/A')
                    cmp = cc.get('comparison', 'N/A')
                    v = (cc.get('compareValue') or {}).get('value', 'N/A')
                    s = f"Field **{f}** {cmp} **{v}**"
                elif ct == 'jira.comparator.condition':
                    f = cc.get('first', 'N/A')
                    o = cc.get('operator', 'N/A')
                    sec = cc.get('second', 'N/A')
                    s = f"`{{ {f} }}` {o} `{sec}`"
                elif ct == 'jira.jql.condition':
                    j = cc if isinstance(cc, str) else (cc or {}).get('query', 'N/A')
                    s = f"matches JQL: `{j}`"
                else:
                    s = f"Unknown: {ct}"
                details.append(f"**Must Match:** {s}")
    return details


def _format_comp_if_container(_component: Dict[str, Any]) -> List[str]:
    return ["**Condition:** IF/ELSE Logic Block"]


def _format_comp_if_block(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    conds = component.get('conditions', [])
    if not conds:
        return ["**Else Block:**"]
    details = [f"**IF Block:** (Match: {config.get('conditionMatchType', 'ALL')})"]
    for c in conds:
        cc = c.get('value') or {}
        ct = c.get('type')
        s = f"Unknown: {ct}"
        if ct == 'jira.issue.condition':
            f = (cc.get('selectedField') or {}).get('value', 'N/A')
            cmp = cc.get('comparison', 'N/A')
            v = (cc.get('compareValue') or {}).get('value', 'N/A')
            s = f"Field **{f}** {cmp} **{v}**"
        elif ct == 'jira.comparator.condition':
            f = cc.get('first', 'N/A')
            o = cc.get('operator', 'N/A')
            sec = cc.get('second', 'N/A')
            s = f"`{{ {f} }}` {o} `{sec}`"
        elif ct == 'jira.jql.condition':
            j = cc if isinstance(cc, str) else (cc or {}).get('query', 'N/A')
            s = f"matches JQL: `{j}`"
        details.append(f"**If:** {s}")
    return details


def _format_comp_jql_cond(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    jql = 'N/A'
    if isinstance(config, str):
        jql = config
    elif isinstance(config, dict):
        jql_val = config.get('query')
        if isinstance(jql_val, str):
            jql = jql_val
        else:
            jql = (jql_val or {}).get('value', 'N/A (dict)')
    return ["**Condition:** JQL Condition", f"**If:** JQL matches: `{jql}`"]


def _format_comp_archive(_component: Dict[str, Any]) -> List[str]:
    return ["**Action:** Archive Issue"]


def _format_comp_refresh(_component: Dict[str, Any]) -> List[str]:
    return ["**Action:** Re-fetch Issue Data"]


def _format_comp_smart_value_branch(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    val = (config.get('query') or {}).get('value', 'N/A')
    var = (config.get('name') or {}).get('value', 'item')
    return [
        "**Branch:** For Each Smart Value",
        f"**Value:** `{val}`",
        f"**As:** `{var}`"
    ]


def _format_comp_link_issue(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    link_type = config.get('linkType', 'N/A')
    issue_to_link = _parse_field_value(config.get('issue'))
    return [
        "**Action:** Link Issue",
        f"**Link Type:** {link_type}",
        f"**To Issue:** {issue_to_link}"
    ]


def _format_comp_set_entity_property(component: Dict[str, Any]) -> List[str]:
    config = component.get('configuration') or component.get('value') or {}
    val = config.get('value', 'N/A')
    if isinstance(val, str) and len(val) > 70:
        val_display = f"`{val[:70]}...` (truncated)"
    else:
        val_display = f"`{val}`"
    return [
        "**Action:** Set Entity Property",
        f"**Entity Type:** {config.get('entityType', 'N/A')}",
        f"**Property Key:** `{config.get('key', 'N/A')}`",
        f"**Property Value:** {val_display}"
    ]


COMPONENT_FORMATTERS: Dict[str, Callable[[Dict[str, Any]], List[str]]] = {
    'jira.issue.outgoing.email': _format_comp_email,
    'jira.issue.edit': _format_comp_edit,
    'jira.issue.assign': _format_comp_assign,
    'jira.issue.transition': _format_comp_transition,
    'jira.lookup.issues': _format_comp_lookup,
    'jira.issue.comment': _format_comp_comment,
    'com.onresolve.jira.groovy.groovyrunner:execute-script-issue-action-v2': (
        _format_comp_scriptrunner
    ),
    'jira.issue.condition': _format_comp_issue_cond,
    'jira.comparator.condition': _format_comp_compare_cond,
    'jira.issue.related': _format_comp_related_branch,
    'jira.issue.create.subtasks': _format_comp_create_subtasks,
    'jira.create.variable': _format_comp_create_variable,
    'codebarrel.action.log': _format_comp_log_action,
    'jira.issue.create': _format_comp_create_issue,
    'jira.issues.related.condition': _format_comp_related_cond,
    'jira.condition.container.block': _format_comp_if_container,
    'jira.condition.if.block': _format_comp_if_block,
    'jira.jql.condition': _format_comp_jql_cond,
    'jira.issue.archive': _format_comp_archive,
    'jira.issue.refresh.issue': _format_comp_refresh,
    'jira.smart.values.branch': _format_comp_smart_value_branch,
    'jira.issue.clone': _format_comp_clone_issue,
    'jira.issue.link': _format_comp_link_issue,
    'jira.set.entity.property': _format_comp_set_entity_property,
}


def get_component_lines(comp: Dict) -> List[str]:
    """Retrieves formatted lines for a component using the dispatcher."""
    func = COMPONENT_FORMATTERS.get(
        comp.get('type'),
        _format_comp_unknown
    )

    try:
        return func(comp)
    except Exception as e:
        # We purposefully catch everything here to prevent the whole
        # generation process from stopping due to one malformed component.
        print(f"Error parsing {comp.get('type')}: {e}")
        return [f"**Error Parsing:** `{comp.get('type')}`"]


# --- Step 4: Trigger Formatting ---

def _format_trigger_scheduled(config: Dict[str, Any], _trigger_type: str) -> str:
    jql = config.get('jql', 'N/A')
    return f"**Scheduled (JQL):** Runs for issues matching JQL:\n```\n{jql}\n```"


def _format_trigger_field_changed(config: Dict[str, Any], _trigger_type: str) -> str:
    fields = [f['value'] for f in config.get('fields', [])]
    return (
        f"**Field Value Changed:** Triggers when field(s) "
        f"**{', '.join(fields)}** are modified."
    )


def _format_trigger_webhook(_config: Dict[str, Any], _trigger_type: str) -> str:
    return "**Incoming Webhook:** Triggers when the unique webhook URL is called."


def _format_trigger_manual(_config: Dict[str, Any], _trigger_type: str) -> str:
    return "**Manually Triggered:** Run by a user."


def _format_trigger_generic(_config: Dict[str, Any], trigger_type: str) -> str:
    return f"**Trigger:** `{trigger_type}`"


def _format_trigger_cmdb_object(config: Dict[str, Any], _trigger_type: str) -> str:
    op = config.get('operation', 'N/A')
    schema = config.get('schemaLabel', 'N/A')
    return (
        f"**Assets Object Trigger:** Triggers when an object in "
        f"**{schema}** is **{op}**."
    )


def _format_trigger_sla(config: Dict[str, Any], _trigger_type: str) -> str:
    t_type = config.get('thresholdType', 'N/A')
    return f"**SLA Threshold:** Triggers when an SLA threshold is **{t_type}**."


TRIGGER_FORMATTERS_SIMPLE: Dict[str, Callable[[Dict, str], str]] = {
    'jira.jql.scheduled': _format_trigger_scheduled,
    'jira.issue.field.changed': _format_trigger_field_changed,
    'jira.incoming.webhook': _format_trigger_webhook,
    'jira.manual.trigger.issue': _format_trigger_manual,
    'cmdb.object.trigger': _format_trigger_cmdb_object,
    'jira.sla.threshold.trigger': _format_trigger_sla,
}


def parse_trigger(trigger: Dict[str, Any]) -> str:
    """Uses dictionary dispatch to format the trigger description."""
    trigger_type = trigger.get('type')
    config = (trigger.get('configuration') or trigger.get('value') or {})
    formatter = TRIGGER_FORMATTERS_SIMPLE.get(
        trigger_type, _format_trigger_generic
    )
    return formatter(config, trigger_type)


# --- Step 5: ADF Generation (Confluence) ---

def adf_text(text: str, strong: bool = False, code: bool = False) -> Dict:
    node = {"type": "text", "text": text}
    marks = []
    if strong:
        marks.append({"type": "strong"})
    if code:
        marks.append({"type": "code"})
    if marks:
        node["marks"] = marks
    return node


def parse_markdown_line_to_adf(line: str) -> List[Dict]:
    """Parses a string with basic markdown (**bold**, `code`) into ADF."""
    parts = re.split(r'(`[^`]+`)', line)
    nodes = []
    for part in parts:
        if part.startswith('`') and part.endswith('`'):
            nodes.append(adf_text(part[1:-1], code=True))
        else:
            subparts = re.split(r'(\*\*[^*]+\*\*)', part)
            for sub in subparts:
                if sub.startswith('**') and sub.endswith('**'):
                    nodes.append(adf_text(sub[2:-2], strong=True))
                elif sub:
                    nodes.append(adf_text(sub))
    return nodes


def adf_paragraph(content_nodes: List[Dict]) -> Dict:
    if not content_nodes:
        return {"type": "paragraph"}
    return {"type": "paragraph", "content": content_nodes}


def adf_code_block(text: str) -> Dict:
    return {
        "type": "codeBlock",
        "content": [{"type": "text", "text": text}]
    }


def adf_list_item(content_nodes: List[Dict]) -> Dict:
    return {"type": "listItem", "content": content_nodes}


def adf_ordered_list(items: List[Dict]) -> Dict:
    return {"type": "orderedList", "content": items}


def adf_bullet_list(items: List[Dict]) -> Dict:
    return {"type": "bulletList", "content": items}


def adf_heading(text: str, level: int = 1) -> Dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}]
    }


def _build_adf_info_table(rule: Dict) -> Dict:
    desc = rule.get('description') or 'N/A'
    rows = []
    rows.append({
        "type": "tableRow",
        "content": [
            {
                "type": "tableHeader",
                "attrs": {"background": "#f4f5f7"},
                "content": [adf_paragraph([adf_text("Attribute", strong=True)])]
            },
            {
                "type": "tableHeader",
                "attrs": {"background": "#f4f5f7"},
                "content": [adf_paragraph([adf_text("Value", strong=True)])]
            }
        ]
    })

    def add_row(key, val_nodes):
        rows.append({
            "type": "tableRow",
            "content": [
                {
                    "type": "tableCell",
                    "content": [adf_paragraph([adf_text(key, strong=True)])]
                },
                {
                    "type": "tableCell",
                    "content": [adf_paragraph(val_nodes)]
                }
            ]
        })

    add_row("ID", [adf_text(str(rule.get('id')), code=True)])
    add_row("State", [adf_text(rule.get('state'), strong=True)])
    add_row("Description", parse_markdown_line_to_adf(desc))
    add_row("Author", [adf_text(str(rule.get('authorAccountId')), code=True)])
    add_row("Actor", [adf_text(str(rule.get('actorAccountId')), code=True)])

    return {
        "type": "table",
        "attrs": {
            "isNumberColumnEnabled": False,
            "layout": "default",
            "width": 760
        },
        "content": rows
    }


def _get_rule_adf_nodes(rule: Dict) -> List[Dict]:
    """Generates the list of ADF nodes for a SINGLE rule."""
    content = []
    content.append(_build_adf_info_table(rule))
    content.append(adf_heading("Trigger", 2))

    trigger_text = parse_trigger(rule['trigger'])
    if "```" in trigger_text:
        parts = trigger_text.split("```")
        content.append(adf_paragraph(
            parse_markdown_line_to_adf(parts[0].strip())
        ))
        if len(parts) > 1:
            content.append(adf_code_block(parts[1].strip()))
    else:
        content.append(adf_paragraph(parse_markdown_line_to_adf(trigger_text)))

    content.append(adf_heading("Components", 2))
    if not rule.get('components'):
        content.append(adf_paragraph([adf_text("(No components)")]))
    else:
        root_items = []
        for comp in rule.get('components'):
            root_items.append(build_adf_for_component(comp))
        content.append(adf_ordered_list(root_items))

    return content


def build_adf_for_component(comp: Dict) -> Dict:
    """Recursive function to build an ADF ListItem for a component."""
    lines = get_component_lines(comp)
    main_line = lines[0] if lines else "Unknown"
    details = lines[1:] if len(lines) > 1 else []

    li_content = []
    li_content.append(adf_paragraph(parse_markdown_line_to_adf(main_line)))

    if details:
        bullet_items = []
        for detail in details:
            if detail.startswith("```"):
                code_text = detail.strip("`\n")
                bullet_items.append(adf_list_item([adf_code_block(code_text)]))
            else:
                if detail.startswith("* "):
                    detail = detail[2:]
                bullet_items.append(adf_list_item([
                    adf_paragraph(parse_markdown_line_to_adf(detail))
                ]))
        li_content.append(adf_bullet_list(bullet_items))

    children = comp.get('children')
    if children:
        child_items = []
        for child in children:
            child_items.append(build_adf_for_component(child))
        li_content.append(adf_ordered_list(child_items))

    return adf_list_item(li_content)


# --- Step 6: Confluence Upload Logic ---

def create_confluence_pages_multi(rules: List[Dict]):
    """Creates ONE page per rule."""
    confluence = Confluence(
        url=CONFLUENCE_URL,
        username=CONFLUENCE_USERNAME,
        password=CONFLUENCE_API_TOKEN,
        cloud=True
    )

    for rule in rules:
        title = f"{PAGE_TITLE_PREFIX} {rule['name']} (ID: {rule['id']})"
        print(f"Creating: {title}")

        nodes = _get_rule_adf_nodes(rule)
        adf_body = {"version": 1, "type": "doc", "content": nodes}
        json_body = json.dumps(adf_body)

        exists = confluence.get_page_id(CONFLUENCE_SPACE_KEY, title)
        if exists:
            confluence.update_page(
                page_id=exists,
                title=title,
                body=json_body,
                parent_id=CONFLUENCE_PARENT_PAGE_ID,
                representation='atlas_doc_format'
            )
        else:
            confluence.create_page(
                space=CONFLUENCE_SPACE_KEY,
                title=title,
                body=json_body,
                parent_id=CONFLUENCE_PARENT_PAGE_ID,
                representation='atlas_doc_format'
            )


def create_confluence_single_page(rules: List[Dict]):
    """Creates ONE massive page containing ALL rules."""
    confluence = Confluence(
        url=CONFLUENCE_URL,
        username=CONFLUENCE_USERNAME,
        password=CONFLUENCE_API_TOKEN,
        cloud=True
    )
    print(f"Building Single Page: {CONFLUENCE_SINGLE_PAGE_TITLE}...")

    all_content_nodes = []

    for rule in rules:
        title = f"{rule['name']} (ID: {rule['id']})"
        all_content_nodes.append(adf_heading(title, level=1))
        rule_nodes = _get_rule_adf_nodes(rule)
        all_content_nodes.extend(rule_nodes)
        all_content_nodes.append({"type": "rule"})

    adf_body = {"version": 1, "type": "doc", "content": all_content_nodes}
    json_body = json.dumps(adf_body)

    exists = confluence.get_page_id(
        CONFLUENCE_SPACE_KEY, CONFLUENCE_SINGLE_PAGE_TITLE
    )
    if exists:
        print(f"Updating page ID: {exists}")
        confluence.update_page(
            page_id=exists,
            title=CONFLUENCE_SINGLE_PAGE_TITLE,
            body=json_body,
            parent_id=CONFLUENCE_PARENT_PAGE_ID,
            representation='atlas_doc_format'
        )
    else:
        print("Creating new single page")
        confluence.create_page(
            space=CONFLUENCE_SPACE_KEY,
            title=CONFLUENCE_SINGLE_PAGE_TITLE,
            body=json_body,
            parent_id=CONFLUENCE_PARENT_PAGE_ID,
            representation='atlas_doc_format'
        )


# --- Step 7: Markdown Generation Logic ---

def parse_component_markdown(component: Dict[str, Any], indent_level: int = 0) -> str:
    """Recursively parses a component into a markdown string."""
    current_indent = "    " * indent_level
    nested_indent = "    " * (indent_level + 1)

    lines = get_component_lines(component)
    output_lines = []

    for i, line in enumerate(lines):
        if i == 0:
            output_lines.append(f"{current_indent}1.  {line}\n")
        else:
            clean_line = line
            if clean_line.startswith("* "):
                clean_line = clean_line[2:]

            if clean_line.startswith("```"):
                output_lines.append(f"{nested_indent}{clean_line}\n")
            else:
                output_lines.append(f"{nested_indent}* {clean_line}\n")

    children = component.get('children')
    if children:
        for child in children:
            output_lines.append(
                parse_component_markdown(child, indent_level + 1)
            )

    return "".join(output_lines)


def _generate_single_rule_markdown_text(rule: Dict[str, Any]) -> str:
    output = []
    output.append("| Attribute | Value |\n| :--- | :--- |\n")
    output.append(f"| **ID** | `{rule['id']}` |\n")
    output.append(f"| **State** | **{rule['state']}** |\n")
    desc = (rule['description'] or 'N/A').replace('\n', '<br/>')
    output.append(f"| **Description** | {desc} |\n")
    output.append(f"| **Author** | `{rule['authorAccountId']}` |\n")
    output.append(f"| **Actor** | `{rule['actorAccountId']}` |\n")
    output.append("\n### Trigger\n")
    output.append(parse_trigger(rule['trigger']) + "\n")
    output.append("### Components (Actions/Conditions)\n")
    if not rule['components']:
        output.append("* (No components defined)\n")
    else:
        for comp in rule['components']:
            output.append(parse_component_markdown(comp, indent_level=0))
    return "".join(output)


def generate_markdown_file_content(rules: List[Dict]) -> str:
    """Generates the full markdown string for all rules."""
    out = ["# Jira Automation Documentation\n\n"]
    for rule in sorted(rules, key=lambda x: x.get('id', 0)):
        out.append(f"## {rule['name']}\n\n")
        out.append(_generate_single_rule_markdown_text(rule))
        out.append("\n---\n\n")
    return "".join(out)


# --- Step 8: Main Execution ---
def main():
    if not INPUT_FILE_PATH:
        print("❌ Error: INPUT_FILE_PATH not set in .env")
        return

    raw_data = load_automations(INPUT_FILE_PATH)
    if raw_data:
        extracted_data = extract_rule_details(raw_data)
        if extracted_data:
            print(f"✅ Successfully extracted data for {len(extracted_data)} rules.")

            if MODE == "MARKDOWN":
                try:
                    with open(OUTPUT_MARKDOWN_FILE, 'w', encoding='utf-8') as f:
                        f.write(generate_markdown_file_content(extracted_data))
                    print(f"✅ Generated '{OUTPUT_MARKDOWN_FILE}'")
                except IOError as e:
                    print(f"Error writing markdown file: {e}")
                    traceback.print_exc()

            elif MODE == "CONFLUENCE_MULTI":
                create_confluence_pages_multi(extracted_data)

            elif MODE == "CONFLUENCE_SINGLE":
                create_confluence_single_page(extracted_data)


if __name__ == "__main__":
    main()
