#!/usr/bin/env python3
"""
Haiku 컨트롤러 v2 - 뉴스 크롤링 + AI 분석
- 자동 뉴스 수집
- 주식 테마 분석
- 투자 신호 생성
"""

import subprocess
import json
import re
import os
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
import urllib.parse

# 무한 메모리
try:
    from infinite_memory import InfiniteMemory
    memory = InfiniteMemory()
except:
    memory = None


class NewsCrawler:
    """뉴스 크롤링"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def search_google_news(self, query: str, limit: int = 5) -> list:
        """Google News RSS 검색"""
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
            resp = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'xml')

            results = []
            for item in soup.find_all('item')[:limit]:
                title = item.find('title')
                pub_date = item.find('pubDate')
                if title:
                    results.append({
                        'title': title.get_text(),
                        'date': pub_date.get_text() if pub_date else '',
                        'source': 'google'
                    })
            return results
        except Exception as e:
            return [{'error': str(e)}]

    def search_naver_news(self, query: str, limit: int = 5) -> list:
        """네이버 뉴스 검색"""
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://search.naver.com/search.naver?where=news&query={encoded}"
            resp = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')

            results = []
            for item in soup.select('.news_tit')[:limit]:
                results.append({
                    'title': item.get_text(),
                    'link': item.get('href', ''),
                    'source': 'naver'
                })
            return results
        except Exception as e:
            return [{'error': str(e)}]

    def get_stock_themes(self) -> list:
        """오늘의 테마주 검색"""
        queries = ["주식 테마 급등", "코스닥 상한가", "외국인 순매수"]
        all_news = []
        for q in queries:
            all_news.extend(self.search_google_news(q, 3))
        return all_news

    def get_geopolitical_news(self) -> list:
        """지정학 뉴스"""
        queries = ["이란 미국", "중국 대만", "북한 미사일", "러시아 우크라이나"]
        all_news = []
        for q in queries:
            all_news.extend(self.search_google_news(q, 2))
        return all_news

    def get_market_news(self) -> list:
        """시장 뉴스"""
        queries = ["코스피 코스닥 지수", "외국인 기관 매수", "주식 호재"]
        all_news = []
        for q in queries:
            all_news.extend(self.search_google_news(q, 3))
        return all_news


class StockAnalyzer:
    """주식 분석"""

    def __init__(self):
        self.crawler = NewsCrawler()

    def collect_all_info(self) -> dict:
        """모든 정보 수집"""
        return {
            'themes': self.crawler.get_stock_themes(),
            'geopolitical': self.crawler.get_geopolitical_news(),
            'market': self.crawler.get_market_news(),
            'collected_at': datetime.now().isoformat()
        }

    def format_news_for_analysis(self, info: dict) -> str:
        """뉴스를 분석용 텍스트로 변환"""
        lines = ["=== 수집된 정보 ===\n"]

        lines.append("## 테마/급등 뉴스:")
        for n in info.get('themes', [])[:8]:
            if 'title' in n:
                lines.append(f"- {n['title']}")

        lines.append("\n## 지정학 뉴스:")
        for n in info.get('geopolitical', [])[:6]:
            if 'title' in n:
                lines.append(f"- {n['title']}")

        lines.append("\n## 시장 뉴스:")
        for n in info.get('market', [])[:6]:
            if 'title' in n:
                lines.append(f"- {n['title']}")

        lines.append(f"\n수집 시간: {info.get('collected_at', 'N/A')}")
        return "\n".join(lines)


class HaikuController:
    """Haiku가 다른 모델들을 부하로 관리 + 뉴스 분석"""

    def __init__(self):
        self.models = {
            "haiku": {"cmd": ["claude", "-p", "{prompt}", "--model", "haiku"], "desc": "빠른 응답"},
            "sonnet": {"cmd": ["claude", "-p", "{prompt}", "--model", "sonnet"], "desc": "분석"},
            "opus": {"cmd": ["claude", "-p", "{prompt}", "--model", "opus"], "desc": "심층 분석"},
        }
        self.call_history = []
        self.analyzer = StockAnalyzer()

    def is_investment_query(self, query: str) -> bool:
        """투자 관련 쿼리인지 확인"""
        keywords = ['주식', '투자', '매수', '매도', '테마', '종목', '시장', '코스피', '코스닥',
                   'HEARTBEAT', '분석', '사라', '팔아', '뉴스', '급등', '급락']
        return any(k in query for k in keywords)

    def analyze_investment(self, query: str) -> str:
        """투자 분석 수행"""
        # 1단계: 뉴스 수집
        print("[분석] 1단계: 뉴스 수집 중...")
        info = self.analyzer.collect_all_info()
        news_text = self.analyzer.format_news_for_analysis(info)

        # 2단계: AI 분석
        print("[분석] 2단계: AI 분석 중...")
        analysis_prompt = f"""당신은 전문 주식 애널리스트입니다. 아래 뉴스를 분석하고 투자 신호를 제시하세요.

{news_text}

사용자 요청: {query}

## 분석 지침:
1. 현재 강한 테마가 무엇인지 파악
2. 지정학 리스크와 수혜주 분석
3. 외국인/기관 동향 파악

## 반드시 아래 형식으로 응답:

### 시장 요약 (2-3줄)
[현재 시장 상황]

### 투자 신호
[아래 중 하나 선택]

🟢 매수 신호:
- 종목: [종목명]
- 이유: [구체적 근거]
- 목표가: +X%
- 손절가: -3%

