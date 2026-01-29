#!/usr/bin/env python3
"""
Claude AGI Core v2.0 - 자율 에이전트 시스템
하이쿠로 계획 → 실행 → 학습 반복
"""
import json
import subprocess
import time
import os
from datetime import datetime
from pathlib import Path

# 설정
AGI_DIR = Path("/home/kim/dooray-claude-bot/agi")
MEMORY_FILE = AGI_DIR / "memory.json"
LOG_FILE = AGI_DIR / "agi.log"
CYCLE_INTERVAL = 60  # 1분

# 도구 임포트
import sys
sys.path.insert(0, str(AGI_DIR))
from tools import (
    get_stock_price, get_watchlist_prices, get_exchange_rate,
    get_kospi, get_weather, get_system_status, daily_report
)


class AGIMemory:
    """영구 메모리 시스템"""

    def __init__(self):
        self.memory_file = MEMORY_FILE
        self.load()

    def load(self):
        if self.memory_file.exists():
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            self.data = {
                "created": datetime.now().isoformat(),
                "facts": [],
                "goals": [],
                "completed": [],
                "insights": [],
                "user_preferences": {}
            }
            self.save()

    def save(self):
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_fact(self, fact):
        self.data["facts"].append({
            "time": datetime.now().isoformat(),
            "content": fact
        })
        self.data["facts"] = self.data["facts"][-100:]
        self.save()

    def add_insight(self, insight):
        """인사이트 추가"""
        self.data["insights"].append({
            "time": datetime.now().isoformat(),
            "content": insight
        })
        self.data["insights"] = self.data["insights"][-50:]
        self.save()

    def get_context(self):
        pending_goals = [g for g in self.data["goals"] if g["status"] == "pending"]
        recent_facts = self.data["facts"][-10:]
        recent_insights = self.data["insights"][-5:]

        return {
            "pending_goals": pending_goals,
            "recent_facts": recent_facts,
            "recent_insights": recent_insights,
            "total_completed": len(self.data["completed"])
        }


