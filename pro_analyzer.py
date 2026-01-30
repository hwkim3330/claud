#!/usr/bin/env python3
"""
프로 주식 분석기 - 뉴스 기반 미래 예측
- 다중 뉴스 소스 크롤링
- AI 기반 심층 분석
- 섹터/테마 연관 분석
- 매매 시그널 생성
"""

import requests
import json
import re
import urllib.parse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# AI 분석용
HAIKU_URL = "http://127.0.0.1:8180/v1/messages"


class ProAnalyzer:
    """전문 주식 분석기"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def fetch_naver_news(self, keyword: str, limit: int = 10) -> list:
        """네이버 뉴스 검색"""
        news = []
        try:
            query = urllib.parse.quote(keyword)
            url = f"https://search.naver.com/search.naver?where=news&query={query}&sort=1"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')

            for item in soup.select('.news_tit')[:limit]:
                news.append({
                    'title': item.get_text(strip=True),
                    'url': item.get('href', ''),
                    'source': 'naver'
                })
        except:
            pass
        return news

    def fetch_google_news(self, keyword: str, limit: int = 10) -> list:
        """구글 뉴스 RSS"""
        news = []
        try:
            query = urllib.parse.quote(f"{keyword} 주식")
            url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, 'xml')

            for item in soup.find_all('item')[:limit]:
                title = item.find('title')
                pub_date = item.find('pubDate')
                news.append({
                    'title': title.get_text() if title else '',
                    'date': pub_date.get_text() if pub_date else '',
                    'source': 'google'
                })
        except:
            pass
        return news

    def fetch_investing_news(self, limit: int = 10) -> list:
        """인베스팅닷컴 한국 뉴스"""
        news = []
        try:
            url = "https://kr.investing.com/news/stock-market-news"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')

            for item in soup.select('a.title')[:limit]:
                news.append({
                    'title': item.get_text(strip=True),
                    'source': 'investing'
                })
        except:
            pass
        return news

    def fetch_sector_news(self, sector: str) -> list:
        """섹터별 뉴스"""
        sector_keywords = {
            '반도체': ['반도체', 'HBM', 'AI칩', '메모리', 'DRAM', 'NAND', '파운드리'],
            '2차전지': ['2차전지', '배터리', '전기차', 'EV', '리튬', '양극재', '음극재'],
            '바이오': ['바이오', '신약', '임상', 'FDA', '제약', '헬스케어'],
            'IT': ['AI', '클라우드', '데이터센터', '소프트웨어', 'SaaS'],
            '자동차': ['자동차', '현대차', '기아', '전기차', '자율주행'],
            '금융': ['금리', '은행', '증권', '보험', '핀테크'],
        }

        keywords = sector_keywords.get(sector, [sector])
        all_news = []

        for kw in keywords[:3]:
            all_news.extend(self.fetch_google_news(kw, 5))

        return all_news

    def get_market_sentiment(self) -> dict:
        """시장 전체 센티먼트"""
        indicators = {}

        # 코스피/코스닥 지수
        try:
            resp = self.session.get("https://finance.naver.com/sise/", timeout=5)
            soup = BeautifulSoup(resp.text, 'html.parser')

            kospi = soup.select_one('#KOSPI_now')
            kosdaq = soup.select_one('#KOSDAQ_now')

            if kospi:
                indicators['kospi'] = kospi.get_text(strip=True)
            if kosdaq:
                indicators['kosdaq'] = kosdaq.get_text(strip=True)
        except:
            pass

        # VIX (공포지수) - 간접 추정
        try:
            news = self.fetch_google_news("VIX 공포지수", 3)
            indicators['vix_news'] = [n['title'] for n in news]
        except:
            pass

        return indicators

    def analyze_with_ai(self, stock_name: str, news_list: list, price_data: dict = None) -> dict:
        """AI로 심층 분석"""
        news_text = "\n".join([f"- {n['title']}" for n in news_list[:15]])

        price_info = ""
        if price_data:
            price_info = f"""
