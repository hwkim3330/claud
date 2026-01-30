#!/usr/bin/env python3
"""
Telegram ↔ Claude CLI 브릿지 (MoltBot 기능 포함)
"""

import subprocess
import os
import json
import re
import requests
import urllib.parse
import psutil
from datetime import datetime
from pathlib import Path

# 설정
TELEGRAM_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"
ALLOWED_USERS = ["8341524797"]
DOORAY_WEBHOOK = "https://keti.dooray.com/services/3711006199900720461/4145226571364668339/1QmQmcTCTMKf3FyF1OemZA"
SKILLS_DIR = Path("/home/kim/dooray-claude-bot/moltbot/skills")
MEMORY_FILE = Path("/home/kim/dooray-claude-bot/user_memory.json")

# 메모리 로드
def load_memory():
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except:
            pass
    return {"users": {}, "facts": []}

def save_memory(data):
    MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

MEMORY = load_memory()


# ═══════════════════════════════════════════════════════════════
# 도구 함수들
# ═══════════════════════════════════════════════════════════════

def ask_claude(prompt: str, system: str = "") -> str:
    """Claude CLI 호출"""
    try:
        cmd = ["claude", "-p", prompt]
        if system:
            cmd.extend(["--system-prompt", system])
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        return result.stdout.strip()[:4000] if result.returncode == 0 else f"오류: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "⏱️ 시간 초과"
    except Exception as e:
        return f"오류: {e}"


def ask_codex(prompt: str) -> str:
    """Codex CLI 호출"""
    try:
        result = subprocess.run(
            ["codex", "-q", prompt],
            capture_output=True, text=True, timeout=120
        )
        return result.stdout.strip()[:4000] if result.returncode == 0 else "Codex 오류"
    except Exception as e:
        return f"오류: {e}"


def get_stock_info(query: str) -> str:
    """주식 정보 조회"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        # 종목 검색
        code = query if query.isdigit() else None
        if not code:
            search_url = f"https://m.stock.naver.com/api/json/search/searchListJson.naver?keyword={urllib.parse.quote(query)}"
            resp = requests.get(search_url, timeout=10, headers=headers)
            data = resp.json()
            items = data.get("result", {}).get("d", [])
            if items:
                code = items[0].get("cd", "")

        if not code:
            return f"❌ 종목을 찾을 수 없음: {query}"

        # 주식 정보
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        resp = requests.get(url, timeout=10, headers=headers)
        data = resp.json()

        name = data.get("stockName", query)
        price = data.get("closePrice", "N/A")
        rate = float(data.get("fluctuationsRatio", "0"))
        change = data.get("compareToPreviousClosePrice", "0")

        emoji = "🔴" if rate > 0 else "🔵" if rate < 0 else "⚪"
        sign = "+" if rate > 0 else ""

        return f"""📊 **{name}** ({code})
{emoji} 현재가: **{price}원** ({sign}{rate}%)
전일대비: {change}원"""
    except Exception as e:
        return f"주식 조회 오류: {e}"


def get_watchlist() -> str:
    """관심종목 시세"""
    stocks = [
        ("SK하이닉스", "000660"),
        ("삼성전자", "005930"),
        ("한화에어로", "012450"),
        ("현대로템", "064350"),
        ("한미반도체", "042700"),
    ]

    results = ["📊 **관심종목 시세**\n"]
    headers = {"User-Agent": "Mozilla/5.0"}

    for name, code in stocks:
        try:
            url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            resp = requests.get(url, timeout=5, headers=headers)
            data = resp.json()
            price = data.get("closePrice", "N/A")
            rate = float(data.get("fluctuationsRatio", "0"))
            emoji = "🔴" if rate > 0 else "🔵" if rate < 0 else "⚪"
            sign = "+" if rate > 0 else ""
            results.append(f"{emoji} {name}: {price}원 ({sign}{rate}%)")
        except:
            results.append(f"⚪ {name}: 조회 실패")

    return "\n".join(results)


def get_weather(city: str = "Seoul") -> str:
    """날씨 조회"""
    try:
        result = subprocess.run(
            ["curl", "-s", f"wttr.in/{city}?format=3"],
            capture_output=True, text=True, timeout=10
        )
        return f"🌤️ {result.stdout.strip()}"
    except:
        return "날씨 조회 실패"


def generate_image(prompt: str) -> str:
    """이미지 생성 URL 반환"""
    # 한글이면 번역
    if any('\uac00' <= c <= '\ud7a3' for c in prompt):
        translated = ask_claude(f"Translate to English (only output translation): {prompt}")
        prompt = translated

    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"


def get_system_status() -> str:
    """시스템 상태"""
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    # 실행 중인 서비스
    services = []
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'telegram_claude_bridge' in cmdline:
                services.append(f"✅ Telegram Bot (PID: {proc.info['pid']})")
        except:
            pass

    return f"""🖥️ **시스템 상태**

