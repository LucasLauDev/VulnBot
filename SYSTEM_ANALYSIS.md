# VulnBot System Analysis & Workflow Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Workflow](#workflow)
5. [Database Schema](#database-schema)
6. [Configuration](#configuration)
7. [Usage Commands](#usage-commands)
8. [Detailed Component Analysis](#detailed-component-analysis)

---

## System Overview

**VulnBot** is an autonomous penetration testing framework that leverages Large Language Models (LLMs) to replicate the workflow of human penetration testing teams. It uses a multi-agent collaborative system where specialized agents (roles) work sequentially to perform comprehensive security assessments.

### Key Features

- **Multi-Agent System**: Three specialized roles (Collector, Scanner, Exploiter)
- **LLM-Driven**: Uses OpenAI or Ollama models for intelligent decision-making
- **RAG-Enabled**: Optional Retrieval-Augmented Generation for knowledge-based testing
- **Session Management**: Save and resume penetration testing sessions
- **Automated Execution**: Executes commands on a remote Kali Linux machine via SSH
- **Plan-React Cycle**: Creates plans, executes tasks, and adapts based on results

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         VulnBot System                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────┐      ┌───────────────┐      ┌─────────────┐ │
│  │   CLI Entry   │──────│    Roles      │──────│  Database   │ │
│  │   (cli.py)    │      │  Management   │      │   (MySQL)   │ │
│  └───────────────┘      └───────────────┘      └─────────────┘ │
│         │                       │                      │         │
│         │                       │                      │         │
│  ┌─────▼─────────────┐  ┌─────▼────────┐      ┌─────▼──────┐ │
│  │   Session Mgmt    │  │   Planner    │      │    RAG     │ │
│  │ (pentest.py)      │  │ (planner.py) │      │  (Optional)│ │
│  └───────────────────┘  └──────────────┘      └────────────┘ │
│         │                       │                      │         │
│         │              ┌────────▼────────┐            │         │
│         │              │   LLM Chat      │◄───────────┘         │
│         │              │  (chat.py)      │                      │
│         │              └────────┬────────┘                      │
│         │                       │                                │
│  ┌──────▼───────────────────────▼────────────────────────────┐ │
│  │              Execution Engine                              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │ │
│  │  │  WriteCode   │  │ ExecuteTask  │  │ ShellManager   │  │ │
│  │  │ (write_code) │─►│ (execute_task)│─►│(remote shell)  │  │ │
│  │  └──────────────┘  └──────────────┘  └────────────────┘  │ │
│  └────────────────────────────────────────┬──────────────────┘ │
│                                            │                    │
│                                    ┌───────▼────────┐           │
│                                    │  Kali Linux    │           │
│                                    │  (SSH Target)  │           │
│                                    └────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Entry Points

- **`cli.py`**: Main CLI with commands (init, start, vulnbot)
- **`pentest.py`**: Penetration testing orchestrator
- **`startup.py`**: RAG server manager (FastAPI + Streamlit)

### 2. Roles System

**Three Sequential Phases:**

| Phase | Role | Goal | Tools |
|-------|------|------|-------|
| 1 | Collector | Reconnaissance | Nmap, Curl, Whois, Dnsenum, etc. |
| 2 | Scanner | Vulnerability Scanning | Nikto, Dirb, Sqlmap, WPScan, etc. |
| 3 | Exploiter | Exploitation | Hydra, Metasploit, Netcat, Mimikatz |

### 3. Planning & Execution

- **Planner**: Orchestrates task generation and updates
- **WritePlan**: Generates/updates plans via LLM
- **WriteCode**: Converts tasks to shell commands
- **ExecuteTask**: Executes commands on Kali Linux

### 4. Remote Execution

- **ShellManager**: SSH connection singleton
- **RemoteShell**: Enhanced command execution with prompt detection

### 5. LLM Integration

- **OpenAIChat / OllamaChat**: Multi-provider support
- **_chat()**: Unified interface with RAG integration

### 6. Database Layer

- **Models**: Session, Plan, Task, Conversation, Message
- **Repositories**: CRUD operations for all models

### 7. RAG System (Optional)

- Embedding, Vector Store (Milvus), Retrieval, Reranking

---

## Workflow

### High-Level Flow

```
1. Initialize Project
   └─> python cli.py init

2. (Optional) Start RAG
   └─> python cli.py start -a

3. Run Penetration Test
   └─> python cli.py vulnbot -m 5
       │
       ├─> Load/Create Session
       │
       └─> For Each Role (Collector → Scanner → Exploiter):
           │
           ├─> PLAN: Generate task list via LLM
           │
           └─> REACT Loop (max 5 iterations):
               │
               ├─> Get task details
               ├─> Generate commands
               ├─> Execute on Kali
               ├─> Check success
               └─> Update plan based on results
```

### Plan-React Cycle Detail

```
┌─────────────────────────────────────────────┐
│ PLANNING PHASE                              │
├─────────────────────────────────────────────┤
│ Input: Goal, Tools, Context, Target         │
│ LLM Output: JSON Task List                  │
│   [{id, instruction, action, dependencies}] │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│ REACT PHASE (Per Task)                      │
├─────────────────────────────────────────────┤
│ 1. Task Details (LLM)                       │
│    → Specific execution steps               │
│                                             │
│ 2. Code Generation (LLM)                    │
│    → <execute>command</execute>             │
│                                             │
│ 3. Execution (SSH to Kali)                  │
│    → Run commands, collect output           │
│                                             │
│ 4. Success Check (LLM)                      │
│    → Evaluate: yes/no                       │
│                                             │
│ 5. Plan Update (LLM)                        │
│    → Adapt plan, add/modify tasks           │
└─────────────────────────────────────────────┘
                    │
                    ▼
              Next Task or Complete
```

---

## Database Schema

### Entity Relationships

```
Session (1) ──┬─> (N) Plan
              │
Plan (1) ─────┴─> (N) Task
              
Task (N) ─────────> (M) Task (dependencies)

Conversation (1) ─> (N) Message
```

### Tables

**sessions**
- `id`, `name`, `init_description`
- `current_role_name` (COLLECTOR/SCANNER/EXPLOITER)
- `current_planner_id`, `history_planner_ids`

**plans**
- `id`, `goal`, `current_task_sequence`
- `plan_chat_id`, `react_chat_id`

**tasks**
- `id`, `plan_id`, `sequence`, `action`
- `instruction`, `code` (JSON), `result`
- `is_success`, `is_finished`, `dependencies` (JSON)

**conversations**
- `id`, `name`, `chat_type`

**messages**
- `id`, `conversation_id`, `query`, `response`

---

## Configuration

### File Overview

| File | Purpose | Key Settings |
|------|---------|--------------|
| `basic_config.yaml` | System settings | mode, kali SSH, enable_rag, servers |
| `db_config.yaml` | Database | MySQL connection details |
| `model_config.yaml` | LLM | Provider, model, API key, embeddings |
| `kb_config.yaml` | RAG | Milvus, search params, chunking |

### Key Configuration Options

#### Execution Modes (`basic_config.yaml`)

```yaml
mode: auto    # Options: auto, semi, manual
```

- **auto**: Fully automated execution
- **semi**: Auto for Shell actions, manual for others
- **manual**: User provides all execution results

#### RAG Toggle

```yaml
enable_rag: false    # Set to true to use knowledge base
```

When enabled, system queries Milvus vector store for relevant penetration testing knowledge.

#### Kali Connection

```yaml
kali:
  hostname: 10.10.0.5
  port: 22
  username: root
  password: root
```

SSH credentials for the Kali Linux machine where commands execute.

---

## Usage Commands

### Installation & Setup

```bash
# 1. Clone repository
git clone https://github.com/KHenryAegis/VulnBot
cd VulnBot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure system (edit YAML files)
# - basic_config.yaml: Set Kali SSH details, mode
# - db_config.yaml: MySQL connection
# - model_config.yaml: LLM provider and API key
# - kb_config.yaml: (Optional) Milvus for RAG

# 4. Initialize project
python cli.py init
```

### Running VulnBot

#### Basic Usage

```bash
# Run penetration test with default settings (5 interactions per role)
python cli.py vulnbot

# Run with custom max interactions
python cli.py vulnbot -m 10

# Run with custom max interactions (verbose)
python cli.py vulnbot --max_interactions 10
```

#### Session Management

When you start `vulnbot`, you'll be prompted:

```
Do you want to continue from a previous session? [y/N]:
```

- **New Session**: Enter `N`, then describe your target
- **Resume Session**: Enter `Y`, select from saved sessions

At the end, you'll be prompted to save:

```
Please enter the name of the current session. (Default with current timestamp)
> my_pentest_session
```

#### RAG Module (Optional)

```bash
# Start both API server and WebUI
python cli.py start -a

# Start only API server (port 7861)
python cli.py start --api

# Start only WebUI (port 8501)
python cli.py start -w
```

**Access Points:**
- API: `http://localhost:7861`
- WebUI: `http://localhost:8501`

### Example Workflow

```bash
# Step 1: Initialize
python cli.py init

# Step 2: (Optional) Start RAG if enabled in config
python cli.py start -a

# Step 3: Run penetration test
python cli.py vulnbot -m 5

# During execution:
# - System will prompt if you want to load a previous session
# - If new: Enter target description (e.g., "Penetration test on 192.168.1.100")
# - Collector phase runs (reconnaissance)
# - Scanner phase runs (vulnerability detection)
# - Exploiter phase runs (exploitation)
# - At end, save session with a name

# Step 4: Resume later if needed
python cli.py vulnbot
# Select 'y' to continue from previous session
# Choose the session by index
```

### Database Operations

```bash
# Create/recreate database tables
python cli.py init

# Access MySQL directly (if needed)
mysql -h localhost -u vulnbot -p
use vulnbot_db;

# View sessions
SELECT * FROM sessions;

# View plans for a session
SELECT * FROM plans WHERE id IN (SELECT current_planner_id FROM sessions WHERE name='my_session');

# View tasks for a plan
SELECT * FROM tasks WHERE plan_id='<plan_id>' ORDER BY sequence;
```

### Configuration Updates

```bash
# After modifying config files, reinitialize if needed
python cli.py init

# Check configuration
python -c "from config.config import Configs; print(Configs.basic_config.kali)"
```

### Logs

```bash
# View logs (generated during execution)
ls logs/

# View specific log file
tail -f logs/run_api_server_<timestamp>.log
tail -f logs/run_webui_<timestamp>.log
```

---

## Detailed Component Analysis

### 1. Session Management Flow

```python
# pentest.py - Session lifecycle

def preload_session(console):
    """Prompt user to continue from previous or start new"""
    # Query database for existing sessions
    # User selects by index
    
def initialize_session(previous_session):
    """Create or restore session"""
    if previous_session:
        return previous_session
    else:
        # User describes target
        return new Session()
        
def save_session(console, session):
    """Save session to database with user-provided name"""
```

**Flow:**
1. User starts `vulnbot`
2. System checks for previous sessions
3. User chooses new or existing
4. Session object tracks:
   - Current role (COLLECTOR/SCANNER/EXPLOITER)
   - Current plan ID
   - History of previous plan IDs
5. At end, save with name

### 2. Role Execution Pattern

```python
# roles/role.py - Base role behavior

class Role:
    def run(self, session):
        # 1. Generate plan
        next_task = self._plan(session)
        
        # 2. Execute tasks in loop
        while self.chat_counter < self.max_interactions:
            next_task = self._react(next_task)
            if next_task is None:
                break
                
        # 3. Transition to next role
        self.put_message(session)
```

**Key Points:**
- Each role inherits from base `Role` class
- `_plan()`: Creates initial task list
- `_react()`: Execute → Update cycle
- `put_message()`: Chain to next role
- `max_interactions`: Safety limit (default 5)

### 3. Plan Generation

```python
# actions/write_plan.py

def run(self, init_description):
    """Generate initial plan"""
    # Send goal + tools + context to LLM
    rsp = _chat(prompt.write_plan, kb_name=kb)
    
    # Extract JSON from response
    # Format: [{"id": "1", "instruction": "...", "action": "Shell", "dependent_task_ids": []}]
    return extract_json(rsp)
```

**LLM Prompt Structure:**
```
## Task:
Based on context, write a plan for achieving the goal.

## Available Action Types:
Shell, Web

## Output:
<json>
[
  {"id": "1", "instruction": "...", "action": "Shell", "dependent_task_ids": []},
  ...
]
</json>
```

### 4. Task Execution

```python
# actions/execute_task.py

class ExecuteTask:
    def run(self):
        # 1. Parse commands from <execute> tags
        commands = self.parse_response()
        
        # 2. Get SSH shell
        shell = ShellManager.get_instance().get_shell()
        
        # 3. Execute each command
        for cmd in commands:
            output = shell.execute_cmd(cmd)
            result += f"Action: {cmd}\nObservation: {output}\n"
            
        return ExecuteResult(code=commands, response=result)
```

**Special Handling:**
- **Password prompts**: Automatically detected and handled
- **Interactive prompts**: Yes/no questions answered
- **SMB sessions**: Exit and retry on errors
- **Output cleaning**: Special parsers for dirb, msfconsole

### 5. Plan Update Mechanism

```python
# actions/planner.py

def update_plan(self, result):
    # 1. Check if task succeeded
    check = _chat(prompt.check_success.format(result=result))
    
    # 2. Mark task status
    task.is_finished = True
    task.is_success = ("yes" in check.lower())
    
    # 3. Generate updated plan
    updated = WritePlan.update(
        task_result=task,
        success_tasks=plan.finished_success_tasks,
        fail_tasks=plan.finished_fail_tasks
    )
    
    # 4. Merge tasks
    merge_tasks(updated, current_plan)
    
    # 5. Return next task
    return self.next_task_details()
```

**Merge Logic:**
- Keep all successful tasks
- Remove failed tasks (unless LLM re-adds them)
- Add new tasks from updated plan
- Preserve task dependencies

### 6. LLM Communication

```python
# server/chat/chat.py

def _chat(query, kb_name=None, conversation_id=None):
    # 1. RAG: Query knowledge base if enabled
    if enable_rag and kb_name:
        docs = search_docs(kb_name, query)
        docs = reranker.compress(docs)
        query += f"\n\nContext: {docs}"
    
    # 2. Get conversation history
    history = get_messages(conversation_id)[-5:]  # Last 5 msgs
    
    # 3. Build message array
    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        *history,
        {"role": "user", "content": query}
    ]
    
    # 4. Call LLM
    if provider == "openai":
        response = openai_client.chat(messages)
    elif provider == "ollama":
        response = ollama_client.chat(messages)
    
    # 5. Save to database
    save_message(conversation_id, query, response)
    
    return response, conversation_id
```

**Conversation Management:**
- Each plan has 2 conversations: planning and reasoning
- History limited to last 5 messages (configurable)
- RAG context injected when available
- Retry logic with exponential backoff

### 7. SSH Connection Management

```python
# actions/shell_manager.py

class ShellManager:
    """Singleton for SSH connection"""
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_shell(self):
        if self._shell is None:
            self._connect()
        return self._shell
    
    def _connect(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, username, password, port)
        self._ssh_client = client
        self._shell = RemoteShell(client.invoke_shell())
```

**Features:**
- Singleton pattern: One connection per session
- Automatic reconnection on failure
- Cleanup on exit
- Channel-based interactive shell

### 8. Prompt Engineering

The system uses carefully crafted prompts for different stages:

**Planning Prompt** (`write_plan`):
- Specifies JSON output format
- Provides action types (Shell, Web)
- Requests 1-5 tasks
- Emphasizes including target IP/port
- Notes shell is shared across phases

**Code Generation** (`write_code`):
- Roleplay as "autonomous pentesting assistant"
- Wraps commands in `<execute>` tags
- Optimizes for speed (e.g., nmap -T5)
- Validates against Kali Linux 2026 tools
- Includes example cases

**Success Check** (`check_success`):
- Simple yes/no evaluation
- Checks for empty results or errors
- Used to mark task status

**Plan Update** (`update_plan`):
- Maintains JSON structure
- Keeps successful tasks
- Adapts based on findings
- Considers shell state continuity

### 9. RAG Integration

```python
# server/chat/chat.py - RAG workflow

# 1. Generate query embedding
embedding = embedding_model.encode(query)

# 2. Search vector database
docs = milvus.search(
    collection=kb_name,
    embedding=embedding,
    top_k=3,
    score_threshold=0.5
)

# 3. Rerank results
reranker = LangchainReranker(top_n=1)
docs = reranker.compress_documents(docs, query)

# 4. Extract content
context = "\n".join([doc["page_content"] for doc in docs])

# 5. Inject into prompt
query = f"{query}\n\nRelevant pentesting knowledge: {context}"
```

**When Used:**
- Planning phase: Query with target description
- Task details: Query with task instruction
- Plan updates: Query with task instruction

**Benefits:**
- Provides domain-specific knowledge
- Improves accuracy of generated plans
- Helps with tool selection and parameters

### 10. Error Handling

**Connection Errors:**
```python
try:
    shell = ShellManager.get_instance().get_shell()
except Exception as e:
    return f"SSH failed: {e}. Check Kali connectivity."
```

**LLM Errors:**
```python
@retry(stop=stop_after_attempt(3))
def chat(self, history):
    try:
        response = self.client.chat.completions.create(...)
    except httpx.ReadTimeout:
        time.sleep(2)
        raise  # Triggers retry
```

**Parsing Errors:**
```python
try:
    plan = json.loads(response)
    tasks = parse_tasks(plan)
except (json.JSONDecodeError, ValueError) as e:
    logger.error(f"Plan parse failed: {e}")
    return None
```

**Session Recovery:**
- Sessions saved to database after each role
- Can resume from any role
- History preserved in `history_planner_ids`

---

## Command Reference Cheat Sheet

```bash
# === SETUP ===
pip install -r requirements.txt          # Install dependencies
python cli.py init                       # Initialize project

# === CONFIGURATION ===
# Edit these files before running:
# - basic_config.yaml    # Kali SSH, mode, enable_rag
# - db_config.yaml       # MySQL connection
# - model_config.yaml    # LLM provider and API key
# - kb_config.yaml       # RAG settings (if enable_rag=true)

# === RUNNING ===
python cli.py vulnbot                    # Run with defaults (5 interactions)
python cli.py vulnbot -m 10              # Run with 10 interactions per role
python cli.py start -a                   # Start RAG module (API + WebUI)
python cli.py start --api                # Start only API server
python cli.py start --webui              # Start only WebUI

# === DURING EXECUTION ===
# You'll be prompted:
# 1. Continue from previous session? (y/n)
# 2. If new: Describe target
# 3. At end: Enter session name to save

# === TROUBLESHOOTING ===
python cli.py init                       # Re-initialize after config changes
tail -f logs/*.log                       # View logs
mysql -u vulnbot -p vulnbot_db           # Access database directly
```

---

## Summary

VulnBot is a sophisticated multi-agent penetration testing framework that:

1. **Orchestrates** three specialized roles (Collector, Scanner, Exploiter)
2. **Plans** tasks using LLM-generated strategies
3. **Executes** commands on a remote Kali Linux machine
4. **Adapts** plans based on execution results
5. **Persists** sessions for resumable testing
6. **Optionally leverages** RAG for domain knowledge

**Key Design Patterns:**
- **Plan-React Cycle**: Generate plan → Execute → Update → Repeat
- **Multi-Agent Collaboration**: Sequential role execution with context passing
- **LLM-Driven Decision Making**: Planning, code generation, success evaluation
- **Session Persistence**: Save/resume capabilities via database
- **Adaptive Planning**: Dynamic task generation based on findings

**Technology Stack:**
- Python 3.11
- LLMs: OpenAI GPT / Ollama
- Database: MySQL (via SQLAlchemy)
- SSH: Paramiko
- RAG: Langchain + Milvus
- CLI: Click
- Web: FastAPI + Streamlit

This system demonstrates advanced AI agent capabilities including planning, execution, reflection, and collaboration in a practical cybersecurity context.

---

*Document generated: 2026-07-01*
*Based on VulnBot source code analysis*
