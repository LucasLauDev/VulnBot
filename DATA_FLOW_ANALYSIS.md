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
3. SMB (port 445): Microsoft DS service detected

The target is running a Linux system based on the SSH banner. All three services 
are potential entry points for vulnerability assessment in the next phase."
```

**Data Stored**:
```python
context = summary  # Used in next planning prompt
```

---

### Step 2: Initialize Conversations

**Trigger**: First time role runs

**Action**: Create two LLM conversation threads

```python
# Planning conversation - for generating and updating plans
(_, plan_chat_id) = _chat(
    query=init_plan_prompt,
    conversation_id=None  # New conversation
)
# Returns: "conv_001"

# Reasoning conversation - for task details and success checks
(_, react_chat_id) = _chat(
    query=init_reasoning_prompt,
    conversation_id=None  # New conversation  
)
# Returns: "conv_002"
```

**Database Inserts**:
```sql
INSERT INTO conversations (id, name, chat_type) 
VALUES ('conv_001', 'gpt-4', 'llm_chat');

INSERT INTO conversations (id, name, chat_type)
VALUES ('conv_002', 'gpt-4', 'llm_chat');
```

---

### Step 3: Build Planning Prompt

**Input Variables**:
```python
init_description = "Penetration test on web server at 192.168.1.100"
goal = "Perform full scan to identify all open ports and services"
tools = "Nmap, Curl, Wget, Tcpdump, Whois, Dmitry, Dnsenum, Netdiscover..."
context = ""  # Empty for Collector, summary for other roles
```

**Prompt Template** (`CollectorPrompt.init_plan_prompt`):
```python
f"""
You are a penetration tester in the Information Collection phase.

## Initial Description:
{init_description}

## Your Goal:
{goal}

## Available Tools:
{tools}

## Context from Previous Phases:
{context}

Generate a plan with 1-5 tasks using the format:
<json>
[
  {{
    "id": "unique_id",
    "dependent_task_ids": [],
    "instruction": "detailed instruction including target IP",
    "action": "Shell" or "Web"
  }}
]
</json>
"""
```

**RAG Enhancement (if enabled)**:
```python
if enable_rag:
    # Query knowledge base
    docs = search_docs(
        query=init_description,  # "Penetration test on web server at 192.168.1.100"
        knowledge_base_name="pentest_kb",
        top_k=3
    )
    # Returns: [
    #   {"page_content": "For web server testing, start with nmap...", "score": 0.89},
    #   {"page_content": "Common web server ports: 80, 443, 8080...", "score": 0.85}
    # ]
    
    # Rerank
    docs = reranker.compress_documents(docs, init_description)
    # Returns top 1: [{"page_content": "For web server testing, start with nmap..."}]
    
    # Append to prompt
    context = "\n".join([doc["page_content"] for doc in docs])
    prompt += f"\n\nRelevant Knowledge: {context}"
```

**Final Assembled Prompt**:
```
System: You are a helpful assistant

User: You are a penetration tester in the Information Collection phase.

## Initial Description:
Penetration test on web server at 192.168.1.100

## Your Goal:
Perform full scan to identify all open ports and services

## Available Tools:
Nmap, Curl, Wget, Tcpdump, Whois, Dmitry, Dnsenum, Netdiscover, Amap, 
Enum4linux, Smbclient, Amass, SSLscan, SpiderFoot, Fierce

## Context from Previous Phases:
[empty or summary from previous roles]

[Optional] Relevant Knowledge:
For web server testing, start with nmap port scanning to identify open ports...

Generate a plan with 1-5 tasks...
<json>[...]</json>
```

---

### Step 4: LLM Plan Generation

**LLM Processing**:
- Model: GPT-4 (or configured model)
- Temperature: 0.5
- Max tokens: Based on context_length config

**LLM Response**:
```json
{
  "raw_response": "Based on the target description, I'll create a reconnaissance plan:\n\n<json>\n[\n  {\n    \"id\": \"1\",\n    \"dependent_task_ids\": [],\n    \"instruction\": \"Perform comprehensive port scan on 192.168.1.100 to identify all open TCP/UDP ports\",\n    \"action\": \"Shell\"\n  },\n  {\n    \"id\": \"2\",\n    \"dependent_task_ids\": [\"1\"],\n    \"instruction\": \"Identify service versions on discovered open ports for 192.168.1.100\",\n    \"action\": \"Shell\"\n  },\n  {\n    \"id\": \"3\",\n    \"dependent_task_ids\": [\"2\"],\n    \"instruction\": \"Perform HTTP enumeration on web server at 192.168.1.100:80\",\n    \"action\": \"Shell\"\n  }\n]\n</json>"
}
```

**Message Saved to DB**:
```sql
INSERT INTO messages (id, conversation_id, chat_type, query, response)
VALUES (
  'msg_001',
  'conv_001',  -- plan_chat_id
  'llm_chat',
  '[full planning prompt]',
  '[LLM response with JSON]'
);
```

---

### Step 5: JSON Parsing

**Extraction Process**:
```python
# 1. Extract JSON from tags
regex = r"<json>(.*?)</json>"
match = re.search(regex, raw_response, re.DOTALL)
json_string = match.group(1).strip()
# Result: "[{\"id\":\"1\",...}]"

