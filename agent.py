import anthropic
import httpx
import json
import re
from datetime import datetime

# Конфіг
MCP_BASE_URL = "http://localhost:8001"
GITHUB_REPO = "https://github.com/Valik1602/jira-mcp"
JIRA_PROJECT = "SCRUM"

client = anthropic.Anthropic()

# ============================================================
# УТИЛІТИ: сесія, scratchpad, manifest
# ============================================================

def create_session():
    response = httpx.post(f"{MCP_BASE_URL}/session")
    data = response.json()
    return data["session_id"]

def write_scratchpad(content: str):
    with open("scratchpad.md", "a", encoding="utf-8") as f:
        f.write(content + "\n")
    print(f"📝 Scratchpad оновлено")

def read_scratchpad() -> str:
    try:
        with open("scratchpad.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Scratchpad порожній"

def save_manifest(phase: int, explored: list, findings: dict, next_steps: list):
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
    try:
        with open("manifest.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None

# ============================================================
# СУБАГЕНТИ
# ============================================================

def run_subagent_with_provenance(task: str, source_url: str, document_name: str, context: str = "") -> list:
    """Субагент який повертає структуровані знахідки з провенансом"""
    print(f"\n🤖 Субагент (з провенансом): {task[:50]}...")

    prompt = f"""You are a code reviewer. Analyze the provided information and return findings.

IMPORTANT: Return ONLY a JSON array. No other text. Format:
[
  {{
    "claim": "specific finding or issue",
    "sourceUrl": "{source_url}",
    "documentName": "{document_name}",
    "relevantExcerpt": "specific code or text that supports this finding",
    "publicationDate": "2026-05-03",
    "severity": "CRITICAL, HIGH, or MEDIUM"
  }}
]

Task: {task}"""

    messages = []
    if context:
        messages.append({
            "role": "user",
            "content": f"Context:\n{context}\n\n{prompt}"
        })
    else:
        messages.append({"role": "user", "content": prompt})

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=messages
    )

    result = response.content[0].text

    json_match = re.search(r'\[.*\]', result, re.DOTALL)
    if json_match:
        findings = json.loads(json_match.group())
        print(f"✅ Знайдено {len(findings)} знахідок з провенансом")
        return findings
    else:
        print("⚠️ Не вдалось розпарсити провенанс")
        return []


def create_jira_ticket(session_id: str, summary: str, description: str, issue_type: str = "Task"):
    """Створюємо реальний тікет в Jira через MCP"""
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
        print(f"✅ Тікет створено: {summary[:50]}")
        return result["result"]
    else:
        print(f"❌ Помилка: {result.get('error', 'Unknown error')}")
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

    write_scratchpad(f"# Code Review — {GITHUB_REPO}\n## Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # --- ФАЗА 1: Структура репо ---
    print("\n📌 ФАЗА 1: Аналіз структури")

    phase1_findings = run_subagent_with_provenance(
        task=f"""Analyze this GitHub repository: {GITHUB_REPO}

Files in repo:
- mcp_server.py (main MCP server, 642 lines)
- mcp_server_sse.py (SSE transport)
- mcp_server_http.py (HTTP transport)
- test_http_client.py, test_progress.py, test_roots.py, test_sampling.py, test_sse_client.py
- update_stories_status.py

Find architectural issues and concerns. Each finding must reference a specific file.""",
        source_url=GITHUB_REPO,
        document_name="jira-mcp repository"
    )

    scratchpad_phase1 = "\n## Фаза 1: Структура\n"
    for f in phase1_findings:
        scratchpad_phase1 += f"- [{f.get('severity','?')}] {f['claim']}\n"
        scratchpad_phase1 += f"  File: {f['documentName']} | Excerpt: {f.get('relevantExcerpt','N/A')[:80]}\n"

    write_scratchpad(scratchpad_phase1)
    save_manifest(1, ["structure"], {"phase1_count": len(phase1_findings)}, ["phase2: code quality"])

    # --- ФАЗА 2: Якість коду ---
    print("\n📌 ФАЗА 2: Якість коду")

    phase1_summary = "\n".join([f"- {f['claim']}" for f in phase1_findings])

    phase2_findings = run_subagent_with_provenance(
        task=f"""Review code quality for: {GITHUB_REPO}

Known functions:
- jira_create_issue: sync, no retry logic
- jira_search_issues: async with progress
- jira_analyze_issues_with_ai: uses MCP sampling
- jira_read_export_file: file reading with security checks

Find specific code quality issues with exact function names.""",
        source_url=f"{GITHUB_REPO}/blob/master/mcp_server.py",
        document_name="mcp_server.py",
        context=f"Phase 1 findings:\n{phase1_summary}"
    )

    scratchpad_phase2 = "\n## Фаза 2: Якість коду\n"
    for f in phase2_findings:
        scratchpad_phase2 += f"- [{f.get('severity','?')}] {f['claim']}\n"
        scratchpad_phase2 += f"  Excerpt: {f.get('relevantExcerpt','N/A')[:80]}\n"

    write_scratchpad(scratchpad_phase2)
    save_manifest(2, ["structure", "code_quality"],
                 {"phase1_count": len(phase1_findings), "phase2_count": len(phase2_findings)},
                 ["phase3: create jira tickets"])

    # --- ФАЗА 3: Створення Jira тікетів ---
    print("\n📌 ФАЗА 3: Створення Jira тікетів")

    all_findings = phase1_findings + phase2_findings
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    all_findings.sort(key=lambda x: severity_order.get(x.get("severity", "MEDIUM"), 2))

    print(f"\n🎯 Всього знахідок: {len(all_findings)}")

    created = []
    for finding in all_findings[:5]:
        description = f"""{finding['claim']}

Source: {finding['sourceUrl']}
File: {finding['documentName']}
Evidence: {finding.get('relevantExcerpt', 'N/A')}
Severity: {finding.get('severity', 'MEDIUM')}"""

        result = create_jira_ticket(
            session_id=session_id,
            summary=finding['claim'][:100],
            description=description,
            issue_type="Bug" if finding.get("severity") == "CRITICAL" else "Task"
        )
        if result:
            created.append(finding['claim'][:60])

    print(f"\n✅ Створено тікетів: {len(created)}")
    for t in created:
        print(f"   • {t}")

    write_scratchpad(f"\n## Фаза 3: Створено {len(created)} тікетів")
    save_manifest(3, ["structure", "code_quality", "tickets"],
                 {"created_tickets": len(created)},
                 ["done"])

    print("\n" + "=" * 50)
    print("✅ Code Review завершено!")
    print("📄 Результати в scratchpad.md")
    print("💾 Стан збережено в manifest.json")

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    manifest = load_manifest()
    if manifest and manifest.get("next_steps") != ["done"]:
        print(f"⚠️  Знайдено незавершену сесію (фаза {manifest['phase']})")
        print(f"   Next steps: {manifest['next_steps']}")

    run_coordinator()