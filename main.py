import os
import requests
from datetime import datetime

# 2단계에서 저장한 URL을 꺼내옵니다
webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

# 오늘 날짜
today = datetime.now().strftime("%Y년 %m월 %d일")

# 슬랙으로 보낼 메시지 모양 (Block Kit)
data = {
    "text": "점심 메뉴 알림",
    "blocks": [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🍚 {today} 점심 메뉴"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "아직 크롤링 기능은 연결 안 됨!\n이 메시지가 보이면 연결 성공입니다. ✅"
            }
        }
    ]
}

# 전송
response = requests.post(webhook_url, json=data)
print(f"전송 상태: {response.status_code}")