class AGIExecutor:
    """작업 실행기"""

    # 사용 가능한 도구들
    TOOLS = {
        "stock_price": "get_stock_price(code) - 종목 현재가",
        "watchlist": "get_watchlist_prices() - 관심종목 일괄",
        "kospi": "get_kospi() - 코스피 지수",
        "exchange": "get_exchange_rate() - 원/달러 환율",
        "weather": "get_weather(city) - 날씨",
        "system": "get_system_status() - 시스템 상태",
        "daily_report": "daily_report() - 일일 종합 리포트",
        "shell": "run_command(cmd) - 쉘 명령 실행"
    }

    @staticmethod
    def run_command(cmd, timeout=30):
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:500]
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def ask_claude(prompt, model="haiku"):
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--model", model],
                capture_output=True, text=True, timeout=90
            )
            return result.stdout.strip()
        except Exception as e:
            return f"Error: {e}"

    def execute_tool(self, tool_name, args=None):
        """도구 실행"""
        try:
            if tool_name == "stock_price" and args:
                return {"success": True, "data": get_stock_price(args)}
            elif tool_name == "watchlist":
                return {"success": True, "data": get_watchlist_prices()}
            elif tool_name == "kospi":
                return {"success": True, "data": get_kospi()}
            elif tool_name == "exchange":
                return {"success": True, "data": get_exchange_rate()}
            elif tool_name == "weather":
                city = args or "Seoul"
                return {"success": True, "data": get_weather(city)}
            elif tool_name == "system":
                return {"success": True, "data": get_system_status()}
            elif tool_name == "daily_report":
                return {"success": True, "data": daily_report()}
            elif tool_name == "shell" and args:
                return self.run_command(args)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class AGICore:
    """AGI 코어 엔진 v2"""

    def __init__(self):
        AGI_DIR.mkdir(exist_ok=True)
        self.memory = AGIMemory()
        self.executor = AGIExecutor()
        self.cycle_count = 0
        self.log("AGI Core v2 시작")

    def log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}"
        print(log_line)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_line + "\n")

    def notify(self, message):
        """텔레그램/두레이 알림"""
        try:
            subprocess.run([
                "python3", "/home/kim/dooray-claude-bot/claude_notify.py",
                f"[AGI] {message}"
            ], timeout=10)
        except:
            pass

    def think(self):
        """1단계: 상황 분석 및 계획"""
        context = self.memory.get_context()
        hour = datetime.now().hour

        prompt = f"""당신은 자율 AI 에이전트입니다. 사용자를 위해 유용한 정보를 수집하고 분석합니다.

현재 상황:
- 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')} ({"장중" if 9 <= hour < 16 else "장외"})
- 대기 목표: {len(context['pending_goals'])}개
- 사이클: #{self.cycle_count}

사용 가능한 도구:
{json.dumps(self.executor.TOOLS, ensure_ascii=False, indent=2)}

대기 중인 목표:
{json.dumps(context['pending_goals'][:3], ensure_ascii=False, indent=2)}

최근 수집 정보:
{json.dumps([f['content'][:80] for f in context['recent_facts'][-3:]], ensure_ascii=False)}

규칙:
1. 장중(9-16시)에는 주식 정보 우선
2. 아침(8-9시)에는 daily_report 실행
3. 시스템 상태는 10사이클마다
4. 중요한 변화 발견시 알림(notify=true)

다음 행동을 JSON으로 응답:
{{"tool": "도구명", "args": "인자(있으면)", "reason": "이유", "notify": false}}
"""

        response = self.executor.ask_claude(prompt, "haiku")

        try:
            if "{" in response:
                json_str = response[response.find("{"):response.rfind("}")+1]
                return json.loads(json_str)
        except:
            pass

        # 기본: 시스템 체크
        return {"tool": "system", "args": None, "reason": "기본 체크", "notify": False}

    def act(self, plan):
        """2단계: 계획 실행"""
        tool = plan.get("tool", "system")
        args = plan.get("args")

        self.log(f"실행: {tool} ({plan.get('reason', '')})")

        result = self.executor.execute_tool(tool, args)
        return result

    def learn(self, plan, result):
        """3단계: 결과 학습 및 분석"""
        if not result.get("success"):
            self.log(f"실패: {result.get('error', 'unknown')}")
            return

        data = result.get("data") or result.get("stdout", "")

        # 데이터를 문자열로 변환
        if isinstance(data, dict):
            summary = json.dumps(data, ensure_ascii=False)[:300]
        else:
            summary = str(data)[:300]

        fact = f"{plan.get('tool', 'unknown')}: {summary}"
        self.memory.add_fact(fact)
        self.log(f"학습: {fact[:80]}...")

        # 알림이 필요한 경우
        if plan.get("notify"):
            self.notify(summary[:200])

    def cycle(self):
        """하나의 AGI 사이클"""
        self.cycle_count += 1

        try:
            plan = self.think()
            result = self.act(plan)
            self.learn(plan, result)
        except Exception as e:
            self.log(f"사이클 에러: {e}")

    def run_forever(self):
        """무한 루프"""
        self.log("AGI 무한 루프 시작")

        # 시작시 일일 리포트
        try:
            report = daily_report()
            self.memory.add_fact(f"시작 리포트: {report[:500]}")
            self.log("시작 리포트 저장")
        except:
            pass

        while True:
            self.cycle()
            time.sleep(CYCLE_INTERVAL)


def main():
    print("""
╔═══════════════════════════════════════════╗
║       Claude AGI Core v2.0                ║
║   자율 에이전트 - 하이쿠 기반             ║
╚═══════════════════════════════════════════╝
    """)

    agi = AGICore()
    agi.run_forever()


if __name__ == "__main__":
    main()