**CPU:** {cpu}%
**메모리:** {mem.percent}% ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)
**디스크:** {disk.percent}%

**서비스:**
{chr(10).join(services) if services else '없음'}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""


def shell_execute(cmd: str) -> str:
    """쉘 명령 실행"""
    # 위험한 명령 차단
    dangerous = ["rm -rf /", "mkfs", "dd if=", ":(){"]
    for d in dangerous:
        if d in cmd.lower():
            return f"⛔ 위험한 명령 차단: {d}"

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd="/home/kim"
        )
        output = (result.stdout + result.stderr)[:2000]
        return f"```\n{output}\n```" if output.strip() else "(출력 없음)"
    except subprocess.TimeoutExpired:
        return "⏱️ 시간 초과 (30초)"
    except Exception as e:
        return f"오류: {e}"


def read_file(filepath: str) -> str:
    """파일 읽기"""
    try:
        path = Path(filepath).expanduser()
        if not path.exists():
            return f"❌ 파일 없음: {filepath}"
        if path.is_dir():
            files = list(path.iterdir())[:20]
            return "📁 디렉토리:\n" + "\n".join(f"  {'📁' if f.is_dir() else '📄'} {f.name}" for f in files)
        content = path.read_text()[:2000]
        return f"📄 {filepath}:\n```\n{content}\n```"
    except Exception as e:
        return f"오류: {e}"