# 2. Parse JSON
tasks_data = json.loads(json_string)
# Result: [
#   {"id": "1", "dependent_task_ids": [], "instruction": "...", "action": "Shell"},
#   {"id": "2", "dependent_task_ids": ["1"], "instruction": "...", "action": "Shell"},
#   {"id": "3", "dependent_task_ids": ["2"], "instruction": "...", "action": "Shell"}
# ]
```

**Task Object Creation**:
```python
for idx, task_data in enumerate(tasks_data):
    task = Task(
        id=generate_uuid(),  # "task_001"
        plan_id=current_plan.id,  # "plan_001"
        sequence=idx,  # 0, 1, 2
        action=task_data["action"],  # "Shell"
        instruction=task_data["instruction"],  # "Perform comprehensive port scan..."
        code=[],  # Empty initially
        result="",  # Empty initially
        is_success=False,
        is_finished=False,
        dependencies=[  # Convert task IDs to sequences
            i for i, t in enumerate(tasks_data)
            if t["id"] in task_data["dependent_task_ids"]
        ]  # [0] for task 2, [1] for task 3
    )
```

**Dependency Resolution Example**:
```python
tasks_data = [
  {"id": "1", "dependent_task_ids": []},
  {"id": "2", "dependent_task_ids": ["1"]},
  {"id": "3", "dependent_task_ids": ["2"]}
]

# Task 0: dependencies = [] (no deps)
# Task 1: dependencies = [0] (depends on sequence 0)
# Task 2: dependencies = [1] (depends on sequence 1)
```

---

### Step 6: Database Persistence

**Plan Insert**:
```sql
INSERT INTO plans (id, goal, current_task_sequence, plan_chat_id, react_chat_id)
VALUES (
  'plan_001',
  'Perform full scan to identify all open ports and services',
  0,
  'conv_001',
  'conv_002'
);
```

**Tasks Insert**:
```sql
INSERT INTO tasks (id, plan_id, sequence, action, instruction, code, result, 
                   is_success, is_finished, dependencies)
VALUES
  ('task_001', 'plan_001', 0, 'Shell', 
   'Perform comprehensive port scan on 192.168.1.100...', 
   '[]', '', false, false, '[]'),
   
  ('task_002', 'plan_001', 1, 'Shell',
   'Identify service versions on discovered open ports...',
   '[]', '', false, false, '[0]'),
   
  ('task_003', 'plan_001', 2, 'Shell',
   'Perform HTTP enumeration on web server at 192.168.1.100:80',
   '[]', '', false, false, '[1]');
```

**Session Update**:
```sql
UPDATE sessions 
SET current_planner_id = 'plan_001'
WHERE id = 'abc123';
```

---

## Phase 2: Task Execution Loop

### Iteration 1: First Task

#### Step 1: Get Current Task

**Query Logic**:
```python
# Get sorted tasks (topological sort by dependencies)
sorted_tasks = plan.get_sorted_tasks()
# Result: [task_001, task_002, task_003]

# Find first unfinished
current_task = None
for task in sorted_tasks:
    if not task.is_finished:
        current_task = task
        break
# Result: task_001
```

**Current Task Data**:
```python
task_001 = {
    "id": "task_001",
    "sequence": 0,
    "instruction": "Perform comprehensive port scan on 192.168.1.100 to identify all open TCP/UDP ports",
    "action": "Shell",
    "dependencies": []
}
```

---

#### Step 2: Get Task Details

**Prompt Construction**:
```python
query = f"""
Now you're provided with an input that contains the penetration testing next task.
You need to generate the executable-specific details to complete the next task.

## Next Task:
{task.instruction}

## Output Requirements:
1. Clearly state the task to be executed in no more than three sentences.
   - Provide a description of the task
   - List the exact command to be executed
   - Explain why this task is necessary
2. Be concise and precise in your output.
"""

# With RAG:
if enable_rag:
    kb_query = task.instruction
    docs = search_docs(kb_query, kb_name="pentest_kb")
    # Might return: "Use nmap with -T5 for fast scanning, -p- for all ports..."
```

**LLM Request**:
```
Conversation: conv_002 (react_chat_id)
History: [] (first message in this conversation)

System: You are a helpful assistant

User: Now you're provided with an input that contains the penetration testing next task...

## Next Task:
Perform comprehensive port scan on 192.168.1.100 to identify all open TCP/UDP ports

[Optional RAG Context]
Relevant Knowledge: Use nmap with -T5 for fast scanning, -p- for all ports...
```

**LLM Response**:
```
"Task: Conduct a full port scan on target 192.168.1.100.

Command: nmap -T5 -p- 192.168.1.100

Purpose: This initial reconnaissance scan will identify all listening services by 
scanning all 65535 TCP ports. The -T5 flag enables aggressive timing for faster 
results. This information is critical for subsequent service enumeration and 
vulnerability assessment phases."
```

**Message Saved**:
```sql
INSERT INTO messages (id, conversation_id, query, response)
VALUES (
  'msg_002',
  'conv_002',
  'Now you\'re provided with...\n## Next Task:\nPerform comprehensive port scan...',
  'Task: Conduct a full port scan...\n\nCommand: nmap -T5 -p- 192.168.1.100...'
);
```

---

#### Step 3: Generate Executable Code

**Prompt Construction**:
```python
next_task_details = """Task: Conduct a full port scan on target 192.168.1.100.
Command: nmap -T5 -p- 192.168.1.100
Purpose: This initial reconnaissance scan will identify..."""

