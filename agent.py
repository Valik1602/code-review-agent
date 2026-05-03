import anthropic
import httpx
import json
from datetime import datetime

# Конфіг
MCP_BASE_URL = "http://localhost:8001"
GITHUB_REPO = "https://github.com/Valik1602/jira-mcp"
JIRA_PROJECT = "SCRUM"  # замени на свій ключ проекту

client = anthropic.Anthropic()

# ============================================================
# УТИЛІТИ: сесія, scratchpad, manifest
# ============================================================

def create_session():
    response = httpx.post(f"{MCP_BASE_URL}/session")
    data = response.json()
    return data["session_id"]

def write_scratchpad(content: str):
    """Записуємо знахідки в scratchpad.md"""
    with open("scratchpad.md", "a", encoding="utf-8") as f:
        f.write(content + "\n")
    print(f"📝 Scratchpad оновлено")

def read_scratchpad() -> str:
    """Читаємо scratchpad"""
    try:
        with open("scratchpad.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Scratchpad порожній"

def save_manifest(phase: int, explored: list, findings: dict, next_steps: list):
    """Зберігаємо стан агента для crash recovery"""
    manifest = {
        "session_id": f"review-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "phase": phase,
        "explored_files": explored,
        "key_findings": findings,
        "next_steps": next_steps,
        "timestamp": datetime.now().isoformat()
    }
    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"💾 Manifest збережено (фаза {phase})")

def load_manifest() -> dict:
    """Завантажуємо manifest для відновлення після збою"""
    try:
        with open("manifest.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None

# ============================================================
# СУБАГЕНТИ
# ============================================================

def run_subagent(task: str, context: str = "") -> str:
    """Запускаємо субагента з чистим контекстом"""
    print(f"\n🤖 Субагент: {task[:50]}...")
    
    messages = []
    if context:
        messages.append({
            "role": "user", 
            "content": f"Context from previous phase:\n{context}\n\nYour task: {task}"
        })
    else:
        messages.append({"role": "user", "content": task})
    
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=messages
    )
    
    result = response.content[0].text
    print(f"✅ Субагент завершив роботу")
    return result


def create_jira_ticket(session_id: str, summary: str, description: str, issue_type: str = "Task", priority: str = "Medium"):
    """Создаём реальный тикет в Jira через MCP"""
    mcp_url = f"{MCP_BASE_URL}/mcp/{session_id}"
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "jira_create_issue",
            "arguments": {
                "project_key": JIRA_PROJECT,
                "summary": summary,
                "description": description,
                "issue_type": issue_type
            }
        }
    }
    
    response = httpx.post(mcp_url, json=payload, timeout=30)
    result = response.json()
    
    if "result" in result:
        print(f"✅ Тикет создан: {summary[:50]}")
        return result["result"]
    else:
        print(f"❌ Ошибка: {result.get('error', 'Unknown error')}")
        return None

# ============================================================
# ГОЛОВНИЙ КООРДИНАТОР
# ============================================================

