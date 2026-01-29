#!/usr/bin/env python3
"""
두레이 + Git 연동 시스템
- Git 커밋/푸시 → 두레이 알림
- GitHub Webhook → 두레이 알림
- PR, Issue 알림
"""

import os
import json
import subprocess
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# 두레이 Incoming Webhook URL (환경변수 또는 직접 설정)
DOORAY_WEBHOOK_URL = os.environ.get("DOORAY_WEBHOOK_URL", "")

# 설정 파일에서 읽기
CONFIG_FILE = "/home/kim/dooray-claude-bot/dooray_config.json"


def load_config():
    """설정 로드"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config):
    """설정 저장"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_webhook_url():
    """웹훅 URL 가져오기"""
    if DOORAY_WEBHOOK_URL:
        return DOORAY_WEBHOOK_URL
    config = load_config()
    return config.get("dooray_webhook_url", "")


def send_to_dooray(message: str, title: str = None, color: str = "blue"):
    """두레이로 메시지 전송"""
    webhook_url = get_webhook_url()

    if not webhook_url:
        print("❌ 두레이 웹훅 URL이 설정되지 않았습니다.")
        print("   설정: POST /config {\"dooray_webhook_url\": \"YOUR_URL\"}")
        return False

    payload = {
        "botName": "Git Bot 🔧",
        "text": message,
    }

    if title:
        payload["attachments"] = [{
            "title": title,
            "text": message,
            "color": color
        }]
        payload["text"] = title

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        print(f"[두레이] 전송 완료: {resp.status_code}")
        return resp.status_code == 200
    except Exception as e:
        print(f"[두레이] 전송 실패: {e}")
        return False


# ============================================================
# GitHub Webhook 처리
# ============================================================

@app.route("/github", methods=["POST"])
def github_webhook():
    """GitHub Webhook 수신"""
    event = request.headers.get("X-GitHub-Event", "unknown")
    data = request.json or {}

    print(f"[GitHub] 이벤트: {event}")

    if event == "push":
        return handle_push(data)
    elif event == "pull_request":
        return handle_pr(data)
    elif event == "issues":
        return handle_issue(data)
    elif event == "issue_comment":
        return handle_comment(data)
    elif event == "create":
        return handle_create(data)
    elif event == "delete":
        return handle_delete(data)
    else:
        print(f"[GitHub] 미처리 이벤트: {event}")
        return jsonify({"status": "ignored", "event": event})


def handle_push(data):
    """Push 이벤트 처리"""
    repo = data.get("repository", {}).get("full_name", "unknown")
    branch = data.get("ref", "").replace("refs/heads/", "")
    pusher = data.get("pusher", {}).get("name", "unknown")
    commits = data.get("commits", [])

    if not commits:
        return jsonify({"status": "no commits"})

    # 커밋 메시지 정리
    commit_list = []
    for c in commits[:5]:  # 최대 5개
        sha = c.get("id", "")[:7]
        msg = c.get("message", "").split("\n")[0][:50]
        author = c.get("author", {}).get("name", "")
        commit_list.append(f"• `{sha}` {msg} ({author})")

    if len(commits) > 5:
        commit_list.append(f"... 외 {len(commits) - 5}개 커밋")

    message = f"""🚀 **Push** to `{repo}`

**Branch:** `{branch}`
**By:** {pusher}
**Commits ({len(commits)}):**
{chr(10).join(commit_list)}"""

    send_to_dooray(message, f"🚀 Push: {repo}/{branch}", "green")
    return jsonify({"status": "ok", "type": "push"})


def handle_pr(data):
    """Pull Request 이벤트 처리"""
    action = data.get("action", "")
    pr = data.get("pull_request", {})
    repo = data.get("repository", {}).get("full_name", "unknown")

    title = pr.get("title", "")
    number = pr.get("number", 0)
    user = pr.get("user", {}).get("login", "unknown")
    url = pr.get("html_url", "")
    base = pr.get("base", {}).get("ref", "")
    head = pr.get("head", {}).get("ref", "")

    emoji_map = {
        "opened": "🆕",
        "closed": "✅" if pr.get("merged") else "❌",
        "merged": "🎉",
        "reopened": "🔄",
        "review_requested": "👀",
    }
    emoji = emoji_map.get(action, "📋")

    message = f"""{emoji} **PR {action.upper()}** in `{repo}`

**#{number}** {title}
**By:** {user}
**Branch:** `{head}` → `{base}`
**URL:** {url}"""

    color = "green" if action in ["merged", "closed"] else "blue"
    send_to_dooray(message, f"{emoji} PR #{number}: {title[:30]}", color)
    return jsonify({"status": "ok", "type": "pr", "action": action})