현재가: {price_data.get('price', 'N/A'):,}원
등락률: {price_data.get('change', 0):+.2f}%
거래량: {price_data.get('volume', 'N/A')}
"""

        prompt = f"""당신은 10년 경력의 한국 주식 전문 애널리스트입니다.
다음 {stock_name} 관련 최신 뉴스를 분석하고 투자 전략을 제시하세요.

{price_info}

=== 최신 뉴스 ===
{news_text}

다음 형식으로 분석해주세요:

## 📊 핵심 분석
(뉴스에서 파악되는 핵심 이슈 3가지)

## 🔮 단기 전망 (1-2주)
(뉴스 기반 단기 방향성 예측과 근거)

## 📈 중기 전망 (1-3개월)
(산업 트렌드 기반 중기 전망)

## ⚠️ 리스크 요인
(주의해야 할 위험 요소)

## 💡 투자 전략
- 매수 적정가:
- 목표가:
- 손절가:
- 추천 포지션: (적극매수/매수/관망/매도)

## 🎯 결론
(한 줄 요약)
"""

        try:
            resp = requests.post(
                HAIKU_URL,
                json={
                    "model": "sonnet",  # 분석은 sonnet 사용
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000
                },
                timeout=120
            )
            if resp.status_code == 200:
                data = resp.json()
                if "content" in data and len(data["content"]) > 0:
                    return {
                        "analysis": data["content"][0].get("text", ""),
                        "model": data.get("model", "unknown"),
                        "timestamp": datetime.now().isoformat()
                    }
        except Exception as e:
            print(f"AI 분석 오류: {e}")

        return {"analysis": "분석 실패", "error": True}

    def analyze_stock(self, code: str, name: str, price_data: dict = None) -> dict:
        """종목 종합 분석"""
        print(f"[분석중] {name}...")

        # 뉴스 수집 (병렬)
        all_news = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(self.fetch_naver_news, name, 10),
                executor.submit(self.fetch_google_news, name, 10),
            ]
            for f in as_completed(futures):
                try:
                    all_news.extend(f.result())
                except:
                    pass

        # 중복 제거
        seen = set()
        unique_news = []
        for n in all_news:
            if n['title'] not in seen:
                seen.add(n['title'])
                unique_news.append(n)

        # AI 분석
        ai_result = self.analyze_with_ai(name, unique_news, price_data)

        return {
            "code": code,
            "name": name,
            "news_count": len(unique_news),
            "news": unique_news[:10],
            "analysis": ai_result.get("analysis", ""),
            "model": ai_result.get("model", ""),
            "timestamp": datetime.now().isoformat()
        }

    def analyze_sector(self, sector: str) -> dict:
        """섹터 분석"""
        print(f"[섹터 분석] {sector}...")

        news = self.fetch_sector_news(sector)

        prompt = f"""당신은 한국 증시 섹터 전문 애널리스트입니다.
{sector} 섹터의 최신 뉴스를 분석하고 투자 전략을 제시하세요.

=== 최신 뉴스 ===
{chr(10).join([f"- {n['title']}" for n in news[:15]])}

다음 형식으로 분석:

## 🏭 섹터 현황
(현재 섹터 상황 요약)

## 📰 핵심 이슈
(주요 뉴스 3개 분석)

## 🔮 섹터 전망
(향후 1-3개월 전망)

## 💰 추천 종목
(이 섹터에서 주목할 종목 3개와 이유)

## ⚠️ 주의 종목
(피해야 할 종목과 이유)
"""

        try:
            resp = requests.post(
                HAIKU_URL,
                json={
                    "model": "sonnet",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000
                },
                timeout=120
            )
            if resp.status_code == 200:
                data = resp.json()
                if "content" in data:
                    return {
                        "sector": sector,
                        "news_count": len(news),
                        "analysis": data["content"][0].get("text", ""),
                        "timestamp": datetime.now().isoformat()
                    }
        except Exception as e:
            print(f"섹터 분석 오류: {e}")

        return {"sector": sector, "error": True}

    def get_hot_themes(self) -> dict:
        """오늘의 핫 테마"""
        themes = ['반도체', '2차전지', 'AI', '로봇', '바이오', '방산', '조선', '원전']
        theme_news = {}

        for theme in themes:
            news = self.fetch_google_news(f"{theme} 주식 테마", 3)
            theme_news[theme] = [n['title'] for n in news]

        prompt = f"""오늘 한국 증시의 핫 테마를 분석하세요.

