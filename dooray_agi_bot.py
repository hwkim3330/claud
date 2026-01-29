#!/usr/bin/env python3
"""
두레이 AGI 봇 - 시스템 전체 권한
Claude가 할 수 있는 모든 것을 두레이에서!

명령어:
  /s [질문]           - Claude 대화
  /s 이미지 [설명]    - 이미지 생성
  /s 실행 [명령]      - 쉘 명령 실행
  /s 파일 [경로]      - 파일 읽기
  /s 검색 [키워드]    - 웹 검색
  /s 브라우저 [URL]   - 웹페이지 열기
  /s 스크린샷         - 현재 화면 캡처
  /s 주식 [종목]      - 주식 정보
  /s 코드 [언어] ...  - 코드 실행
  /s 시스템           - 시스템 상태
"""

from flask import Flask, request, jsonify
import subprocess
import threading
import urllib.parse
import os
import re
import json
import psutil
import requests
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

# 설정
ALLOWED_COMMANDS = True  # 쉘 명령 허용
MAX_OUTPUT_LENGTH = 3000
DATA_DIR = Path("/home/kim/dooray-claude-bot/dooray_data")
DATA_DIR.mkdir(exist_ok=True)
MEMORY_FILE = DATA_DIR / "memory.json"
INVESTMENT_FILE = DATA_DIR / "investment_plan.json"


# ═══════════════════════════════════════════════════════════════
# 영구 메모리 시스템
# ═══════════════════════════════════════════════════════════════

class DoorayMemory:
    """두레이 사용자별 영구 메모리"""

    def __init__(self):
        self.data = self._load()
        self.lock = threading.Lock()

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text())
            except:
                pass
        return {
            "users": {},
            "facts": [],
            "preferences": {},
            "conversations": {}
        }

    def save(self):
        with self.lock:
            MEMORY_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def get_user(self, user_id: str, user_name: str = "") -> dict:
        """사용자 정보 가져오기/생성"""
        if user_id not in self.data["users"]:
            self.data["users"][user_id] = {
                "name": user_name,
                "first_seen": datetime.now().isoformat(),
                "last_seen": None,
                "message_count": 0,
                "facts": [],
                "preferences": {},
                "history": []
            }
        elif user_name and not self.data["users"][user_id]["name"]:
            self.data["users"][user_id]["name"] = user_name
        return self.data["users"][user_id]

    def add_message(self, user_id: str, user_name: str, role: str, content: str):
        """메시지 기록 추가"""
        user = self.get_user(user_id, user_name)
        user["history"].append({
            "role": role,
            "content": content[:2000],
            "time": datetime.now().isoformat()
        })
        user["history"] = user["history"][-50:]  # 최근 50개 유지
        user["message_count"] += 1
        user["last_seen"] = datetime.now().isoformat()
        self.save()

    def add_fact(self, user_id: str, fact: str):
        """사용자 정보 저장"""
        user = self.get_user(user_id)
        if fact not in user["facts"]:
            user["facts"].append(fact)
            user["facts"] = user["facts"][-20:]  # 최근 20개
            self.save()

    def get_context(self, user_id: str, user_name: str = "") -> str:
        """대화 컨텍스트 생성"""
        user = self.get_user(user_id, user_name)

        context_parts = []

        # 사용자 정보
        if user["name"]:
            context_parts.append(f"사용자: {user['name']}")

        # 저장된 정보
        if user["facts"]:
            context_parts.append(f"기억된 정보: {', '.join(user['facts'][-5])}")

        # 최근 대화 (최근 5개)
        if user["history"]:
            recent = user["history"][-5:]
            history_text = "\n".join([
                f"{'사용자' if h['role'] == 'user' else 'Claude'}: {h['content'][:100]}"
                for h in recent
            ])
            context_parts.append(f"최근 대화:\n{history_text}")

        return "\n".join(context_parts) if context_parts else ""


# 메모리 인스턴스
memory = DoorayMemory()