def run_coordinator():
    print("\n🚀 Code Review Agent запущено!")
    session_id = create_session()
    print(f"✅ MCP сесія: {session_id}")
    print(f"📁 Репо: {GITHUB_REPO}")
    print("=" * 50)
    
    # Ініціалізуємо scratchpad
    write_scratchpad(f"# Code Review — {GITHUB_REPO}\n## Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    # --- ФАЗА 1: Структура репо ---
    print("\n📌 ФАЗА 1: Аналіз структури")
    
    phase1_result = run_subagent(
        task=f"""Analyze this GitHub repository structure: {GITHUB_REPO}
        
The repo contains these files:
- mcp_server.py (main MCP server, 642 lines)
- mcp_server_sse.py (SSE version)
- mcp_server_http.py (HTTP version)
- test_http_client.py, test_progress.py, test_roots.py, test_sampling.py, test_sse_client.py
- update_stories_status.py
- pyproject.toml

Provide a brief structured analysis:
1. Architecture overview
2. Main components
3. Potential concerns"""
    )
    
    write_scratchpad(f"\n## Фаза 1: Структура\n{phase1_result}")
    save_manifest(1, ["structure"], {"phase1": phase1_result[:200]}, ["phase2: code quality"])
    
    # --- ФАЗА 2: Якість коду (з summary injection) ---
    print("\n📌 ФАЗА 2: Якість коду")
    
    # Summary injection — передаємо знахідки фази 1
    phase1_summary = f"Phase 1 findings: {phase1_result[:300]}"
    
    phase2_result = run_subagent(
        task=f"""Review code quality for: {GITHUB_REPO}

Known facts about the code:
- jira_search_issues: async function with progress reporting
- jira_create_issue: sync function, no retry logic
- jira_analyze_issues_with_ai: uses MCP sampling
- jira_read_export_file: file reading with security checks

Find issues in these categories:
1. Missing error handling / retry logic
2. Test coverage gaps  
3. Security concerns
4. Code structure issues

Return as numbered list with severity: CRITICAL/HIGH/MEDIUM""",
        context=phase1_summary
    )
    
    write_scratchpad(f"\n## Фаза 2: Якість коду\n{phase2_result}")
    save_manifest(2, ["structure", "code_quality"], 
                 {"phase1": phase1_result[:200], "phase2": phase2_result[:200]}, 
                 ["phase3: create jira tickets"])
    
    # --- ФАЗА 3: Створення Jira тікетів ---
    # --- ФАЗА 3: Створення Jira тікетів ---
    print("\n📌 ФАЗА 3: Створення Jira тікетів")
    
    all_findings = read_scratchpad()
    
    phase3_result = run_subagent(
        task=f"""Based on code review findings, create a list of Jira tickets.

Return ONLY a JSON array, no other text. Format:
[
  {{
    "summary": "ticket title",
    "description": "detailed description",
    "type": "Bug or Task",
    "priority": "Critical, High, or Medium"
  }}
]

Create maximum 5 tickets for the most important issues.""",
        context=all_findings[-3000:]
    )
    
    # Парсимо JSON і створюємо тікети
    import re
    json_match = re.search(r'\[.*\]', phase3_result, re.DOTALL)
    
    if json_match:
        tickets = json.loads(json_match.group())
        print(f"\n🎯 Знайдено {len(tickets)} тікетів для створення")
        
        created = []
        for ticket in tickets:
            result = create_jira_ticket(
                session_id=session_id,
                summary=ticket["summary"],
                description=ticket["description"],
                issue_type=ticket.get("type", "Task"),
                priority=ticket.get("priority", "Medium")
            )
            if result:
                created.append(ticket["summary"])
        
        print(f"\n✅ Створено тікетів: {len(created)}")
        for t in created:
            print(f"   • {t}")
    else:
        print("❌ Не вдалось розпарсити тікети")
        print(phase3_result)
    
    write_scratchpad(f"\n## Фаза 3: Jira тікети\n{phase3_result}")
    save_manifest(3, ["structure", "code_quality", "tickets"], 
                 {"tickets": phase3_result[:200]}, 
                 ["done"])
    
    print("\n" + "=" * 50)
    print("✅ Code Review завершено!")
    print("📄 Результати в scratchpad.md")
    print("💾 Стан збережено в manifest.json")
    
    # Читаємо scratchpad для координатора
    all_findings = read_scratchpad()
    
    phase3_result = run_subagent(
        task=f"""Based on code review findings, create a list of Jira tickets.

Format each ticket as:
TICKET N:
- Summary: [title]
- Type: Bug/Task
- Priority: Critical/High/Medium
- Description: [details]

Create tickets for the most important issues found.""",
        context=all_findings[-3000:]
    )
    
    write_scratchpad(f"\n## Фаза 3: Jira тікети\n{phase3_result}")
    save_manifest(3, ["structure", "code_quality", "tickets"], 
                 {"tickets": phase3_result[:200]}, 
                 ["done"])
    
    print("\n" + "=" * 50)
    print("✅ Code Review завершено!")
    print("📄 Результати в scratchpad.md")
    print("💾 Стан збережено в manifest.json")
    
    return phase3_result

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    # Перевіряємо чи є незавершена сесія
    manifest = load_manifest()
    if manifest and manifest.get("next_steps") != ["done"]:
        print(f"⚠️  Знайдено незавершену сесію (фаза {manifest['phase']})")
        print(f"   Next steps: {manifest['next_steps']}")
        print("   Починаємо з початку (або додай логіку відновлення)")
    
    result = run_coordinator()
    print("\n📋 ПЛАН JIRA ТІКЕТІВ:")
    print(result)