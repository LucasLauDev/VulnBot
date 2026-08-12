# VulnBot Data Flow & Processing Analysis

## Table of Contents

1. [Overview](#overview)
2. [Complete Data Flow Diagram](#complete-data-flow-diagram)
3. [User Input Processing](#user-input-processing)
4. [Phase 1: Initial Planning](#phase-1-initial-planning)
5. [Phase 2: Task Execution Loop](#phase-2-task-execution-loop)
6. [Phase 3: Plan Adaptation](#phase-3-plan-adaptation)
7. [Role Transitions](#role-transitions)
8. [RAG Data Flow](#rag-data-flow)
9. [Database Persistence Flow](#database-persistence-flow)
10. [Complete End-to-End Example](#complete-end-to-end-example)

---

## Overview

This document traces the complete journey of data through the VulnBot system, from initial user input to final execution results. We'll examine:

- **Input Transformations**: How user descriptions become LLM prompts
- **Prompt Templates**: Actual prompts sent to the LLM
- **LLM Responses**: Format and structure of outputs
- **Response Parsing**: How JSON/text is extracted and validated
- **Data Persistence**: What gets saved to the database
- **Inter-Role Communication**: How data flows between phases

---

## Complete Data Flow Diagram

```
USER INPUT
    │
    │ "Penetration test on 192.168.1.100"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ SESSION INITIALIZATION                                       │
├─────────────────────────────────────────────────────────────┤
│ Input: init_description (string)                             │
│ Creates: Session object                                      │
│   {                                                          │
│     id: "abc123",                                            │
│     init_description: "Penetration test on 192.168.1.100",  │
│     current_role_name: "COLLECTOR",                          │
│     current_planner_id: "",                                  │
│     history_planner_ids: []                                  │
│   }                                                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ COLLECTOR ROLE - PLANNING PHASE                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ 1. GET SUMMARY (if previous phases exist)                   │
│    Input: history_planner_ids = []                          │
│    Output: "" (empty - first phase)                         │
│                                                              │
│ 2. INITIALIZE CONVERSATIONS                                 │
│    Creates 2 conversation IDs in DB:                        │
│    - plan_chat_id: "conv_plan_001"                          │
│    - react_chat_id: "conv_react_001"                        │
│                                                              │
│ 3. BUILD PLANNING PROMPT                                    │
│    Template: init_plan_prompt                               │
│    Variables:                                               │
│      - init_description: "Penetration test on 192.168.1.100"│
│      - goal: "Perform full scan to identify ports/services" │
│      - tools: "Nmap, Curl, Wget, Whois, Dnsenum..."        │
│      - context: "" (empty for first phase)                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ PROMPT TO LLM
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM REQUEST #1: GENERATE PLAN                               │
├─────────────────────────────────────────────────────────────┤
│ Conversation: conv_plan_001                                 │
│                                                              │
│ System Message:                                             │
│   "You are a helpful assistant"                             │
│                                                              │
│ User Message:                                               │
│   "## Available Action Types: Shell, Web                    │
│    ## Task: Based on the context, write a plan...          │
│    [full write_plan prompt]                                 │
│    ## Goal: Perform full scan to identify ports/services    │
│    ## Tools: Nmap, Curl, Wget, Whois, Dnsenum...          │
│    ## Target: Penetration test on 192.168.1.100"           │
│                                                              │
│ [+ Optional RAG Context if enabled]                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ LLM RESPONSE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM RESPONSE #1: PLAN JSON                                  │
├─────────────────────────────────────────────────────────────┤
│ Raw Response:                                               │
│   "Based on the target, here's the plan:                    │
│    <json>                                                    │
│    [                                                         │
│      {                                                       │
│        "id": "1",                                            │
│        "dependent_task_ids": [],                            │
│        "instruction": "Scan all ports on 192.168.1.100",    │
│        "action": "Shell"                                     │
│      },                                                      │
│      {                                                       │
│        "id": "2",                                            │
│        "dependent_task_ids": ["1"],                         │
│        "instruction": "Identify services on open ports",    │
│        "action": "Shell"                                     │
│      },                                                      │
│      {                                                       │
│        "id": "3",                                            │
│        "dependent_task_ids": ["2"],                         │
│        "instruction": "Check for banners and versions",     │
│        "action": "Shell"                                     │
│      }                                                       │
│    ]                                                         │
│    </json>"                                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ PARSE & VALIDATE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ JSON EXTRACTION & PARSING                                   │
├─────────────────────────────────────────────────────────────┤
│ 1. Extract JSON from <json>...</json> tags                  │
│                                                              │
│ 2. Parse JSON array                                         │
│                                                              │
│ 3. Create Task objects:                                     │
│    Task 0:                                                   │
│      {                                                       │
│        id: "task_001",                                       │
│        plan_id: "plan_001",                                  │
│        sequence: 0,                                          │
│        action: "Shell",                                      │
│        instruction: "Scan all ports on 192.168.1.100",      │
│        code: [],                                             │
│        result: "",                                           │
│        is_success: false,                                    │
│        is_finished: false,                                   │
│        dependencies: []                                      │
│      }                                                       │
│                                                              │
│    Task 1:                                                   │
│      { sequence: 1, dependencies: [0], ... }                │
│                                                              │
│    Task 2:                                                   │
│      { sequence: 2, dependencies: [1], ... }                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ SAVE TO DATABASE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ DATABASE: CREATE PLAN                                       │
├─────────────────────────────────────────────────────────────┤
│ INSERT INTO plans:                                          │
│   id: "plan_001"                                             │
│   goal: "Perform full scan to identify ports/services"      │
│   current_task_sequence: 0                                   │
│   plan_chat_id: "conv_plan_001"                             │
│   react_chat_id: "conv_react_001"                           │
│                                                              │
│ INSERT INTO tasks (3 records):                              │
│   [task_001, task_002, task_003]                            │
│                                                              │
│ UPDATE sessions:                                            │
│   current_planner_id: "plan_001"                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ START REACT LOOP
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ REACT ITERATION #1: TASK DETAILS                            │
├─────────────────────────────────────────────────────────────┤
│ Current Task: Task 0                                        │
│   instruction: "Scan all ports on 192.168.1.100"           │
│                                                              │
│ Build prompt with next_task_details template                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ PROMPT TO LLM
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM REQUEST #2: GET TASK DETAILS                            │
├─────────────────────────────────────────────────────────────┤
│ Conversation: conv_react_001                                │
│                                                              │
│ User Message:                                               │
│   "Now you're provided with an input that contains the      │
│    penetration testing next task...                         │
│    ## Next Task: Scan all ports on 192.168.1.100           │
│    ## Output Requirements:                                  │
│    1. Clearly state the task to be executed...             │
│    2. Be concise and precise..."                            │
│                                                              │
│ [+ Optional RAG Context: Query KB with task instruction]    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ LLM RESPONSE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM RESPONSE #2: TASK DETAILS                               │
├─────────────────────────────────────────────────────────────┤
│ Response Text:                                              │
│   "Task: Perform a comprehensive port scan on target        │
│    192.168.1.100 to discover all open TCP/UDP ports.        │
│                                                              │
│    Command: nmap -T5 -p- 192.168.1.100                     │
│                                                              │
│    Purpose: This scan will identify all listening services  │
│    on the target, providing the foundation for subsequent   │
│    vulnerability assessment and enumeration tasks."         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ NEXT: GENERATE CODE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM REQUEST #3: GENERATE EXECUTABLE CODE                    │
├─────────────────────────────────────────────────────────────┤
│ Conversation: NEW (no history for code generation)          │
│                                                              │
│ User Message:                                               │
│   "You play as an autonomous penetration testing assistant  │
│    running on Kali Linux 2023...                            │
│    [full write_code prompt]                                 │
│                                                              │
│    **Next Task**: Task: Perform a comprehensive port scan   │
│    on target 192.168.1.100 to discover all open TCP/UDP     │
│    ports. Command: nmap -T5 -p- 192.168.1.100..."         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ LLM RESPONSE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM RESPONSE #3: EXECUTABLE COMMANDS                        │
├─────────────────────────────────────────────────────────────┤
│ Response Text:                                              │
│   "<execute>nmap -T5 -p- 192.168.1.100</execute>"          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ PARSE COMMANDS
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ COMMAND EXTRACTION                                          │
├─────────────────────────────────────────────────────────────┤
│ Regex: r'<execute>\s*(.*?)\s*</execute>'                    │
│                                                              │
│ Extracted Commands:                                         │
│   ["nmap -T5 -p- 192.168.1.100"]                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ EXECUTE ON KALI
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ SSH EXECUTION                                               │
├─────────────────────────────────────────────────────────────┤
│ 1. Connect to Kali via SSH                                  │
│    Host: 10.10.0.5:22                                       │
│    User: root                                                │
│                                                              │
│ 2. Execute command:                                         │
│    shell.execute_cmd("nmap -T5 -p- 192.168.1.100")        │
│                                                              │
│ 3. Wait for prompt detection                                │
│                                                              │
│ 4. Collect output                                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ COMMAND OUTPUT
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ EXECUTION RESULT                                            │
├─────────────────────────────────────────────────────────────┤
│ Output:                                                     │
│   "Starting Nmap 7.94 ( https://nmap.org )                 │
│    Nmap scan report for 192.168.1.100                      │
│    Host is up (0.0012s latency).                           │
│    Not shown: 65532 closed tcp ports (reset)               │
│    PORT    STATE SERVICE                                    │
│    22/tcp  open  ssh                                        │
│    80/tcp  open  http                                       │
│    445/tcp open  microsoft-ds                               │
│                                                              │
│    Nmap done: 1 IP address (1 host up) scanned"           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ FORMAT RESULT
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ FORMATTED EXECUTION RESULT                                  │
├─────────────────────────────────────────────────────────────┤
│ ExecuteResult:                                              │
│   context: {                                                │
│     action: "Shell",                                         │
│     instruction: "<execute>nmap -T5 -p- 192.168.1.100...", │
│     code: ["nmap -T5 -p- 192.168.1.100"]                   │
│   }                                                          │
│   response:                                                 │
│     "Action: nmap -T5 -p- 192.168.1.100                    │
│      Observation: Starting Nmap 7.94...                     │
│      PORT    STATE SERVICE                                  │
│      22/tcp  open  ssh                                      │
│      80/tcp  open  http                                     │
│      445/tcp open  microsoft-ds                             │
│      Nmap done: 1 IP address (1 host up) scanned"         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ CHECK SUCCESS
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM REQUEST #4: SUCCESS CHECK                               │
├─────────────────────────────────────────────────────────────┤
│ Conversation: conv_react_001 (continues)                    │
│                                                              │
│ User Message:                                               │
│   "You are tasked with evaluating the success of the task   │
│    execution result...                                      │
│    ## Task Execution Result:                                │
│    Action: nmap -T5 -p- 192.168.1.100                      │
│    Observation: Starting Nmap 7.94...                       │
│    PORT    STATE SERVICE                                    │
│    22/tcp  open  ssh                                        │
│    80/tcp  open  http                                       │
│    445/tcp open  microsoft-ds..."                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ LLM RESPONSE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM RESPONSE #4: SUCCESS EVALUATION                         │
├─────────────────────────────────────────────────────────────┤
│ Response Text:                                              │
│   "yes"                                                      │
│                                                              │
│ Parsed:                                                     │
│   is_success: true (contains "yes")                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ UPDATE TASK
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ TASK STATUS UPDATE                                          │
├─────────────────────────────────────────────────────────────┤
│ Task 0 (in memory):                                         │
│   is_finished: true                                          │
│   is_success: true                                           │
│   code: ["nmap -T5 -p- 192.168.1.100"]                     │
│   result: "Action: nmap -T5 -p- 192.168.1.100\n..."        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ UPDATE PLAN
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM REQUEST #5: PLAN UPDATE                                 │
├─────────────────────────────────────────────────────────────┤
│ Conversation: conv_plan_001 (continues planning thread)     │
│                                                              │
│ User Message:                                               │
│   "You are required to revise the plan based on the         │
│    provided execution details...                            │
│    ## Init Description:                                     │
│    Penetration test on 192.168.1.100                       │
│                                                              │
│    ## Finished Tasks                                        │
│       ### Successful Tasks                                  │
│       ["Scan all ports on 192.168.1.100"]                  │
│       ### Failed Tasks                                      │
│       []                                                     │
│                                                              │
│    ## Current Task                                          │
│    Scan all ports on 192.168.1.100                         │
│                                                              │
│    ## Task Execution Command:                               │
│    ["nmap -T5 -p- 192.168.1.100"]                          │
│                                                              │
│    ## Task Execution Result:                                │
│    Action: nmap -T5 -p- 192.168.1.100                      │
│    Observation: ...22/tcp open ssh, 80/tcp open http,      │
│    445/tcp open microsoft-ds..."                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ LLM RESPONSE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM RESPONSE #5: UPDATED PLAN                               │
├─────────────────────────────────────────────────────────────┤
│ Response Text:                                              │
│   "Based on the scan results showing SSH (22), HTTP (80),   │
│    and SMB (445) services, here's the updated plan:         │
│    <json>                                                    │
│    [                                                         │
│      {                                                       │
│        "id": "1",                                            │
│        "dependent_task_ids": [],                            │
│        "instruction": "Scan all ports on 192.168.1.100",    │
│        "action": "Shell"                                     │
│      },                                                      │
│      {                                                       │
│        "id": "2",                                            │
│        "dependent_task_ids": ["1"],                         │
│        "instruction": "Enumerate SSH service on port 22",   │
│        "action": "Shell"                                     │
│      },                                                      │
│      {                                                       │
│        "id": "3",                                            │
│        "dependent_task_ids": ["1"],                         │
│        "instruction": "Enumerate HTTP service on port 80",  │
│        "action": "Shell"                                     │
│      },                                                      │
│      {                                                       │
│        "id": "4",                                            │
│        "dependent_task_ids": ["1"],                         │
│        "instruction": "Enumerate SMB on port 445",          │
│        "action": "Shell"                                     │
│      }                                                       │
│    ]                                                         │
│    </json>"                                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ MERGE TASKS
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ TASK MERGING LOGIC                                          │
├─────────────────────────────────────────────────────────────┤
│ Old Plan (3 tasks):                                         │
│   Task 0: "Scan all ports" (SUCCESS)                        │
│   Task 1: "Identify services" (NOT STARTED)                 │
│   Task 2: "Check banners" (NOT STARTED)                     │
│                                                              │
│ New Plan (4 tasks):                                         │
│   Task "1": "Scan all ports" (keep from old)                │
│   Task "2": "Enumerate SSH"                                 │
│   Task "3": "Enumerate HTTP"                                │
│   Task "4": "Enumerate SMB"                                 │
│                                                              │
│ Merge Result:                                               │
│   Task 0: "Scan all ports" (SUCCESS, keep)                  │
│   Task 1: "Enumerate SSH" (new)                             │
│   Task 2: "Enumerate HTTP" (new)                            │
│   Task 3: "Enumerate SMB" (new)                             │
│                                                              │
│ Next Task: Task 1 (first unfinished)                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ CONTINUE REACT LOOP
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ REACT ITERATION #2: Next Task                               │
├─────────────────────────────────────────────────────────────┤
│ [Repeat: Task Details → Code Gen → Execute → Check → Update]│
└─────────────────────────────────────────────────────────────┘
    │
    │ ... (continues for max_interactions or until no tasks)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ROLE COMPLETION                                             │
├─────────────────────────────────────────────────────────────┤
│ After 5 iterations or all tasks done:                       │
│                                                              │
│ 1. Save all tasks to database                               │
│    UPDATE tasks SET ... WHERE plan_id = "plan_001"          │
│                                                              │
│ 2. Update session:                                          │
│    UPDATE sessions SET                                      │
│      current_role_name = "SCANNER",                         │
│      history_planner_ids = "plan_001",                      │
│      current_planner_id = ""                                │
│                                                              │
│ 3. Instantiate Scanner role                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ NEXT ROLE
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ SCANNER ROLE - PLANNING PHASE                               │
├─────────────────────────────────────────────────────────────┤
│ 1. GET SUMMARY                                              │
│    history_planner_ids: ["plan_001"]                        │
│    Query DB for plan_001's finished tasks                   │
│    Generate summary via LLM                                 │
│                                                              │
│ 2. BUILD PLANNING PROMPT                                    │
│    Template: init_plan_prompt                               │
│    Variables:                                               │
│      - goal: "Check for vulnerabilities..."                 │
│      - tools: "Nikto, Dirb, Whatweb, Sqlmap..."            │
│      - context: [summary from Collector phase]              │
│                                                              │
│ 3. [Rest of planning flow same as Collector]               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    │ ... [Scanner completes] → [Exploiter runs] → END
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ FINAL: SAVE SESSION                                         │
├─────────────────────────────────────────────────────────────┤
│ Prompt user: "Enter session name: "                         │
│ Input: "webserver_pentest"                                  │
│                                                              │
│ UPDATE sessions SET                                         │
│   name = "webserver_pentest"                                │
│ WHERE id = "abc123"                                          │
│                                                              │
│ Close SSH connection                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## User Input Processing

### Initial User Input

**Entry Point**: `pentest.py` → `initialize_session()`

```python
# User is prompted:
>>> Please describe the penetration testing task.
>>> Penetration test on web server at 192.168.1.100
```

**Data Structure Created**:
```python
session = Session(
    id="generated_uuid",
    name=None,  # Set at end
    init_description="Penetration test on web server at 192.168.1.100",
    current_role_name="COLLECTOR",
    current_planner_id="",
    history_planner_ids=[]
)
```

**Data Flow**:
```
User Input (string)
    │
    ├─> Stored in: session.init_description
    │
    ├─> Used in: Planning prompts (all roles)
    │
    ├─> Used in: Plan updates (for context)
    │
    └─> Persisted in: DB → sessions.init_description
```

---

## Phase 1: Initial Planning

### Step 1: Summary Generation

**Trigger**: `role._plan(session)`

**Input Data**:
```python
history_planner_ids = session.history_planner_ids  # [] for first role
```

**For First Role (Collector)**:
```python
# No history, returns empty string
summary = ""
```

**For Subsequent Roles (Scanner, Exploiter)**:

**Database Query**:
```sql
SELECT * FROM tasks 
WHERE plan_id IN ('plan_001') 
  AND is_finished = true 
  AND is_success = true
```

**Retrieved Data**:
```python
finished_tasks = [
    {
        "instruction": "Scan all ports on 192.168.1.100",
        "code": ["nmap -T5 -p- 192.168.1.100"],
        "result": "...22/tcp open ssh, 80/tcp open http, 445/tcp open microsoft-ds..."
    },
    {
        "instruction": "Enumerate SSH service on port 22",
        "code": ["nmap -sV -p 22 192.168.1.100"],
        "result": "...SSH-2.0-OpenSSH_7.9p1..."
    }
]
```

**Prompt to LLM**:
```
User Message:
"You are an autonomous agent tasked with summarizing your historical activities.
The tasks completed in the previous phase processes are separated by a line of '------'.
Based on the tasks listed from the previous phase, generate a concise summary...

**Instruction**: Scan all ports on 192.168.1.100
**Code**: nmap -T5 -p- 192.168.1.100
**Result**: ...22/tcp open ssh, 80/tcp open http, 445/tcp open microsoft-ds...
------
**Instruction**: Enumerate SSH service on port 22
**Code**: nmap -sV -p 22 192.168.1.100
**Result**: ...SSH-2.0-OpenSSH_7.9p1...
------"
```

**LLM Response (Summary)**:
```
"Previous Phase Summary:

The information collection phase successfully identified three open services on 
target 192.168.1.100:

1. SSH (port 22): Running OpenSSH 7.9p1
2. HTTP (port 80): Web server active
3. SMB (port 445