def handle_issue(data):
    """Issue 이벤트 처리"""
    action = data.get("action", "")
    issue = data.get("issue", {})
    repo = data.get("repository", {}).get("full_name", "unknown")

    title = issue.get("title", "")
    number = issue.get("number", 0)
    user = issue.get("user", {}).get("login", "unknown")
    url = issue.get("html_url", "")

    emoji_map = {
        "opened": "🐛",
        "closed": "✅",
        "reopened": "🔄",
    }
    emoji = emoji_map.get(action, "📋")

    message = f"""{emoji} **Issue {action.upper()}** in `{repo}`

**#{number}** {title}
**By:** {user}
**URL:** {url}"""

    send_to_dooray(message, f"{emoji} Issue #{number}: {title[:30]}", "yellow")
    return jsonify({"status": "ok", "type": "issue", "action": action})


def handle_comment(data):
    """댓글 이벤트 처리"""
    action = data.get("action", "")
    if action != "created":
        return jsonify({"status": "ignored"})

    comment = data.get("comment", {})
    issue = data.get("issue", {})
    repo = data.get("repository", {}).get("full_name", "unknown")

    user = comment.get("user", {}).get("login", "unknown")
    body = comment.get("body", "")[:200]
    number = issue.get("number", 0)
    title = issue.get("title", "")

    message = f"""💬 **New Comment** in `{repo}`

**#{number}** {title}
**By:** {user}
**Comment:** {body}"""

    send_to_dooray(message, f"💬 Comment on #{number}", "gray")
    return jsonify({"status": "ok", "type": "comment"})


def handle_create(data):
    """브랜치/태그 생성"""
    ref_type = data.get("ref_type", "")
    ref = data.get("ref", "")
    repo = data.get("repository", {}).get("full_name", "unknown")
    sender = data.get("sender", {}).get("login", "unknown")

    emoji = "🌿" if ref_type == "branch" else "🏷️"

    message = f"""{emoji} **{ref_type.upper()} Created** in `{repo}`

**Name:** `{ref}`
**By:** {sender}"""

    send_to_dooray(message, f"{emoji} New {ref_type}: {ref}", "blue")
    return jsonify({"status": "ok", "type": "create"})


def handle_delete(data):
    """브랜치/태그 삭제"""
    ref_type = data.get("ref_type", "")
    ref = data.get("ref", "")
    repo = data.get("repository", {}).get("full_name", "unknown")

    message = f"""🗑️ **{ref_type.upper()} Deleted** in `{repo}`

**Name:** `{ref}`"""

    send_to_dooray(message, f"🗑️ Deleted {ref_type}: {ref}", "red")
    return jsonify({"status": "ok", "type": "delete"})


# ============================================================
# 로컬 Git Hook
# ============================================================

@app.route("/local-commit", methods=["POST"])
def local_commit():
    """로컬 Git 커밋 알림"""
    data = request.json or {}

    repo = data.get("repo", "local")
    branch = data.get("branch", "unknown")
    commit_hash = data.get("hash", "")[:7]
    message = data.get("message", "")
    author = data.get("author", "unknown")

    msg = f"""📝 **Local Commit**

**Repo:** `{repo}`
**Branch:** `{branch}`
**Commit:** `{commit_hash}`
**Message:** {message}
**Author:** {author}"""

    send_to_dooray(msg, f"📝 Commit: {message[:30]}", "green")
    return jsonify({"status": "ok"})


# ============================================================
# 설정 API
# ============================================================

@app.route("/config", methods=["GET", "POST"])
def config():
    """설정 관리"""
    if request.method == "GET":
        cfg = load_config()
        # 웹훅 URL은 일부만 표시
        if cfg.get("dooray_webhook_url"):
            url = cfg["dooray_webhook_url"]
            cfg["dooray_webhook_url"] = url[:30] + "..." if len(url) > 30 else url
        return jsonify(cfg)

    else:  # POST
        data = request.json or {}
        cfg = load_config()
        cfg.update(data)
        save_config(cfg)
        return jsonify({"status": "ok", "message": "설정 저장됨"})


@app.route("/test", methods=["POST"])
def test():
    """테스트 메시지 전송"""
    send_to_dooray(
        "🔔 **Git 연동 테스트**\n\n두레이 + Git 연동이 정상 작동합니다!",
        "✅ 연동 테스트 성공",
        "green"
    )
    return jsonify({"status": "ok", "message": "테스트 메시지 전송됨"})


@app.route("/health", methods=["GET"])
def health():
    return "OK"


@app.route("/", methods=["GET"])
def home():
    return """
    <h1>🔧 두레이 + Git 연동</h1>
    <h2>API 엔드포인트:</h2>
    <ul>
        <li><b>POST /github</b> - GitHub Webhook</li>
        <li><b>POST /local-commit</b> - 로컬 커밋 알림</li>
        <li><b>GET/POST /config</b> - 설정 관리</li>
        <li><b>POST /test</b> - 테스트 메시지</li>
    </ul>
    <h2>설정:</h2>
    <pre>
    POST /config
    {"dooray_webhook_url": "https://hook.dooray.com/..."}
    </pre>
    """


if __name__ == "__main__":
    print("=" * 50)
    print("🔧 두레이 + Git 연동 서버")
    print("=" * 50)
    print("엔드포인트:")
    print("  POST /github      - GitHub Webhook")
    print("  POST /local-commit - 로컬 커밋")
    print("  POST /config      - 설정")
    print("  POST /test        - 테스트")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5001, threaded=True)