class AGIWorker:
    """AGI 스타일 워커 - 모든 기능 통합"""

    def __init__(self):
        self.lock = threading.Lock()
        self.browser_page = None

    def claude_ask(self, question, model="sonnet", context=""):
        """Claude에게 질문 (컨텍스트 포함)"""
        with self.lock:
            try:
                # 컨텍스트가 있으면 질문에 포함
                if context:
                    full_question = f"""[이전 대화 컨텍스트]
{context}

[현재 질문]
{question}

위 컨텍스트를 참고하여 답변해주세요. 이전 대화 내용이 있다면 자연스럽게 이어서 대화하세요."""
                else:
                    full_question = question

                result = subprocess.run(
                    ["claude", "-p", full_question, "--model", model],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={**os.environ, "LANG": "ko_KR.UTF-8"}
                )
                if result.returncode == 0:
                    answer = result.stdout.strip()
                    if len(answer) > MAX_OUTPUT_LENGTH:
                        answer = answer[:MAX_OUTPUT_LENGTH] + "\n...(생략)"
                    return answer
                return f"오류: {result.stderr.strip()[:200]}"
            except subprocess.TimeoutExpired:
                return "⏱️ 시간 초과 (120초)"
            except Exception as e:
                return f"오류: {str(e)}"

    def shell_execute(self, command):
        """쉘 명령 실행"""
        if not ALLOWED_COMMANDS:
            return "⚠️ 쉘 명령이 비활성화되어 있습니다"

        # 위험한 명령 차단
        dangerous = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"]
        for d in dangerous:
            if d in command.lower():
                return f"⛔ 위험한 명령 차단됨: {d}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/home/kim"
            )
            output = result.stdout + result.stderr
            if len(output) > MAX_OUTPUT_LENGTH:
                output = output[:MAX_OUTPUT_LENGTH] + "\n...(생략)"
            return output if output.strip() else "(출력 없음)"
        except subprocess.TimeoutExpired:
            return "⏱️ 시간 초과 (30초)"
        except Exception as e:
            return f"오류: {str(e)}"

    def read_file(self, filepath):
        """파일 읽기"""
        try:
            path = Path(filepath).expanduser()
            if not path.exists():
                return f"❌ 파일 없음: {filepath}"
            if path.is_dir():
                files = list(path.iterdir())[:20]
                return "📁 디렉토리 내용:\n" + "\n".join(f"  {'📁' if f.is_dir() else '📄'} {f.name}" for f in files)
            content = path.read_text()
            if len(content) > MAX_OUTPUT_LENGTH:
                content = content[:MAX_OUTPUT_LENGTH] + "\n...(생략)"
            return f"📄 {filepath}:\n```\n{content}\n```"
        except Exception as e:
            return f"오류: {str(e)}"

    def write_file(self, filepath, content):
        """파일 쓰기"""
        try:
            path = Path(filepath).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return f"✅ 파일 저장됨: {filepath}"
        except Exception as e:
            return f"오류: {str(e)}"

    def web_search(self, query):
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
                        results.append(f"• {topic['Text'][:100]}")

            return "\n".join(results) if results else "검색 결과 없음"
        except Exception as e:
            return f"검색 오류: {str(e)}"

    def get_stock_info(self, query):
        """주식 정보 조회"""
        try:
            # 종목 검색
            search_url = f"https://m.stock.naver.com/api/json/search/searchListJson.naver?keyword={urllib.parse.quote(query)}"
            resp = requests.get(search_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})

            # 직접 코드로 조회 시도
            code = query if query.isdigit() else None
            if not code:
                # 이름으로 검색
                data = resp.json()
                items = data.get("result", {}).get("d", [])
                if items:
                    code = items[0].get("cd", "")

            if not code:
                return f"❌ 종목을 찾을 수 없음: {query}"

            # 주식 정보 조회
            url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            data = resp.json()

            name = data.get("stockName", query)
            price = data.get("closePrice", "0")
            change = data.get("compareToPreviousClosePrice", "0")
            rate = data.get("fluctuationsRatio", "0")

            # 수급 정보
            trend_url = f"https://m.stock.naver.com/api/stock/{code}/trend?page=1&pageSize=1"
            trend_resp = requests.get(trend_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            trend_data = trend_resp.json()

            foreign = "N/A"
            inst = "N/A"
            if trend_data:
                foreign = trend_data[0].get("foreignerPureBuyQuant", "N/A")
                inst = trend_data[0].get("organPureBuyQuant", "N/A")

            emoji = "🔴" if float(rate) > 0 else "🔵" if float(rate) < 0 else "⚪"

            return f"""📊 **{name}** ({code})

{emoji} 현재가: **{price}원** ({'+' if float(rate) > 0 else ''}{rate}%)
전일대비: {change}원

📈 수급 현황:
• 외국인: {foreign}
• 기관: {inst}
"""
        except Exception as e:
            return f"주식 조회 오류: {str(e)}"

    def get_system_status(self):
        """시스템 상태"""
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # 실행 중인 봇 확인
        bots = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'agi_bot' in cmdline:
                    bots.append(f"🤖 텔레그램 AGI (PID: {proc.info['pid']})")
                elif 'dooray' in cmdline and 'python' in cmdline:
                    bots.append(f"💬 두레이 봇 (PID: {proc.info['pid']})")
            except:
                pass

        return f"""🖥️ **시스템 상태**

**CPU:** {cpu}%
**메모리:** {mem.percent}% ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)
**디스크:** {disk.percent}% ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)

**실행 중인 봇:**
{chr(10).join(bots) if bots else '없음'}

**시간:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    def run_code(self, language, code):
        """코드 실행"""
        runners = {
            "python": ["python3", "-c"],
            "py": ["python3", "-c"],
            "node": ["node", "-e"],
            "js": ["node", "-e"],
            "bash": ["bash", "-c"],
            "sh": ["sh", "-c"],
        }

        if language not in runners:
            return f"❌ 지원하지 않는 언어: {language}\n지원: {', '.join(runners.keys())}"

        try:
            result = subprocess.run(
                runners[language] + [code],
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout + result.stderr
            if len(output) > MAX_OUTPUT_LENGTH:
                output = output[:MAX_OUTPUT_LENGTH] + "\n...(생략)"
            return f"```\n{output}\n```" if output.strip() else "(출력 없음)"
        except subprocess.TimeoutExpired:
            return "⏱️ 시간 초과 (10초)"
        except Exception as e:
            return f"오류: {str(e)}"

    def generate_image(self, prompt):
        """이미지 생성"""
        # 한글이면 번역
        if any('\uac00' <= c <= '\ud7a3' for c in prompt):
            translated = self.claude_ask(
                f"Translate to English for image generation. Only output the translation: {prompt}",
                model="haiku"
            )
            prompt = translated

        encoded = urllib.parse.quote(prompt)
        return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true", prompt

    def get_portfolio(self):
        """투자 포트폴리오 조회"""
        try:
            if not INVESTMENT_FILE.exists():
                return "❌ 투자 계획이 없습니다."

            plan = json.loads(INVESTMENT_FILE.read_text())

            # ISA 포트폴리오
            isa = plan.get("isa_portfolio", {})
            isa_text = ""
            if isa:
                total = isa.get("total", 0)
                isa_text = f"**💰 ISA 포트폴리오** ({total/10000:.0f}만원)\n"
                for a in isa.get("allocations", []):
                    isa_text += f"• {a['etf']}: {a['ratio']*100:.0f}% ({a['amount']/10000:.0f}만원)\n"

            # 단기 트레이딩
            trading = plan.get("trading_portfolio", {})
            trading_text = ""
            if trading:
                trading_text = f"\n**📊 단기 트레이딩**\n"
                for s in trading.get("stocks", []):
                    if s.get("code"):
                        trading_text += f"• {s['name']}: {s['ratio']*100:.0f}% (목표: {s.get('target_price', 'N/A')})\n"

            # 관심종목
            watchlist = trading.get("watchlist", [])
            watch_text = ""
            if watchlist:
                watch_text = f"\n**👀 관심종목**\n"
                for w in watchlist[:5]:
                    watch_text += f"• {w['name']}: {w.get('note', '')}\n"

            return isa_text + trading_text + watch_text
        except Exception as e:
            return f"오류: {str(e)}"

    def get_multiple_stocks(self, codes):
        """여러 종목 현재가 조회"""
        stock_list = [
            ("SK하이닉스", "000660"),
            ("삼성전자", "005930"),
            ("한화에어로스페이스", "012450"),
            ("현대로템", "064350"),
            ("한미반도체", "042700"),
        ]

        results = ["**📊 주요 종목 현재가**\n"]

        for name, code in stock_list:
            try:
                url = f"https://m.stock.naver.com/api/stock/{code}/basic"
                resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                data = resp.json()

                price = data.get("closePrice", "N/A")
                rate = data.get("fluctuationsRatio", "0")

                emoji = "🔴" if float(rate) > 0 else "🔵" if float(rate) < 0 else "⚪"
                results.append(f"{emoji} **{name}**: {price}원 ({'+' if float(rate) > 0 else ''}{rate}%)")
            except:
                results.append(f"⚪ **{name}**: 조회 실패")

        return "\n".join(results)

    def get_market_analysis(self):
        """시장 분석 조회"""
        try:
            if not INVESTMENT_FILE.exists():
                return "❌ 분석 데이터가 없습니다."

            plan = json.loads(INVESTMENT_FILE.read_text())
            analysis = plan.get("market_analysis", {})

            if not analysis:
                return "❌ 시장 분석 데이터가 없습니다."

            result = f"**📈 시장 분석** ({analysis.get('date', 'N/A')})\n\n"

            # 글로벌
            glob = analysis.get("global", {})
            if glob:
                result += f"**🌍 글로벌**\n"
                result += f"• Fed: {glob.get('fed', 'N/A')}\n"
                risks = glob.get("risk", [])
                if risks:
                    result += f"• 리스크: {', '.join(risks[:2])}\n"

            # 한국 섹터
            sectors = analysis.get("korea_sectors", {})
            if sectors:
                result += f"\n**🇰🇷 주도 섹터**\n"
                for i in range(1, 4):
                    s = sectors.get(f"rank{i}", {})
                    if s:
                        result += f"{i}. {s.get('sector', '')}: {s.get('reason', '')}\n"

            return result
        except Exception as e:
            return f"오류: {str(e)}"

    def browse_url(self, url):
        """웹페이지 내용 가져오기"""
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            # 간단히 텍스트만 추출
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                def handle_data(self, data):
                    self.text.append(data.strip())

            parser = TextExtractor()
            parser.feed(resp.text)
            text = ' '.join(filter(None, parser.text))

            if len(text) > MAX_OUTPUT_LENGTH:
                text = text[:MAX_OUTPUT_LENGTH] + "..."

            return f"🌐 {url}\n\n{text}"
        except Exception as e:
            return f"오류: {str(e)}"


# 워커 인스턴스
agi = AGIWorker()


def parse_command(text):
    """명령어 파싱"""
    text = text.strip()

    # 이미지 생성
    if re.match(r'^(이미지|그려|그림|image|draw)\s+', text, re.I):
        prompt = re.sub(r'^(이미지|그려줘?|그림|image|draw)\s+', '', text, flags=re.I)
        return "image", prompt

    # 쉘 실행
    if re.match(r'^(실행|exec|run|shell|sh)\s+', text, re.I):
        cmd = re.sub(r'^(실행|exec|run|shell|sh)\s+', '', text, flags=re.I)
        return "shell", cmd

    # 파일 읽기
    if re.match(r'^(파일|file|read|cat)\s+', text, re.I):
        path = re.sub(r'^(파일|file|read|cat)\s+', '', text, flags=re.I)
        return "file", path

    # 검색
    if re.match(r'^(검색|search|찾기)\s+', text, re.I):
        query = re.sub(r'^(검색|search|찾기)\s+', '', text, flags=re.I)
        return "search", query

    # 브라우저
    if re.match(r'^(브라우저|browser|웹|web|url)\s+', text, re.I):
        url = re.sub(r'^(브라우저|browser|웹|web|url)\s+', '', text, flags=re.I)
        if not url.startswith('http'):
            url = 'https://' + url
        return "browser", url

    # 주식
    if re.match(r'^(주식|stock|종목)\s+', text, re.I):
        query = re.sub(r'^(주식|stock|종목)\s+', '', text, flags=re.I)
        return "stock", query

    # 코드 실행
    if re.match(r'^(코드|code)\s+', text, re.I):
        rest = re.sub(r'^(코드|code)\s+', '', text, flags=re.I)
        parts = rest.split(None, 1)
        if len(parts) >= 2:
            return "code", (parts[0], parts[1])
        return "code", ("python", rest)

    # 시스템 상태
    if re.match(r'^(시스템|system|상태|status)$', text, re.I):
        return "system", None

    # 도움말
    if re.match(r'^(도움|help|\?)$', text, re.I):
        return "help", None

    # 기억하기
    if re.match(r'^(기억해|기억|remember)\s+', text, re.I):
        fact = re.sub(r'^(기억해|기억|remember)\s+', '', text, flags=re.I)
        return "remember", fact

    # 기억 보기
    if re.match(r'^(기억목록|memories|내정보)$', text, re.I):
        return "memories", None

    # 투자 포트폴리오
    if re.match(r'^(투자|포트폴리오|portfolio|내투자)$', text, re.I):
        return "portfolio", None

    # 현재가 조회
    if re.match(r'^(시세|현재가|price|prices)$', text, re.I):
        return "prices", None

    # 시장 분석
    if re.match(r'^(분석|시장|market|analysis)$', text, re.I):
        return "analysis", None

    # 모델 선택
    model = "sonnet"
    if re.search(r'(opus|오푸스|오퍼스)', text, re.I):
        model = "opus"
        text = re.sub(r'\s*(opus|오푸스|오퍼스)\s*', ' ', text, flags=re.I).strip()
    elif re.search(r'(haiku|하이쿠)', text, re.I):
        model = "haiku"
        text = re.sub(r'\s*(haiku|하이쿠)\s*', ' ', text, flags=re.I).strip()

    # 일반 Claude 질문
    return "claude", (text, model)


@app.route("/slash", methods=["POST"])
def slash():
    """두레이 슬래시 커맨드"""
    data = request.json or {}

    user_name = data.get("userName", "사용자")
    user_id = data.get("userId", data.get("tenantId", user_name))  # 사용자 ID
    text = data.get("text", "").strip()

    print(f"[요청] {user_name}({user_id}): {text}")

    if not text:
        return jsonify({
            "text": get_help_text(),
            "responseType": "ephemeral"
        })

    # 메모리에 사용자 메시지 기록
    memory.add_message(str(user_id), user_name, "user", text)

    cmd, arg = parse_command(text)

    # 명령어 처리
    if cmd == "help":
        return jsonify({"text": get_help_text(), "responseType": "ephemeral"})

    elif cmd == "image":
        image_url, prompt = agi.generate_image(arg)
        return jsonify({
            "text": f"**🎨 {user_name}:** {arg}",
            "responseType": "inChannel",
            "attachments": [{
                "title": "생성된 이미지",
                "text": f"프롬프트: {prompt}",
                "imageUrl": image_url,
                "color": "green"
            }]
        })

    elif cmd == "shell":
        result = agi.shell_execute(arg)
        return jsonify({
            "text": f"**💻 {user_name}:** `{arg}`\n\n```\n{result}\n```",
            "responseType": "inChannel"
        })

    elif cmd == "file":
        result = agi.read_file(arg)
        return jsonify({
            "text": f"**📁 {user_name}:** {arg}\n\n{result}",
            "responseType": "inChannel"
        })

    elif cmd == "search":
        result = agi.web_search(arg)
        return jsonify({
            "text": f"**🔍 {user_name}:** {arg}\n\n{result}",
            "responseType": "inChannel"
        })

    elif cmd == "browser":
        result = agi.browse_url(arg)
        return jsonify({
            "text": f"**🌐 {user_name}**\n\n{result}",
            "responseType": "inChannel"
        })

    elif cmd == "stock":
        result = agi.get_stock_info(arg)
        return jsonify({
            "text": f"**📈 {user_name}:** {arg}\n\n{result}",
            "responseType": "inChannel"
        })

    elif cmd == "code":
        lang, code = arg
        result = agi.run_code(lang, code)
        return jsonify({
            "text": f"**🖥️ {user_name}:** ({lang})\n\n{result}",
            "responseType": "inChannel"
        })

    elif cmd == "system":
        result = agi.get_system_status()
        return jsonify({
            "text": result,
            "responseType": "inChannel"
        })

    elif cmd == "remember":
        memory.add_fact(str(user_id), arg)
        return jsonify({
            "text": f"✅ 기억했어요: **{arg}**",
            "responseType": "inChannel"
        })

    elif cmd == "memories":
        user_data = memory.get_user(str(user_id), user_name)
        facts = user_data.get("facts", [])
        if facts:
            facts_text = "\n".join([f"• {f}" for f in facts])
            result = f"🧠 **{user_name}님의 기억**\n\n{facts_text}\n\n📊 총 대화: {user_data.get('message_count', 0)}회"
        else:
            result = "아직 저장된 기억이 없어요. `/s 기억해 [내용]`으로 저장하세요!"
        return jsonify({
            "text": result,
            "responseType": "ephemeral"
        })

    elif cmd == "portfolio":
        result = agi.get_portfolio()
        return jsonify({
            "text": f"**📊 {user_name}님의 투자 계획**\n\n{result}",
            "responseType": "inChannel"
        })

    elif cmd == "prices":
        result = agi.get_multiple_stocks(None)
        return jsonify({
            "text": result,
            "responseType": "inChannel"
        })

    elif cmd == "analysis":
        result = agi.get_market_analysis()
        return jsonify({
            "text": result,
            "responseType": "inChannel"
        })

    else:  # claude
        # 메모리에서 컨텍스트 가져오기
        context = memory.get_context(str(user_id), user_name)

        # arg가 튜플이면 (텍스트, 모델) 분리
        if isinstance(arg, tuple):
            question, model = arg
        else:
            question, model = arg, "sonnet"

        answer = agi.claude_ask(question, model=model, context=context)

        # 응답을 메모리에 저장
        memory.add_message(str(user_id), user_name, "assistant", answer)

        model_emoji = {"opus": "🧠", "sonnet": "💬", "haiku": "⚡"}.get(model, "💬")

        return jsonify({
            "text": f"**🙋 {user_name}:** {question}\n\n**{model_emoji} Claude ({model}):**\n{answer}",
            "responseType": "inChannel"
        })


def get_help_text():
    return """🤖 **두레이 AGI 봇** (메모리 + 투자 기능!)

**대화 & 기억:**
• `/s [질문]` - Claude 대화 (이전 대화 기억!)
• `/s 기억해 [내용]` - 정보 저장
• `/s 기억목록` - 저장된 기억 보기

**💰 투자:**
• `/s 투자` - 내 포트폴리오 보기
• `/s 시세` - 주요 종목 현재가
• `/s 분석` - 시장 분석
• `/s 주식 [종목]` - 개별 종목 조회

**도구:**
• `/s 이미지 [설명]` - 이미지 생성
• `/s 실행 [명령]` - 쉘 명령 실행
• `/s 파일 [경로]` - 파일 읽기
• `/s 검색 [키워드]` - 웹 검색
• `/s 브라우저 [URL]` - 웹페이지 열기
• `/s 코드 [언어] [코드]` - 코드 실행
• `/s 시스템` - 시스템 상태

**예시:**
• `/s 투자` → 포트폴리오 조회
• `/s 시세` → SK하이닉스, 삼성전자 등 현재가
• `/s 주식 카카오` → 개별 종목 조회
"""


@app.route("/image", methods=["POST"])
def image():
    """이미지 생성 전용"""
    data = request.json or {}
    user = data.get("userName", "사용자")
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"text": "사용법: `/이미지 [설명]`", "responseType": "ephemeral"})

    image_url, prompt = agi.generate_image(text)
    return jsonify({
        "text": f"**🎨 {user_name}:** {text}",
        "responseType": "inChannel",
        "attachments": [{
            "title": "생성된 이미지",
            "imageUrl": image_url,
            "color": "green"
        }]
    })


@app.route("/exec", methods=["POST"])
def exec_cmd():
    """쉘 명령 전용"""
    data = request.json or {}
    user = data.get("userName", "사용자")
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"text": "사용법: `/exec [명령]`", "responseType": "ephemeral"})

    result = agi.shell_execute(text)
    return jsonify({
        "text": f"**💻 {user_name}:** `{text}`\n\n```\n{result}\n```",
        "responseType": "inChannel"
    })


@app.route("/stock", methods=["POST"])
def stock():
    """주식 정보 전용"""
    data = request.json or {}
    user = data.get("userName", "사용자")
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"text": "사용법: `/stock [종목명/코드]`", "responseType": "ephemeral"})

    result = agi.get_stock_info(text)
    return jsonify({
        "text": f"**📈 {user_name}:** {text}\n\n{result}",
        "responseType": "inChannel"
    })


@app.route("/health", methods=["GET"])
def health():
    return "OK"


@app.route("/", methods=["GET"])
def home():
    return """
    <h1>🤖 두레이 AGI 봇</h1>
    <p>시스템 전체 권한을 가진 Claude 봇</p>
    <h3>엔드포인트:</h3>
    <ul>
        <li>POST /slash - 메인 슬래시 커맨드</li>
        <li>POST /image - 이미지 생성</li>
        <li>POST /exec - 쉘 실행</li>
        <li>POST /stock - 주식 정보</li>
    </ul>
    """


if __name__ == "__main__":
    print("=" * 50)
    print("🤖 두레이 AGI 봇 - 시스템 전체 권한")
    print("=" * 50)
    print("명령어:")
    print("  /s [질문]        - Claude 대화")
    print("  /s 이미지 [설명] - 이미지 생성")
    print("  /s 실행 [명령]   - 쉘 명령")
    print("  /s 파일 [경로]   - 파일 읽기")
    print("  /s 검색 [키워드] - 웹 검색")
    print("  /s 주식 [종목]   - 주식 정보")
    print("  /s 코드 [언어]   - 코드 실행")
    print("  /s 시스템        - 상태 확인")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, threaded=True)
