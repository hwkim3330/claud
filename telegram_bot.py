#!/usr/bin/env python3
"""
텔레그램 AI 어시스턴트 - AGI 스타일
Clawd.bot 참고하여 더 자연스럽고 능동적인 AI
"""

import logging
import subprocess
import os
import json
import urllib.parse
import re
import requests
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.request import HTTPXRequest

# 설정
BOT_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"
MEMORY_FILE = Path("/home/kim/dooray-claude-bot/user_memory.json")
INVESTMENT_FILE = Path("/home/kim/dooray-claude-bot/dooray_data/investment_plan.json")
ALLOWED_USERS = []  # 비어있으면 모두 허용

# 로깅
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserMemory:
    """사용자 기억/컨텍스트 관리"""

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if MEMORY_FILE.exists():
            return json.loads(MEMORY_FILE.read_text())
        return {}

    def save(self):
        MEMORY_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def get_user(self, user_id: int) -> dict:
        uid = str(user_id)
        if uid not in self.data:
            self.data[uid] = {
                "name": "",
                "preferences": {},
                "history": [],
                "reminders": [],
                "last_seen": None
            }
        return self.data[uid]

    def update_history(self, user_id: int, role: str, content: str):
        user = self.get_user(user_id)
        user["history"].append({
            "role": role,
            "content": content[:500],  # 길이 제한
            "time": datetime.now().isoformat()
        })
        # 최근 20개만 유지
        user["history"] = user["history"][-20:]
        user["last_seen"] = datetime.now().isoformat()
        self.save()

    def get_context(self, user_id: int) -> str:
        user = self.get_user(user_id)
        if not user["history"]:
            return ""

        # 최근 대화 5개
        recent = user["history"][-5:]
        context = "\n".join([f"{h['role']}: {h['content']}" for h in recent])
        return f"최근 대화:\n{context}\n\n"


memory = UserMemory()


def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


def ask_claude(prompt: str, context: str = "", system: str = "", model: str = "sonnet") -> str:
    """Claude에게 질문 (컨텍스트 포함, 모델 선택 가능)"""

    system_prompt = system or """너는 텔레그램에서 동작하는 개인 AI 어시스턴트야.
특징:
- 친근하고 자연스러운 대화체 사용
- 이모지 적절히 사용
- 간결하지만 유용한 답변
- 필요하면 후속 질문
- 사용자의 의도를 파악해서 능동적으로 도움
- 한국어로 대화

할 수 있는 것:
- 일반 대화 및 질문 답변
- 이미지 생성 (사용자가 원하면)
- 뉴스/주식/점심메뉴 정보
- 웹 검색
- 코드 작성
- 번역
- 요약
- 분석"""

    full_prompt = f"{context}{prompt}" if context else prompt

    try:
        cmd = ["claude", "-p", full_prompt, "--model", model]
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        if result.returncode == 0:
            response = result.stdout.strip()
            if len(response) > 4000:
                response = response[:4000] + "\n\n...(생략)"
            return response
        return f"오류 발생 😅"
    except subprocess.TimeoutExpired:
        return "응답 시간이 초과됐어요. 다시 시도해주세요 ⏱️"
    except Exception as e:
        return f"문제가 생겼어요: {str(e)[:100]}"


def generate_image_url(prompt: str) -> str:
    """이미지 생성 URL"""
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&nologo=true"


def web_search(query: str) -> str:
    """웹 검색 (DuckDuckGo)"""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if results:
                return "\n".join([f"• {r['title']}: {r['body'][:100]}..." for r in results])
    except:
        pass
    return "검색 결과를 가져오지 못했어요"