=== 테마별 뉴스 ===
{json.dumps(theme_news, ensure_ascii=False, indent=2)}

다음 형식으로 분석:

## 🔥 오늘의 TOP 3 테마
1. (테마명) - 이유
2. (테마명) - 이유
3. (테마명) - 이유

## 📈 급등 예상 테마
(내일/다음주 급등 가능성 높은 테마)

## 📉 주의 테마
(과열 또는 하락 예상 테마)

## 💡 스윙 트레이딩 전략
(단기 매매 전략)
"""

        try:
            resp = requests.post(
                HAIKU_URL,
                json={
                    "model": "sonnet",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500
                },
                timeout=120
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "themes": theme_news,
                    "analysis": data["content"][0].get("text", ""),
                    "timestamp": datetime.now().isoformat()
                }
        except:
            pass

        return {"themes": theme_news}

    def morning_report(self) -> str:
        """아침 종합 리포트"""
        import sys
        sys.path.insert(0, '/home/kim/dooray-claude-bot')

        # 시장 센티먼트
        sentiment = self.get_market_sentiment()

        # 핫 테마
        themes = self.get_hot_themes()

        # 주요 종목 분석
        from kiwoom_trader import KiwoomTrader
        trader = KiwoomTrader(use_mock=False, test_mode=True)

        stocks = [
            ('005930', '삼성전자'),
            ('000660', 'SK하이닉스'),
            ('035720', '카카오'),
            ('005380', '현대차'),
        ]

        stock_analyses = []
        for code, name in stocks:
            price = trader.get_stock_price(code)
            analysis = self.analyze_stock(code, name, price)
            stock_analyses.append(analysis)

        # 종합 리포트 생성
        report = f"""
# 📊 {datetime.now().strftime('%Y-%m-%d')} 아침 시장 리포트

## 🌐 시장 현황
- KOSPI: {sentiment.get('kospi', 'N/A')}
- KOSDAQ: {sentiment.get('kosdaq', 'N/A')}

---

{themes.get('analysis', '테마 분석 없음')}

---

## 📈 주요 종목 분석

"""
        for sa in stock_analyses:
            report += f"""
### {sa['name']} ({sa['code']})
{sa.get('analysis', '분석 없음')[:1500]}

---
"""

        return report


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--stock', help='종목 분석 (코드,이름)')
    parser.add_argument('--sector', help='섹터 분석')
    parser.add_argument('--themes', action='store_true', help='핫 테마')
    parser.add_argument('--report', action='store_true', help='종합 리포트')
    parser.add_argument('--send', action='store_true', help='텔레그램 전송')
    args = parser.parse_args()

    analyzer = ProAnalyzer()

    result = None

    if args.stock:
        code, name = args.stock.split(',')
        import sys
        sys.path.insert(0, '/home/kim/dooray-claude-bot')
        from kiwoom_trader import KiwoomTrader
        trader = KiwoomTrader(use_mock=False, test_mode=True)
        price = trader.get_stock_price(code)
        result = analyzer.analyze_stock(code, name, price)
        print(result['analysis'])

    elif args.sector:
        result = analyzer.analyze_sector(args.sector)
        print(result.get('analysis', '분석 실패'))

    elif args.themes:
        result = analyzer.get_hot_themes()
        print(result.get('analysis', '분석 실패'))

    elif args.report:
        result = analyzer.morning_report()
        print(result)

    if args.send and result:
        text = result if isinstance(result, str) else result.get('analysis', '')
        # 텔레그램 전송
        TELEGRAM_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"
        TELEGRAM_CHAT_ID = "8341524797"

        # 긴 메시지 분할
        max_len = 4000
        parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
        for part in parts:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "Markdown"}
            )
        print("\n✅ 텔레그램 전송 완료")


if __name__ == "__main__":
    main()