query = f"""
You play as an autonomous penetration testing assistant running on Kali Linux 2023.
Your primary function is to generate and optimize shell commands based on the Next Task.

## Core Capabilities:
- Expert knowledge of command-line penetration testing tools
- Deep understanding of Kali Linux 2023's tool ecosystem
- Parameter validation and optimization

## Command Generation Rules:
1. All commands must be wrapped in <execute></execute> tags
2. Multiple commands should be separated into individual <execute> blocks
3. Commands must use parameters available in Kali Linux 2023
4. Optimize commands for execution speed
5. Cannot add command

## Output Format:
<execute>[optimized command]</execute>

**Next Task**: {next_task_details}
"""
```

**LLM Request**:
```
Conversation: NEW (no conversation_id, one-shot request)

System: You are a helpful assistant

User: You play as an autonomous penetration testing assistant...
**Next Task**: Task: Conduct a full port scan...
Command: nmap -T5 -p- 192.168.1.100...
```

**LLM Response**:
```
"<execute>nmap -T5 -p- 192.168.1.100</execute>"
```

**Command Extraction**:
```python
# Regex pattern
pattern = r'<execute>\s*(.*?)\s*</execute>'
commands = re.findall(pattern, response, re.DOTALL)
# Result: ["nmap -T5 -p- 192.168.1.100"]
```

---

#### Step 4: Execute Commands on Kali

**SSH Connection**:
```python
# Get shell (singleton)
shell_manager = ShellManager.get_instance()
shell = shell_manager.get_shell()

# Shell connects via paramiko
# Host: 10.10.0.5:22
# User: root
# Password: [from config]
```

**Command Execution**:
```python
command = "nmap -T5 -p- 192.168.1.100"

# Send command
shell.shell.send(command + '\n')

