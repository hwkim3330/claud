#!/usr/bin/env python3
"""
AGI 제어 CLI
목표 추가, 상태 확인, 메모리 관리
"""
import sys
import json
from pathlib import Path

AGI_DIR = Path("/home/kim/dooray-claude-bot/agi")
MEMORY_FILE = AGI_DIR / "memory.json"

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_goal(goal_text, priority=5):
    """목표 추가"""
    from datetime import datetime
    memory = load_memory()

    if "goals" not in memory:
        memory["goals"] = []

    memory["goals"].append({
        "id": len(memory["goals"]) + 1,
        "content": goal_text,
        "priority": priority,
        "created": datetime.now().isoformat(),
        "status": "pending"
    })

    save_memory(memory)
    print(f"✅ 목표 추가됨: {goal_text} (우선순위: {priority})")

def show_status():
    """상태 표시"""
    memory = load_memory()

    print("\n" + "="*50)
    print("🤖 AGI 상태")
    print("="*50)

    # 목표
    goals = memory.get("goals", [])
    pending = [g for g in goals if g.get("status") == "pending"]
    print(f"\n📋 대기 중인 목표: {len(pending)}개")
    for g in pending:
        print(f"  [{g['id']}] (P{g['priority']}) {g['content']}")

    # 최근 학습
    facts = memory.get("facts", [])[-5:]
    print(f"\n🧠 최근 학습 ({len(facts)}개):")
    for f in facts:
        print(f"  - {f['content'][:60]}")

    # 통계
    completed = memory.get("completed", [])
    print(f"\n📊 완료: {len(completed)}개")
    print("="*50)

def clear_completed():
    """완료된 목표 정리"""
    memory = load_memory()
    memory["goals"] = [g for g in memory.get("goals", [])
                       if g.get("status") != "completed"]
    save_memory(memory)
    print("✅ 완료된 목표 정리됨")

def main():
    if len(sys.argv) < 2:
        print("""
AGI CLI 사용법:
  agi status              - 상태 확인
  agi goal "목표" [우선순위] - 목표 추가 (우선순위 1-10, 기본 5)
  agi clear               - 완료된 목표 정리
  agi log                 - 로그 보기

예시:
  agi goal "매일 아침 8시에 시장 동향 분석" 8
  agi goal "날씨 정보 수집" 3
        """)
        return

    cmd = sys.argv[1]

    if cmd == "status":
        show_status()
    elif cmd == "goal" and len(sys.argv) >= 3:
        priority = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        add_goal(sys.argv[2], priority)
    elif cmd == "clear":
        clear_completed()
    elif cmd == "log":
        import subprocess
        subprocess.run(["tail", "-50", str(AGI_DIR / "agi.log")])
    else:
        print(f"알 수 없는 명령: {cmd}")

if __name__ == "__main__":
    main()
