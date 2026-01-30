# Claude Bot System

MoltBot + Claude CLI 기반 자동화 시스템 (Telegram + Dooray)

## 아키텍처

```
[Telegram/Dooray] → [MoltBot Gateway] → [Claude CLI Proxy] → [Claude CLI]
                          ↓
                   [자율 에이전트]
                   [주식 모니터링]
                   [시스템 헬스체크]
```

## 핵심 컴포넌트

| 파일 | 설명 |
|------|------|
| `claude_api_proxy.py` | Claude CLI를 Anthropic API로 래핑하는 프록시 (포트 8180) |
| `autonomous_agent.py` | 자율 에이전트 (아침인사, 주식알림, 시스템체크, 저녁요약) |
| `health_monitor.py` | 서비스 헬스 모니터링 (5분마다) |
| `moltbot_cron.py` | MoltBot 크론 작업 러너 |
| `telegram_claude_bridge.py` | Telegram-Claude 브릿지 (백업) |

## 주식/투자

| 파일 | 설명 |
|------|------|
| `auto_trading_sim.py` | 자동 매매 시뮬레이션 |
| `early_detector.py` | 급등주 조기 탐지 |
| `daily_investment_reminder.py` | 일일 투자 리마인더 |

## 모델 계층

```
[Haiku]  ← 빠른 응답, 자율 체크 (기본)
   ↓
[Sonnet] ← 일반 대화, 분석
   ↓
[Opus]   ← 복잡한 추론 (명시적 호출)
   ↓
[Codex]  ← 코드 실행
```

## 설치 및 실행

```bash
# 서비스 시작
systemctl --user start moltbot-gateway claude-api-proxy

# 상태 확인
systemctl --user status moltbot-gateway claude-api-proxy

# MoltBot 채널 상태
./moltbot/moltbot.mjs channels status
```

## 설정

### ~/.moltbot/moltbot.json
```json
{
  "agents": {
    "defaults": {
      "model": { "primary": "claude-cli/sonnet" }
    }
  },
  "models": {
    "providers": {
      "claude-cli": {
        "baseUrl": "http://127.0.0.1:8180/v1",
        "apiKey": "dummy",
        "api": "anthropic-messages"
      }
    }
  }
}
```

## 크론

```cron
# 아침 뉴스 (평일 8시)
0 8 * * 1-5 python3 moltbot_cron.py news

# 투자 리마인더 (평일 8시 30분)
30 8 * * 1-5 python3 moltbot_cron.py investment

# 헬스 모니터 (5분마다)
*/5 * * * * python3 health_monitor.py
```

## 채널

- **Telegram**: @dooray_claude_bot
- **Dooray**: Webhook 연동