또는

🔴 매도 신호:
- 종목: [종목명]
- 이유: [구체적 근거]

또는

⏸️ 관망:
- 이유: [왜 지금은 매매하면 안 되는지]
- 주목할 점: [다음에 봐야 할 것]

### 주의사항
- 추격매수 금지 (이미 많이 오른 것)
- 확실한 근거 없으면 관망
"""

        result = self.call_model("sonnet", analysis_prompt, timeout=90)
        return result.get("output", result.get("error", "분석 실패"))

    def route_query(self, user_query: str) -> str:
        """Haiku가 적절한 모델 선택"""
        # 투자 분석은 sonnet
        if self.is_investment_query(user_query):
            return "sonnet"

        # 간단한 질문은 haiku
        if len(user_query) < 50:
            return "haiku"

        return "sonnet"

    def call_model(self, model: str, prompt: str, timeout: int = 60) -> dict:
        """특정 모델 호출"""
        if model not in self.models:
            model = "haiku"

        start_time = datetime.now()

        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--model", model],
                capture_output=True, text=True, timeout=timeout,
                env={**os.environ, "LANG": "ko_KR.UTF-8"}
            )

            elapsed = (datetime.now() - start_time).total_seconds()

            self.call_history.append({
                "model": model,
                "elapsed": elapsed,
                "success": result.returncode == 0,
                "timestamp": datetime.now().isoformat()
            })

            if result.returncode == 0:
                return {"output": result.stdout.strip(), "model": model, "elapsed": elapsed}
            else:
                return {"error": result.stderr.strip(), "output": "", "model": model}

        except subprocess.TimeoutExpired:
            return {"error": "Timeout", "output": "", "model": model}
        except Exception as e:
            return {"error": str(e), "output": "", "model": model}

    def process(self, user_query: str, user_id: str = "default", force_model: str = None) -> dict:
        """사용자 질문 처리"""

        # 투자 분석 요청 감지
        if self.is_investment_query(user_query):
            print(f"[컨트롤러] 투자 분석 모드 활성화")
            output = self.analyze_investment(user_query)
            return {
                "output": output,
                "model": "sonnet",
                "routing": {"selected": "sonnet", "reason": "투자 분석"}
            }

        # 일반 질문
        if force_model and force_model in self.models:
            selected_model = force_model
        else:
            selected_model = self.route_query(user_query)

        print(f"[컨트롤러] 모델: {selected_model}")
        result = self.call_model(selected_model, user_query)
        result["routing"] = {"selected": selected_model, "reason": "자동 선택"}
        return result

    def get_stats(self) -> dict:
        """호출 통계"""
        if not self.call_history:
            return {"total_calls": 0}

        return {
            "total_calls": len(self.call_history),
            "recent": self.call_history[-5:]
        }


# API 서버
def run_api_server(host="127.0.0.1", port=8180):
    """Flask 기반 API 서버"""
    from flask import Flask, request, jsonify, Response

    app = Flask(__name__)
    controller = HaikuController()

    @app.route("/v1/messages", methods=["POST"])
    def messages():
        """Anthropic Messages API 호환"""
        import uuid

        data = request.json or {}
        messages_data = data.get("messages", [])
        model = data.get("model", "auto")
        stream = data.get("stream", False)

        if not messages_data:
            return jsonify({"error": "No messages"}), 400

        # 텍스트 추출
        user_msg = messages_data[-1].get("content", "")
        if isinstance(user_msg, list):
            user_msg = " ".join([c.get("text", "") for c in user_msg if c.get("type") == "text"])

        # 처리
        if model == "auto":
            result = controller.process(user_msg)
        else:
            result = controller.process(user_msg, force_model=model)

        output_text = result.get("output", result.get("error", ""))
        message_id = f"msg_{uuid.uuid4().hex[:24]}"

        if stream:
            def generate():
                yield f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": {"id": message_id, "type": "message", "role": "assistant", "content": [], "model": model, "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 0}}})}\n\n'
                yield f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})}\n\n'
                yield f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": output_text}})}\n\n'
                yield f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": 0})}\n\n'
                yield f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": len(output_text.split())}})}\n\n'
                yield f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n'

            return Response(generate(), mimetype='text/event-stream', headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            })
        else:
            return jsonify({
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": output_text}],
                "model": model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": len(output_text.split())},
                "routing": result.get("routing", {})
            })

    @app.route("/v1/analyze", methods=["POST"])
    def analyze():
        """투자 분석 전용 엔드포인트"""
        data = request.json or {}
        query = data.get("query", "주식 시장 분석해줘")
        result = controller.analyze_investment(query)
        return jsonify({"analysis": result})

    @app.route("/v1/news", methods=["GET"])
    def news():
        """뉴스 수집"""
        info = controller.analyzer.collect_all_info()
        return jsonify(info)

    @app.route("/v1/stats", methods=["GET"])
    def stats():
        return jsonify(controller.get_stats())

    @app.route("/health", methods=["GET"])
    def health():
        return "OK"

    print(f"Haiku Controller v2 (뉴스분석): http://{host}:{port}")
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        run_api_server()
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        # 테스트
        controller = HaikuController()
        print("=== 투자 분석 테스트 ===")
        result = controller.analyze_investment("오늘 주식 시장 분석하고 매수 신호 있으면 알려줘")
        print(result)
    else:
        print("Usage: python haiku_controller.py serve|test")