# Wait for output (with prompt detection)
output = SSHOutputHandler.receive_data(shell.shell, timeout=120.0)
```

**Raw Output from Kali**:
```
root@kali:~# nmap -T5 -p- 192.168.1.100
Starting Nmap 7.94 ( https://nmap.org ) at 2024-01-15 10:30 UTC
Warning: 192.168.1.100 giving up on port because retransmission cap hit (2).
Nmap scan report for 192.168.1.100
Host is up (0.0012s latency).
Not shown: 65532 closed tcp ports (reset)
PORT    STATE SERVICE
22/tcp  open  ssh
80/tcp  open  http
445/tcp open  microsoft-ds
MAC Address: 00:0C:29:3F:3B:72 (VMware)

Nmap done: 1 IP address (1 host up) scanned in 45.23 seconds
root@kali:~#
```

**Output Processing**:
```python
# Format result
result = f"Action: {command}\nObservation: {output}\n"

# Result:
result = """
Action: nmap -T5 -p- 192.168.1.100
Observation: Starting Nmap 7.94 ( https://nmap.org ) at 2024-01-15 10:30 UTC
Nmap scan report for 192.168.1.100
Host is up (0.0012s latency).
Not shown: 65532 closed tcp ports (reset)
PORT    STATE SERVICE
22/tcp  open  ssh
80/tcp  open  http
445/tcp open  microsoft-ds
MAC Address: 00:0C:29:3F:3B:72 (VMware)
Nmap done: 1 IP address (1 host up) scanned in 45.23 seconds
"""
```

---

#### Step 5: Check Task Success

**Prompt Construction**:
```python
query = f"""
You are tasked with evaluating the success of the task execution result:
- If the Task Execution Result is empty, it will be considered unsuccessful.
- If the Task Execution Result contains any exceptions or errors, it will be unsuccessful.
- Please reply with "yes" if the task execution was successful.
- Please reply with "no" if the task execution was unsuccessful.

## Task Execution Result:
{result}
"""
```

**LLM Request**:
```
Conversation: conv_002 (continues react_chat_id conversation)

History:
  User: "Now you're provided with...## Next Task: Perform comprehensive port scan..."
  Assistant: "Task: Conduct a full port scan...Command: nmap -T5 -p- 192.168.1.100..."

Current Message:
  User: "You are tasked with evaluating the success...
         ## Task Execution Result:
         Action: nmap -T5 -p- 192.168.1.100
         Observation: ...PORT STATE SERVICE\n22/tcp open ssh\n80/tcp open http..."
```

**LLM Response**:
```
"yes"
```

**Success Evaluation**:
```python
check_success = "yes"
is_success = "yes" in check_success.lower()  # True
```

**Task Update (In Memory)**:
```python
task_001.is_finished = True
task_001.is_success = True
task_001.code = ["nmap -T5 -p- 192.168.1.100"]
task_001.result = """Action: nmap -T5 -p- 192.168.1.100
Observation: ...PORT STATE SERVICE..."""
```

---

## Phase 3: Plan Adaptation

### Step 1: Build Update Prompt

**Gather Context**:
```python
# Finished successful tasks
success_tasks = [
    "Perform comprehensive port scan on 192.168.1.100 to identify all open TCP/UDP ports"
]

# Finished failed tasks
fail_tasks = []  # None yet

# Current task info
current_task = task_001
current_code = ["nmap -T5 -p- 192.168.1.100"]
task_result = """Action: nmap -T5 -p- 192.168.1.100
Observation: PORT STATE SERVICE
22/tcp open ssh
80/tcp open http
445/tcp open microsoft-ds"""
```

**Prompt Template**:
```python
query = f"""
You are required to revise the plan based on the provided execution details:
- Maintain the existing JSON structure
- The Successful Tasks in the Finished Tasks must be retained in the plan
- Update the plan in accordance with the provided task execution result
- Only add new tasks when necessary and directly related to the current penetration testing step
- Ensure the revised plan is clear, organized, and free of unrelated information
- Always include the target IP or port in the instruction
- If no task is applicable for this stage, the output should be empty
- Consider shell sharing (if already in a shell, don't re-execute preceding command)

## Init Description:
{init_description}

## Finished Tasks
   ### Successful Tasks
   {success_tasks}
   ### Failed Tasks
   {fail_tasks}

## Current Task
{current_task.instruction}

## Task Execution Command:
{current_code}

## Task Execution Result:
{task_result}
"""
```

**Assembled Prompt**:
```
You are required to revise the plan based on the provided execution details...

## Init Description:
Penetration test on web server at 192.168.1.100

## Finished Tasks
   ### Successful Tasks
   ["Perform comprehensive port scan on 192.168.1.100 to identify all open TCP/UDP ports"]
   ### Failed Tasks
   []

## Current Task
Perform comprehensive port scan on 192.168.1.100 to identify all open TCP/UDP ports

## Task Execution Command:
["nmap -T5 -p- 192.168.1.100"]

## Task Execution Result:
Action: nmap -T5 -p- 192.168.1.100
Observation: PORT STATE SERVICE
22/tcp open ssh
80/tcp open http
445/tcp open microsoft-ds
MAC Address: 00:0C:29:3F:3B:72 (VMware)
Nmap done: 1 IP address (1 host up) scanned in 45.23 seconds
```

---

### Step 2: LLM Plan Update

**LLM Request**:
```
Conversation: conv_001 (plan_chat_id - continues planning conversation)

History:
  User: "## Available Action Types: Shell, Web\n## Task: Based on context, write a plan..."
  Assistant: "<json>[{\"id\":\"1\", \"instruction\":\"Perform comprehensive port scan...\"...}]</json>"

Current Message:
  User: "You are required to revise the plan based on the provided execution details...
         ## Task Execution Result:
         Observation: PORT STATE SERVICE\n22/tcp open ssh\n80/tcp open http\n445/tcp open microsoft-ds..."
```

**LLM Response**:
```
"Based on the scan results showing three open services (SSH on 22, HTTP on 80, SMB on 445), 
I'm updating the plan to enumerate each discovered service:

<json>
[
  {
    "id": "1",
    "dependent_task_ids": [],
    "instruction": "Perform comprehensive port scan on 192.168.1.100 to identify all open TCP/UDP ports",
    "action": "Shell"
  },
  {
    "id": "2",
    "dependent_task_ids": ["1"],
    "instruction": "Enumerate SSH service version and configuration on 192.168.1.100:22",
    "action": "Shell"
  },
  {
    "id": "3",
    "dependent_task_ids": ["1"],
    "instruction": "Enumerate HTTP web server and identify technologies on 192.168.1.100:80",
    "action": "Shell"
  },
  {
    "id": "4",
    "dependent_task_ids": ["1"],
    "instruction": "Enumerate SMB shares and version on 192.168.1.100:445",
    "action": "Shell"
  },
  {
    "id": "5",
    "dependent_task_ids": ["2", "3", "4"],
    "instruction": "Gather OS fingerprint and system information from 192.168.1.100",
    "action": "Shell"
  }
]
</json>"
```

**Message Saved**:
```sql
INSERT INTO messages (id, conversation_id, query, response)
VALUES (
  'msg_003',
  'conv_001',
  'You are required to revise the plan based on...',
  'Based on the scan results showing three open services...\n<json>[...]</json>'
);
```

---

### Step 3: Merge Tasks

**Old Plan Tasks**:
```python
old_tasks = [
    {"sequence": 0, "instruction": "Perform comprehensive port scan...", "is_finished": True, "is_success": True},
    {"sequence": 1, "instruction": "Identify service versions...", "is_finished": False},
    {"sequence": 2, "instruction": "Perform HTTP enumeration...", "is_finished": False}
]
```

**New Plan from LLM**:
```python
new_tasks_json = [
    {"id": "1", "instruction": "Perform comprehensive port scan..."},  # Same as old task 0
    {"id": "2", "instruction": "Enumerate SSH service version..."},      # New
    {"id": "3", "instruction": "Enumerate HTTP web server..."},          # Modified
    {"id": "4", "instruction": "Enumerate SMB shares..."},               # New
    {"id": "5", "instruction": "Gather OS fingerprint..."}               # New
]
```

**Merge Logic**:
```python
# Step 1: Keep all successful tasks from old plan
completed_tasks_map = {
    "Perform comprehensive port scan...": old_task_0  # is_success=True
}

# Step 2: For each new task
merged_tasks = []

for task_data in new_tasks_json:
    if task_data["instruction"] in completed_tasks_map:
        # Keep old task (preserves code, result, success status)
        existing_task = completed_tasks_map[task_data["instruction"]]
        existing_task.sequence = len(merged_tasks)
        merged_tasks.append(existing_task)
    else:
        # Create new task
        new_task = Task(
            sequence=len(merged_tasks),
            instruction=task_data["instruction"],
            action=task_data["action"],
            dependencies=[...],  # Resolved from dependent_task_ids
            is_finished=False,
            is_success=False
        )
        merged_tasks.append(new_task)

# Result:
merged_tasks = [
    Task 0: "Perform comprehensive port scan..." (SUCCESS, from old),
    Task 1: "Enumerate SSH service version..." (new, unfinished),
    Task 2: "Enumerate HTTP web server..." (new, unfinished),
    Task 3: "Enumerate SMB shares..." (new, unfinished),
    Task 4: "Gather OS fingerprint..." (new, unfinished)
]
```

**Next Task Selection**:
```python
# Get first unfinished task
next_task = merged_tasks[1]  # Task 1: "Enumerate SSH service version..."
```

---

### React Loop Continues

**Iteration 2**: Execute Task 1 (Enumerate SSH)
**Iteration 3**: Execute Task 2 (Enumerate HTTP)
**Iteration 4**: Execute Task 3 (Enumerate SMB)
**Iteration 5**: Execute Task 4 (Gather OS fingerprint)

*OR*

**Max Interactions Reached**: After 5 iterations, exit loop even if tasks remain

---

## Role Transitions

### End of Collector Phase

**Trigger**: `put_message(session)`

**Step 1: Save Tasks to Database**:
```sql
UPDATE tasks 
SET 
  code = '["nmap -T5 -p- 192.168.1.100"]',
  result = 'Action: nmap -T5 -p- 192.168.1.100\nObservation: PORT STATE SERVICE...',
  is_finished = true,
  is_success = true
WHERE id = 'task_001';

-- Repeat for all modified tasks...
```

**Step 2: Update Session**:
```python
# Add current plan to history
session.history_planner_ids.append(planner.current_plan.id)
# Result: history_planner_ids = ['plan_001']

# Move to next role
session.current_role_name = RoleType.SCANNER.value
# Result: current_role_name = 'SCANNER'

# Clear current planner (Scanner will create its own)
session.current_planner_id = ''
```

**Step 3: Database Update**:
```sql
UPDATE sessions
SET 
  current_role_name = 'SCANNER',
  history_planner_ids = 'plan_001',  -- Comma-separated if multiple
  current_planner_id = ''
WHERE id = 'abc123';
```

**Step 4: Instantiate Next Role**:
```python
# In Collector.put_message()
if message.current_role_name == RoleType.COLLECTOR.value:
    message.current_role_name = RoleType.SCANNER.value
    message.history_planner_ids.append(self.planner.current_plan.id)
    message.current_planner_id = ''
    
    # Create and run Scanner
    Scanner(console=self.console, max_interactions=self.max_interactions).run(message)
```

---

### Scanner Phase Begins

**Initial State**:
```python
session = {
    "current_role_name": "SCANNER",
    "current_planner_id": "",
    "history_planner_ids": ["plan_001"],
    "init_description": "Penetration test on web server at 192.168.1.100"
}
```

**Step 1: Generate Summary of Previous Phase**:

```python
# Query database
SELECT * FROM tasks 
WHERE plan_id = 'plan_001' 
  AND is_finished = true 
  AND is_success = true;

# Retrieved:
tasks = [
    {
        "instruction": "Perform comprehensive port scan on 192.168.1.100",
        "code": ["nmap -T5 -p- 192.168.1.100"],
        "result": "...PORT 22/tcp open ssh, 80/tcp open http, 445/tcp open microsoft-ds..."
    },
    {
        "instruction": "Enumerate SSH service version on 192.168.1.100:22",
        "code": ["nmap -sV -p 22 192.168.1.100"],
        "result": "...SSH-2.0-OpenSSH_7.9p1 Debian-10+deb10u2..."
    },
    # ... more tasks
]
```

**Prompt to LLM for Summary**:
```
You are an autonomous agent tasked with summarizing your historical activities.

**Instruction**: Perform comprehensive port scan on 192.168.1.100
**Code**: nmap -T5 -p- 192.168.1.100
**Result**: PORT 22/tcp open ssh, 80/tcp open http, 445/tcp open microsoft-ds
------
**Instruction**: Enumerate SSH service version on 192.168.1.100:22
**Code**: nmap -sV -p 22 192.168.1.100
**Result**: SSH-2.0-OpenSSH_7.9p1 Debian-10+deb10u2
------
[... all successful tasks from Collector phase]
```

**LLM Summary Response**:
```
"Previous Phase Summary:

Information Collection Phase completed successfully:

Target: 192.168.1.100 (Debian Linux system)

Discovered Services:
1. SSH (22/tcp): OpenSSH 7.9p1 Debian-10+deb10u2
2. HTTP (80/tcp): Apache/2.4.38 (Debian)
3. SMB (445/tcp): Samba smbd 4.9.5-Debian

Key Findings:
- Target is a Debian 10 system
- Web server running Apache with default configuration
- File sharing enabled via Samba
- No unusual ports detected

Recommended focus for vulnerability scanning: Web application vulnerabilities, 
SMB enumeration, and SSH authentication testing."
```

**Step 2: Scanner Planning**:

**Prompt to LLM**:
```
You are a penetration tester in the Vulnerability Scanner phase.

## Initial Description:
Penetration test on web server at 192.168.1.100

## Your Goal:
Based on reconnaissance results, further enumeration and check for vulnerabilities 
and misconfigurations in the target.

## Available Tools:
Nikto, Curl, Dirb, Whatweb, WPScan, Sqlmap, ExploitDB, Wapiti, Aircrack-ng, 
Webshells, Weevely, Tshark, Nmap(with NSE scripts)

## Context from Previous Phases:
Information Collection Phase completed successfully:
Target: 192.168.1.100 (Debian Linux system)
Discovered Services:
1. SSH (22/tcp): OpenSSH 7.9p1 Debian-10+deb10u2
2. HTTP (80/tcp): Apache/2.4.38 (Debian)
3. SMB (445/tcp): Samba smbd 4.9.5-Debian
[...]

Generate a plan with 1-5 tasks...
<json>[...]</json>
```

**LLM Planning Response**:
```json
<json>
[
  {
    "id": "1",
    "dependent_task_ids": [],
    "instruction": "Perform web vulnerability scan on http://192.168.1.100 using Nikto",
    "action": "Shell"
  },
  {
    "id": "2",
    "dependent_task_ids": [],
    "instruction": "Enumerate web directories and files on 192.168.1.100 using Dirb",
    "action": "Shell"
  },
  {
    "id": "3",
    "dependent_task_ids": ["1", "2"],
    "instruction": "Test for SQL injection vulnerabilities on discovered web pages at 192.168.1.100",
    "action": "Shell"
  },
  {
    "id": "4",
    "dependent_task_ids": [],
    "instruction": "Run NSE vulnerability scripts against SMB service on 192.168.1.100:445",
    "action": "Shell"
  }
]
</json>
```

**Scanner continues with same Plan-React cycle...**

---

### Exploiter Phase

After Scanner completes, similar transition occurs:

```python
session = {
    "current_role_name": "EXPLOITER",
    "current_planner_id": "",
    "history_planner_ids": ["plan_001", "plan_002"],  # Collector + Scanner
    "init_description": "Penetration test on web server at 192.168.1.100"
}
```

**Summary Generation**: Includes findings from both Collector and Scanner phases

**Example Exploiter Plan**:
```json
[
  {
    "id": "1",
    "instruction": "Attempt SQL injection exploit on login form at http://192.168.1.100/admin",
    "action": "Shell"
  },
  {
    "id": "2",
    "instruction": "Use Hydra to perform password brute force on SSH at 192.168.1.100:22",
    "action": "Shell"
  },
  {
    "id": "3",
    "dependent_task_ids": ["1"],
    "instruction": "If SQL injection successful, dump database credentials from 192.168.1.100",
    "action": "Shell"
  }
]
```

---

## RAG Data Flow

### When RAG is Enabled

**Configuration**:
```yaml
# basic_config.yaml
enable_rag: true

# kb_config.yaml
kb_name: "pentest_kb"
top_k: 3
top_n: 1
score_threshold: 0.5
```

### RAG Query Flow

**Trigger Points**:
1. Initial planning (`_plan`)
2. Task details (`next_task_details`)
3. Plan updates (`update_plan`)

**Example: Task Details with RAG**

**Input**:
```python
kb_query = "Perform web vulnerability scan on http://192.168.1.100 using Nikto"
kb_name = "pentest_kb"
```

**Step 1: Generate Query Embedding**:
```python
from rag.embedding import EmbeddingModel

embedding_model = EmbeddingModel(
    model_name="maidalun1020/bce-embedding-base_v1"
)

query_embedding = embedding_model.encode(kb_query)
# Returns: [0.0234, -0.0123, 0.0456, ...] (768-dimensional vector)
```

**Step 2: Vector Search in Milvus**:
```python
from pymilvus import Collection

collection = Collection("pentest_kb")

search_results = collection.search(
    data=[query_embedding],
    anns_field="vector",
    param={"metric_type": "L2", "params": {"nprobe": 10}},
    limit=3,  # top_k
    expr=None
)

# Returns:
results = [
    {
        "id": "doc_001",
        "distance": 0.12,
        "page_content": "Nikto is a web vulnerability scanner. Use -h for host, -p for port. "
                        "Common command: nikto -h http://target.com -C all",
        "metadata": {"source": "nikto_guide.pdf", "page": 1}
    },
    {
        "id": "doc_045",
        "distance": 0.18,
        "page_content": "Web vulnerability scanning best practices: Always scan with SSL, "
                        "check for common misconfigurations, test for known CVEs.",
        "metadata": {"source": "web_testing_handbook.pdf", "page": 23}
    },
    {
        "id": "doc_112",
        "distance": 0.25,
        "page_content": "Apache web server vulnerabilities to check: mod_ssl exploits, "
                        "directory traversal, default credentials, outdated versions.",
        "metadata": {"source": "apache_security.md"}
    }
]
```

**Step 3: Filter by Score Threshold**:
```python
score_threshold = 0.5

# Convert distance to similarity score
filtered_docs = [
    doc for doc in results 
    if (1 - doc["distance"]) >= score_threshold
]

# Results: All 3 docs pass (scores: 0.88, 0.82, 0.75)
```

**Step 4: Reranking**:
```python
from rag.reranker import LangchainReranker

reranker = LangchainReranker(
    top_n=1,
    model_name="maidalun1020/bce-reranker-base_v1"
)

reranked_docs = reranker.compress_documents(
    documents=filtered_docs,
    query=kb_query
)

# Returns top 1:
final_doc = [
    {
        "page_content": "Nikto is a web vulnerability scanner. Use -h for host, -p for port. "
                        "Common command: nikto -h http://target.com -C all"
    }
]
```

**Step 5: Context Injection**:
```python
context = final_doc[0]["page_content"]

# Original query
original_query = "Now you're provided with..."

# Enhanced query
enhanced_query = f"""{original_query}


Ensure that the **Overall Target** IP or the IP from the **Initial Description** is prioritized. 
You will respond to questions and generate tasks based on the provided penetration test case materials: 
{context}
"""

# Result:
enhanced_query = """
Now you're provided with an input that contains the penetration testing next task...
## Next Task: Perform web vulnerability scan on http://192.168.1.100 using Nikto


Ensure that the **Overall Target** IP is prioritized.
You will respond based on the provided penetration test case materials:
Nikto is a web vulnerability scanner. Use -h for host, -p for port. 
Common command: nikto -h http://target.com -C all
"""
```

**Step 6: Send Enhanced Query to LLM**:
```python
response, conversation_id = _chat(
    query=enhanced_query,
    conversation_id=react_chat_id
)

# LLM now has domain knowledge context
```

**LLM Response with RAG Context**:
```
"Task: Execute Nikto web vulnerability scanner against the target web server.

Command: nikto -h http://192.168.1.100 -C all -p 80

Purpose: Nikto will scan for known vulnerabilities, misconfigurations, and security 
issues in the Apache web server. The -C all flag enables comprehensive checks, and 
-p 80 specifies the HTTP port discovered in the previous phase."
```

**Comparison Without RAG**:
```
"Task: Scan for web vulnerabilities.

Command: nikto -h 192.168.1.100

Purpose: Check for security issues."
```

*Notice: RAG-enhanced response includes proper syntax, parameter explanations, and context awareness.*

---

## Database Persistence Flow

### Data Persistence Points

**Throughout execution, data is continuously persisted:**

#### 1. Conversation Creation
```sql
-- When: Role initialization
INSERT INTO conversations (id, name, chat_type)
VALUES ('conv_001', 'gpt-4', 'llm_chat');
```

#### 2. Message Storage
```sql
-- When: After every LLM interaction
INSERT INTO messages (id, conversation_id, chat_type, query, response)
VALUES (
  'msg_001',
  'conv_001',
  'llm_chat',
  'You are a penetration tester...',
  '<json>[{"id":"1", "instruction":"..."}]</json>'
);
```

#### 3. Plan Creation
```sql
-- When: After initial planning
INSERT INTO plans (id, goal, current_task_sequence, plan_chat_id, react_chat_id)
VALUES (
  'plan_001',
  'Perform full scan to identify all open ports and services',
  0,
  'conv_001',
  'conv_002'
);
```

#### 4. Task Creation
```sql
-- When: Plan is parsed
INSERT INTO tasks (id, plan_id, sequence, action, instruction, code, result, 
                   is_success, is_finished, dependencies)
VALUES
  ('task_001', 'plan_001', 0, 'Shell', 'Perform comprehensive port scan...', 
   '[]', '', false, false, '[]');
```

#### 5. Task Updates
```sql
-- When: Task execution completes
UPDATE tasks
SET
  code = '["nmap -T5 -p- 192.168.1.100"]',
  result = 'Action: nmap...\nObservation: PORT STATE SERVICE...',
  is_finished = true,
  is_success = true
WHERE id = 'task_001';
```

#### 6. Session Updates
```sql
-- When: Role transitions
UPDATE sessions
SET
  current_role_name = 'SCANNER',
  history_planner_ids = 'plan_001',
  current_planner_id = ''
WHERE id = 'abc123';

-- When: Session saved at end
UPDATE sessions
SET name = 'webserver_pentest'
WHERE id = 'abc123';
```

### Data Retrieval Flow

**When resuming a session:**

```python
# 1. Fetch session
session = fetch_session_by_id('abc123')
# Returns: {current_role_name: 'SCANNER', current_planner_id: 'plan_002', ...}

# 2. If current_planner_id exists, fetch plan
if session.current_planner_id:
    plan = get_planner_by_id(session.current_planner_id)
    # Returns: Plan object with all tasks
    
# 3. Fetch conversation history
if plan:
    messages = get_conversation_messages(plan.plan_chat_id)
    # Returns: List of previous LLM interactions
    
# 4. Continue from current state
role = roles[session.current_role_name]  # Scanner
role.run(session)  # Resumes from where it left off
```

---

## Complete End-to-End Example

### Scenario: Simple Web Server Pentest

**User Input**:
```
>>> Please describe the penetration testing task.
>>> Test web application at 10.20.30.40
```

---

### COLLECTOR PHASE

#### LLM Interaction 1: Planning
**Input to LLM**:
```
Goal: Perform full scan to identify all open ports and services
Tools: Nmap, Curl, Wget...
Target: Test web application at 10.20.30.40
```

**Output from LLM**:
```json
[
  {"id": "1", "instruction": "Quick port scan on 10.20.30.40", "action": "Shell"},
  {"id": "2", "dependent_task_ids": ["1"], "instruction": "Service enumeration on 10.20.30.40", "action": "Shell"}
]
```

#### LLM Interaction 2: Task Details (Task 1)
**Input to LLM**:
```
Next Task: Quick port scan on 10.20.30.40
```

**Output from LLM**:
```
Task: Scan common ports
Command: nmap -F 10.20.30.40
Purpose: Fast discovery
```

#### LLM Interaction 3: Code Generation (Task 1)
**Input to LLM**:
```
Next Task: Task: Scan common ports
Command: nmap -F 10.20.30.40
```

**Output from LLM**:
```
<execute>nmap -F 10.20.30.40</execute>
```

#### Execution (Task 1)
**SSH Command**:
```bash
nmap -F 10.20.30.40
```

**Output**:
```
PORT    STATE SERVICE
22/tcp  open  ssh
80/tcp  open  http
443/tcp open  https
```

#### LLM Interaction 4: Success Check (Task 1)
**Input to LLM**:
```
Result: PORT 22/tcp open ssh, 80/tcp open http, 443/tcp open https
```

**Output from LLM**:
```
yes
```

#### LLM Interaction 5: Plan Update
**Input to LLM**:
```
Successful Tasks: ["Quick port scan on 10.20.30.40"]
Result: Found ports 22, 80, 443
```

**Output from LLM**:
```json
[
  {"id": "1", "instruction": "Quick port scan on 10.20.30.40", "action": "Shell"},
  {"id": "2", "instruction": "Enumerate HTTP on 10.20.30.40:80", "action": "Shell"},
  {"id": "3", "instruction": "Enumerate HTTPS on 10.20.30.40:443", "action": "Shell"},
  {"id": "4", "instruction": "Enumerate SSH on 10.20.30.40:22", "action": "Shell"}
]
```

#### Iterations 2-5
*Execute tasks 2, 3, 4...*

---

### SCANNER PHASE

#### LLM Interaction 6: Summary Generation
**Input to LLM**:
```
Summarize previous tasks:
- Quick port scan found 22, 80, 443
- HTTP running Apache 2.4.41
- HTTPS with valid SSL cert
- SSH OpenSSH 8.2p1
```

**Output from LLM**:
```
Target 10.20.30.40 runs Apache web server with SSL, SSH available
```

#### LLM Interaction 7: Scanner Planning
**Input to LLM**:
```
Goal: Check for vulnerabilities
Tools: Nikto, Dirb, Sqlmap...
Context: Apache 2.4.41, OpenSSH 8.2p1
```

**Output from LLM**:
```json
[
  {"id": "1", "instruction": "Nikto scan on http://10.20.30.40", "action": "Shell"},
  {"id": "2", "instruction": "Dirb directory brute force on 10.20.30.40", "action": "Shell"}
]
```

#### Iterations 1-5
*Execute vulnerability scans...*

---

### EXPLOITER PHASE

#### LLM Interaction 13: Exploiter Planning
**Input to LLM**:
```
Goal: Exploit vulnerabilities
Context: Found /admin panel, SQL injection possible, weak SSH passwords
```

**Output from LLM**:
```json
[
  {"id": "1", "instruction": "SQLmap on http://10.20.30.40/admin", "action": "Shell"},
  {"id": "2", "instruction": "Hydra SSH brute force on 10.20.30.40:22", "action": "Shell"}
]
```

#### Iterations 1-5
*Execute exploits...*

---

### SESSION SAVE

**Prompt**:
```
Please enter the name of the current session.
> webapp_test_jan2024
```

**Database Final State**:
```sql
SELECT * FROM sessions WHERE id = 'abc123';
-- name: webapp_test_jan2024
-- current_role_name: EXPLOITER
-- history_planner_ids: plan_001,plan_002,plan_003

SELECT COUNT(*) FROM tasks;
-- 15 total tasks

SELECT COUNT(*) FROM messages;
-- 47 LLM interactions
```

---

## Data Flow Summary

### Input → Output Chain

```
USER INPUT (string)
  ↓
SESSION OBJECT (Python)
  ↓
PLANNING PROMPT (string) → LLM → PLAN JSON (string)
  ↓
TASK OBJECTS (Python list)
  ↓
DATABASE (MySQL rows)
  ↓
TASK DETAILS PROMPT (string) → LLM → DETAILS (string)
  ↓
CODE GENERATION PROMPT (string) → LLM → COMMANDS (string)
  ↓
COMMAND EXTRACTION (regex) → COMMAND LIST (list)
  ↓
SSH EXECUTION (paramiko) → RAW OUTPUT (bytes)
  ↓
OUTPUT DECODING (string) → FORMATTED RESULT (string)
  ↓
SUCCESS CHECK PROMPT (string) → LLM → YES/NO (string)
  ↓
TASK UPDATE (boolean)
  ↓
UPDATE PROMPT (string) → LLM → NEW PLAN JSON (string)
  ↓
TASK MERGE (Python logic) → UPDATED TASK LIST
  ↓
DATABASE UPDATE (MySQL)
  ↓
NEXT ITERATION OR ROLE TRANSITION
  ↓
FINAL SESSION SAVE
```

### Key Transformations

| From | To | Method |
|------|----|---------|
| User description | Session object | `Session(**kwargs)` |
| Session + Goal | Planning prompt | Template substitution |
| LLM JSON | Task objects | `json.loads()` + `Task()` |
| Task instruction | Executable commands | LLM + regex extraction |
| Commands | Execution results | SSH + paramiko |
| Results | Success boolean | LLM evaluation |
| Results + Old plan | New plan | LLM + merge logic |
| Plan sequence | Task ordering | Topological sort |
| Tasks | Database rows | SQLAlchemy ORM |

---

## Conclusion

This document traced the complete data flow through VulnBot, showing how:

1. **User input** transforms into structured session data
2. **LLM prompts** are constructed with context and templates
3. **LLM responses** are parsed into executable components
4. **Execution results** feed back into adaptive planning
5. **Database persistence** enables session resumption
6. **RAG enhancement** provides domain knowledge
7. **Role transitions** chain phases together

Every piece of data flows through a clear pipeline of transformations, with LLM interactions at key decision points and database persistence ensuring state continuity.

---

*Document generated: 2026-07-01*
*Comprehensive data flow analysis of VulnBot penetration testing framework*