def detect_intent(text: str) -> dict:
    """사용자 의도 파악"""
    text_lower = text.lower()

    # 모델 선택 확인
    model = "sonnet"  # 기본값
    if any(k in text_lower for k in ['opus', '오푸스', '오퍼스']):
        model = "opus"
    elif any(k in text_lower for k in ['haiku', '하이쿠']):
        model = "haiku"

    # 이미지 생성
    if any(k in text_lower for k in ['이미지', '그려', '그림', 'image', 'draw', '생성해', '만들어줘']):
        if any(k in text_lower for k in ['이미지', '그림', 'image']):
            prompt = re.sub(r'^(이미지|그려\s*줘?|그림|image|draw|generate|만들어\s*줘?|생성)\s*', '', text, flags=re.I).strip()
            return {"type": "image", "prompt": prompt or text}

    # 뉴스
    if any(k in text_lower for k in ['뉴스', 'news', '소식', '오늘 뭐']):
        return {"type": "news"}

    # 포트폴리오
    if any(k in text_lower for k in ['포트폴리오', '내투자', '내 투자', 'portfolio']):
        return {"type": "portfolio"}

    # 시세/현재가
    if any(k in text_lower for k in ['시세', '현재가', 'prices', '종목가격']):
        return {"type": "prices"}

    # 시장 분석
    if any(k in text_lower for k in ['시장분석', '분석', 'analysis']):
        return {"type": "analysis"}

    # 주식
    if any(k in text_lower for k in ['주식', 'stock', '투자', '시장', '증시']):
        return {"type": "stock"}

    # 점심
    if any(k in text_lower for k in ['점심', '메뉴', '밥', '뭐 먹', 'lunch', '식당']):
        return {"type": "lunch"}

    # 검색
    if any(k in text_lower for k in ['검색', 'search', '찾아', '알아봐']):
        query = re.sub(r'^(검색|search|찾아\s*줘?|알아봐\s*줘?)\s*', '', text, flags=re.I).strip()
        return {"type": "search", "query": query or text}

    # 날씨
    if any(k in text_lower for k in ['날씨', 'weather', '기온', '비 와', '눈 와']):
        return {"type": "weather"}

    # 번역
    if any(k in text_lower for k in ['번역', 'translate', '영어로', '한국어로']):
        return {"type": "translate", "text": text}

    # 코드
    if any(k in text_lower for k in ['코드', 'code', '프로그램', '스크립트', '함수']):
        return {"type": "code", "text": text}

    return {"type": "chat", "text": text, "model": model}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """시작"""
    user = update.effective_user
    user_id = user.id

    if not is_allowed(user_id):
        await update.message.reply_text(f"⛔ 허용되지 않은 사용자입니다.\nID: {user_id}")
        return

    # 메모리에 사용자 등록
    mem = memory.get_user(user_id)
    mem["name"] = user.first_name
    memory.save()

    keyboard = [
        [
            InlineKeyboardButton("📰 뉴스", callback_data="news"),
            InlineKeyboardButton("📈 주식", callback_data="stock"),
        ],
        [
            InlineKeyboardButton("💰 포트폴리오", callback_data="portfolio"),
            InlineKeyboardButton("📊 시세", callback_data="prices"),
        ],
        [
            InlineKeyboardButton("🍽️ 점심", callback_data="lunch"),
            InlineKeyboardButton("🎨 이미지", callback_data="image_help"),
        ],
        [
            InlineKeyboardButton("💡 도움말", callback_data="help"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"안녕하세요 {user.first_name}님! 👋\n\n"
        f"저는 당신의 AI 어시스턴트예요.\n"
        f"무엇이든 물어보세요!\n\n"
        f"💬 자연스럽게 대화하면 돼요\n"
        f"🎨 \"고양이 그려줘\" → 이미지 생성\n"
        f"🔍 \"검색 파이썬 튜토리얼\" → 웹 검색\n"
        f"📰 \"오늘 뉴스\" → 뉴스 요약\n\n"
        f"아래 버튼을 눌러도 돼요 👇",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """버튼 콜백 처리"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "news":
        await query.message.reply_text("📰 뉴스 가져오는 중...")
        await send_news(query.message)
    elif data == "stock":
        await query.message.reply_text("📈 주식 분석 중...")
        await send_stock(query.message)
    elif data == "portfolio":
        await send_portfolio(query.message)
    elif data == "prices":
        await send_prices(query.message)
    elif data == "lunch":
        await query.message.reply_text("🍽️ 점심 메뉴 확인 중... (1-2분)")
        await send_lunch(query.message)
    elif data == "image_help":
        await query.message.reply_text(
            "🎨 이미지 생성 방법:\n\n"
            "\"이미지 우주를 나는 고양이\"\n"
            "\"그려줘 해변의 일몰\"\n"
            "\"image cyberpunk city\"\n\n"
            "원하는 그림을 설명해주세요!"
        )
    elif data == "help":
        await query.message.reply_text(
            "💡 사용 가이드\n\n"
            "그냥 자연스럽게 말하면 돼요!\n\n"
            "📝 예시:\n"
            "• \"파이썬으로 정렬 함수 짜줘\"\n"
            "• \"이 영어 번역해줘: Hello world\"\n"
            "• \"오늘 IT 뉴스 뭐 있어?\"\n"
            "• \"이미지 귀여운 강아지\"\n"
            "• \"검색 최신 아이폰 가격\"\n"
            "• \"주식 시장 어때?\"\n"
            "• \"점심 뭐 먹지?\"\n\n"
            "🤖 저는 Claude AI 기반이에요!"
        )


async def send_news(message):
    """뉴스 전송"""
    try:
        import xml.etree.ElementTree as ET

        resp = requests.get("https://news.hada.io/rss/news", timeout=30)
        root = ET.fromstring(resp.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        news_items = []
        for entry in root.findall('atom:entry', ns)[:7]:
            title = entry.find('atom:title', ns)
            if title is not None:
                news_items.append(f"• {title.text}")

        news_text = "\n".join(news_items)

        # AI 요약
        summary = ask_claude(
            f"다음 IT 뉴스 헤드라인을 간단히 정리해줘. 각각 한 줄 코멘트 추가:\n{news_text}",
            system="뉴스 큐레이터로서 간결하고 유용한 정보 제공. 이모지 사용."
        )

        today = datetime.now().strftime("%m/%d")
        await message.reply_text(f"📰 {today} 오늘의 뉴스\n\n{summary}")
    except Exception as e:
        await message.reply_text(f"뉴스를 가져오지 못했어요 😅\n{str(e)[:100]}")


async def send_stock(message):
    """주식 분석 전송"""
    try:
        import xml.etree.ElementTree as ET

        resp = requests.get("https://news.hada.io/rss/news", timeout=30)
        root = ET.fromstring(resp.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        news_items = []
        for entry in root.findall('atom:entry', ns)[:10]:
            title = entry.find('atom:title', ns)
            if title is not None:
                news_items.append(title.text)

        news_text = "\n".join(news_items)

        analysis = ask_claude(
            f"오늘의 IT 뉴스를 바탕으로 주식 시장 영향 분석:\n{news_text}\n\n"
            "📊 시장 영향 (2줄)\n📈 주목 섹터\n📉 주의 섹터\n💡 투자 포인트",
            system="주식 애널리스트로서 간결하고 실용적인 분석 제공. 이모지 사용."
        )

        today = datetime.now().strftime("%m/%d")
        await message.reply_text(
            f"📈 {today} 주식 분석\n\n{analysis}\n\n⚠️ 투자 판단은 본인 책임"
        )
    except Exception as e:
        await message.reply_text(f"분석 실패 😅\n{str(e)[:100]}")


async def send_lunch(message):
    """점심 메뉴 전송"""
    try:
        import sys
        sys.path.insert(0, '/home/kim/dooray-claude-bot')
        from lunch_menu import get_all_menus, rank_menus_with_ai

        WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
        today = datetime.now()
        date_str = today.strftime("%m/%d")
        weekday = WEEKDAYS[today.weekday()]

        menus = get_all_menus()

        if not menus:
            await message.reply_text("오늘 식단 정보가 없어요 😅")
            return

        # 식당명 간소화
        clean_menus = {}
        for name, menu in menus.items():
            short = name.split(" 구내식당")[0].replace("1월 다섯째주 식단표", "").replace("1월 넷째주 식단표", "").strip()
            clean_menus[short] = menu

        menu_text = "\n\n".join([f"🍽️ {k}\n{v}" for k, v in clean_menus.items()])
        ranking = rank_menus_with_ai(clean_menus)

        result = f"🍴 {date_str}({weekday}) 점심\n\n{menu_text}\n\n📊 추천\n{ranking or '분석 실패'}"

        if len(result) > 4000:
            result = result[:4000] + "..."

        await message.reply_text(result)
    except Exception as e:
        await message.reply_text(f"메뉴 확인 실패 😅\n{str(e)[:100]}")


async def send_portfolio(message):
    """투자 포트폴리오 전송"""
    try:
        if not INVESTMENT_FILE.exists():
            await message.reply_text("❌ 투자 계획이 없어요")
            return

        plan = json.loads(INVESTMENT_FILE.read_text())

        # ISA 포트폴리오
        isa = plan.get("isa_portfolio", {})
        result = ""
        if isa:
            total = isa.get("total", 0)
            result += f"💰 ISA 포트폴리오 ({total/10000:.0f}만원)\n\n"
            for a in isa.get("allocations", []):
                result += f"• {a['etf']}: {a['ratio']*100:.0f}%\n"

        # 단기 트레이딩
        trading = plan.get("trading_portfolio", {})
        if trading:
            result += f"\n📊 단기 트레이딩\n"
            for s in trading.get("stocks", []):
                if s.get("code"):
                    result += f"• {s['name']}: {s['ratio']*100:.0f}% (목표: {s.get('target_price', 'N/A')})\n"

        await message.reply_text(result or "포트폴리오 정보 없음")
    except Exception as e:
        await message.reply_text(f"오류: {str(e)[:100]}")


async def send_prices(message):
    """주요 종목 현재가 전송"""
    try:
        stock_list = [
            ("SK하이닉스", "000660"),
            ("삼성전자", "005930"),
            ("한화에어로", "012450"),
            ("현대로템", "064350"),
            ("한미반도체", "042700"),
        ]

        results = ["📊 주요 종목 현재가\n"]

        for name, code in stock_list:
            try:
                url = f"https://m.stock.naver.com/api/stock/{code}/basic"
                resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                data = resp.json()

                price = data.get("closePrice", "N/A")
                rate = data.get("fluctuationsRatio", "0")

                emoji = "🔴" if float(rate) > 0 else "🔵" if float(rate) < 0 else "⚪"
                sign = "+" if float(rate) > 0 else ""
                results.append(f"{emoji} {name}: {price}원 ({sign}{rate}%)")
            except:
                results.append(f"⚪ {name}: 조회 실패")

        await message.reply_text("\n".join(results))
    except Exception as e:
        await message.reply_text(f"오류: {str(e)[:100]}")


async def send_market_analysis(message):
    """시장 분석 전송"""
    try:
        if not INVESTMENT_FILE.exists():
            await message.reply_text("❌ 분석 데이터가 없어요")
            return

        plan = json.loads(INVESTMENT_FILE.read_text())
        analysis = plan.get("market_analysis", {})

        if not analysis:
            await message.reply_text("❌ 시장 분석 데이터가 없어요")
            return

        result = f"📈 시장 분석 ({analysis.get('date', 'N/A')})\n\n"

        # 글로벌
        glob = analysis.get("global", {})
        if glob:
            result += f"🌍 글로벌\n"
            result += f"• Fed: {glob.get('fed', 'N/A')}\n"
            risks = glob.get("risk", [])
            if risks:
                result += f"• 리스크: {risks[0][:30]}...\n"

        # 한국 섹터
        sectors = analysis.get("korea_sectors", {})
        if sectors:
            result += f"\n🇰🇷 주도 섹터\n"
            for i in range(1, 4):
                s = sectors.get(f"rank{i}", {})
                if s:
                    result += f"{i}. {s.get('sector', '')}\n"

        await message.reply_text(result)
    except Exception as e:
        await message.reply_text(f"오류: {str(e)[:100]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """메시지 처리 - AGI 스타일"""
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.message.reply_text(f"⛔ 허용되지 않은 사용자입니다.\nID: {user_id}")
        return

    text = update.message.text.strip()
    if not text:
        return

    # 대화 기록
    memory.update_history(user_id, "user", text)

    # 의도 파악
    intent = detect_intent(text)

    # 이미지 생성
    if intent["type"] == "image":
        prompt = intent.get("prompt", text)
        if len(prompt) < 3:
            await update.message.reply_text("어떤 이미지를 원하세요? 설명해주세요 🎨")
            return

        await update.message.reply_text(f"🎨 그리는 중: {prompt[:50]}...")
        image_url = generate_image_url(prompt)
        await update.message.reply_photo(photo=image_url, caption=f"🖼️ {prompt[:100]}")
        memory.update_history(user_id, "assistant", f"[이미지 생성: {prompt}]")
        return

    # 뉴스
    if intent["type"] == "news":
        await update.message.reply_text("📰 뉴스 가져오는 중...")
        await send_news(update.message)
        return

    # 주식
    if intent["type"] == "stock":
        await update.message.reply_text("📈 분석 중...")
        await send_stock(update.message)
        return

    # 포트폴리오
    if intent["type"] == "portfolio":
        await send_portfolio(update.message)
        return

    # 시세
    if intent["type"] == "prices":
        await send_prices(update.message)
        return

    # 시장 분석
    if intent["type"] == "analysis":
        await send_market_analysis(update.message)
        return

    # 점심
    if intent["type"] == "lunch":
        await update.message.reply_text("🍽️ 메뉴 확인 중... (1-2분)")
        await send_lunch(update.message)
        return

    # 검색
    if intent["type"] == "search":
        query = intent.get("query", text)
        await update.message.reply_text(f"🔍 검색 중: {query[:30]}...")

        results = web_search(query)
        response = ask_claude(
            f"검색 결과를 바탕으로 '{query}'에 대해 답변해줘:\n{results}",
            system="검색 결과를 종합해서 유용한 답변 제공"
        )
        await update.message.reply_text(response)
        memory.update_history(user_id, "assistant", response[:200])
        return

    # 일반 대화 - Claude
    user_context = memory.get_context(user_id)
    model = intent.get("model", "sonnet")

    # 타이핑 표시
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # 모델 표시
    model_emoji = {"opus": "🧠", "sonnet": "💬", "haiku": "⚡"}.get(model, "💬")

    response = ask_claude(text, context=user_context, model=model)
    await update.message.reply_text(f"{model_emoji} ({model})\n\n{response}")

    memory.update_history(user_id, "assistant", response[:200])


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """이미지 처리"""
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        return

    await update.message.reply_text("🖼️ 이미지 분석은 아직 준비 중이에요!")


def main():
    """봇 시작"""
    print("🤖 텔레그램 AI 어시스턴트 시작...")

    # DuckDuckGo 검색 설치 확인
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        os.system("pip3 install --break-system-packages duckduckgo-search -q")

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    # 핸들러
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ 봇 실행 중!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=5)


if __name__ == "__main__":
    main()