def web_search(query: str) -> str:
    """웹 검색 (DuckDuckGo)"""
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        results = []
        if data.get("Abstract"):
            results.append(f"📝 {data['Abstract']}")
        if data.get("RelatedTopics"):
            for topic in data["RelatedTopics"][:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(f"• {topic['Text'][:150]}")

        return "\n".join(results) if results else "검색 결과 없음"
    except Exception as e:
        return f"검색 오류: {e}"


def list_skills() -> str:
    """스킬 목록"""
    if not SKILLS_DIR.exists():
        return "스킬 디렉토리 없음"

    skills = [d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
    return "📚 **사용 가능한 스킬:**\n" + "\n".join(f"• {s}" for s in sorted(skills)[:30])


def remember(user_id: str, fact: str) -> str:
    """정보 기억"""
    if user_id not in MEMORY["users"]:
        MEMORY["users"][user_id] = {"facts": [], "history": []}

    MEMORY["users"][user_id]["facts"].append(fact)
    MEMORY["users"][user_id]["facts"] = MEMORY["users"][user_id]["facts"][-20:]
    save_memory(MEMORY)
    return f"✅ 기억했어요: **{fact}**"


def get_memories(user_id: str) -> str:
    """기억 목록"""
    if user_id not in MEMORY["users"] or not MEMORY["users"][user_id].get("facts"):
        return "아직 저장된 기억이 없어요. `기억해 [내용]`으로 저장하세요!"

    facts = MEMORY["users"][user_id]["facts"]
    return "🧠 **저장된 기억:**\n" + "\n".join(f"• {f}" for f in facts)


# ═══════════════════════════════════════════════════════════════
# 메시지 처리
# ═══════════════════════════════════════════════════════════════

def process_command(text: str, user_id: str) -> tuple:
    """명령어 파싱 및 처리. (응답, 이미지URL) 반환"""
    text = text.strip()
    text_lower = text.lower()

    # 도움말
    if text_lower in ['/help', '/start', '도움', '도움말', '?']:
        return ("""🤖 **Telegram Claude Bot**

**대화:**
• 그냥 메시지 → Claude 답변
• `/codex [질문]` → Codex 답변

**주식:**
• `시세` or `주식` → 관심종목
• `주식 삼성전자` → 개별 종목

**도구:**
• `날씨 [도시]` → 날씨
• `이미지 [설명]` → 이미지 생성
• `검색 [키워드]` → 웹 검색
• `시스템` → 시스템 상태
• `실행 [명령]` → 쉘 명령
• `파일 [경로]` → 파일 읽기

**기억:**
• `기억해 [내용]` → 정보 저장
• `기억` → 저장된 기억 보기

**스킬:**
• `스킬` → 사용 가능한 스킬 목록
""", None)

    # 주식/시세
    if text_lower in ['시세', '주식', 'stock', 'stocks', '관심종목']:
        return (get_watchlist(), None)

    if re.match(r'^(주식|stock)\s+', text_lower):
        query = re.sub(r'^(주식|stock)\s+', '', text, flags=re.I)
        return (get_stock_info(query), None)

    # 날씨
    if re.match(r'^(날씨|weather)', text_lower):
        city = re.sub(r'^(날씨|weather)\s*', '', text, flags=re.I) or "Seoul"
        return (get_weather(city), None)

    # 이미지
    if re.match(r'^(이미지|그림|그려|image|draw)\s+', text_lower):
        prompt = re.sub(r'^(이미지|그림|그려줘?|image|draw)\s+', '', text, flags=re.I)
        img_url = generate_image(prompt)
        return (f"🎨 **이미지 생성:** {prompt}", img_url)

    # 검색
    if re.match(r'^(검색|search|찾기)\s+', text_lower):
        query = re.sub(r'^(검색|search|찾기)\s+', '', text, flags=re.I)
        return (f"🔍 **검색:** {query}\n\n{web_search(query)}", None)

    # 시스템
    if text_lower in ['시스템', 'system', '상태', 'status']:
        return (get_system_status(), None)

    # 실행
    if re.match(r'^(실행|exec|run|sh)\s+', text_lower):
        cmd = re.sub(r'^(실행|exec|run|sh)\s+', '', text, flags=re.I)
        return (f"💻 `{cmd}`\n{shell_execute(cmd)}", None)

    # 파일
    if re.match(r'^(파일|file|cat)\s+', text_lower):
        path = re.sub(r'^(파일|file|cat)\s+', '', text, flags=re.I)
        return (read_file(path), None)

    # 스킬
    if text_lower in ['스킬', 'skills', '기능']:
        return (list_skills(), None)

    # 기억
    if re.match(r'^(기억해|remember)\s+', text_lower):
        fact = re.sub(r'^(기억해|remember)\s+', '', text, flags=re.I)
        return (remember(user_id, fact), None)

    if text_lower in ['기억', '기억목록', 'memories', '내기억']:
        return (get_memories(user_id), None)

    # Codex
    if text.startswith('/codex '):
        prompt = text[7:]
        return (f"🤖 **Codex:**\n{ask_codex(prompt)}", None)

    # 일반 Claude 대화
    # 컨텍스트 추가
    context = ""
    if user_id in MEMORY["users"] and MEMORY["users"][user_id].get("facts"):
        facts = MEMORY["users"][user_id]["facts"][-5:]
        context = f"[사용자 정보: {', '.join(facts)}]\n\n"

    system = "너는 친절한 한국어 AI 어시스턴트야. 간결하게 답변해."
    response = ask_claude(context + text, system)
    return (f"🧠 {response}", None)


# ═══════════════════════════════════════════════════════════════
# Telegram API
# ═══════════════════════════════════════════════════════════════

def send_telegram(chat_id: str, text: str, image_url: str = None):
    """Telegram 메시지 전송"""
    if image_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        requests.post(url, json={
            "chat_id": chat_id,
            "photo": image_url,
            "caption": text[:1024],
            "parse_mode": "Markdown"
        }, timeout=30)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "Markdown"
        }, timeout=10)


def get_updates(offset=None):
    """Telegram 업데이트"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=35)
        return resp.json().get("result", [])
    except:
        return []


def process_message(msg):
    """메시지 처리"""
    chat_id = str(msg["chat"]["id"])
    text = msg.get("text", "")
    user = msg["from"].get("first_name", "User")

    if ALLOWED_USERS and chat_id not in ALLOWED_USERS:
        send_telegram(chat_id, "⛔ 승인되지 않은 사용자입니다.")
        return

    if not text:
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {user}: {text[:50]}...")

    response, image_url = process_command(text, chat_id)
    send_telegram(chat_id, response, image_url)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 응답 완료")


def main():
    print("=" * 50)
    print("🤖 Telegram Claude Bot (MoltBot Features)")
    print(f"허용된 사용자: {ALLOWED_USERS}")
    print("=" * 50)

    offset = None
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    process_message(update["message"])
        except KeyboardInterrupt:
            print("\n종료")
            break
        except Exception as e:
            print(f"오류: {e}")
            import time
            time.sleep(5)


if __name__ == "__main__":
    main()
