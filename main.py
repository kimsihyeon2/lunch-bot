import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 1. 설정값 (환경변수에서 가져옴)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

# 타겟 카페 정보 (판교 직장인 탐구생활 - 오늘 점심 메뉴 게시판)
CAFE_ID = "30487307"
MENU_ID = "26"

# 찾고 싶은 식당 이름들
RESTAURANTS = ["송원식당", "해담가", "정겨운맛풍경", "런치포유"]

def get_menu_message():
    # 오늘 날짜 구하기
    now = datetime.now()
    # 게시글 제목 비교용 (공백 없이, 예: "12월19일")
    date_filter = f"{now.month}월{now.day}일"
    # 출력용 날짜
    display_date = f"{now.month}월 {now.day}일"

    # 네이버 카페 게시글 목록 주소 (PC 버전 리스트 사용)
    list_url = f"https://cafe.naver.com/ArticleList.nhn?search.clubid={CAFE_ID}&search.menuid={MENU_ID}&search.boardtype=L"
    
    # 봇이 아니라 사람인 척 위장하기 (차단 방지)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"
    }

    print(f"🔍 크롤링 시작: {display_date} 메뉴를 찾습니다...")
    res = requests.get(list_url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    # 게시글 목록 가져오기
    articles = soup.select("div.article-board table tbody tr")
    
    found_menus = {} # 찾은 메뉴 저장소

    for article in articles:
        # 제목 태그 찾기
        title_tag = article.select_one("a.article")
        if not title_tag:
            continue
            
        title = title_tag.text.strip()
        link = "https://cafe.naver.com" + title_tag["href"]
        
        # 제목에서 모든 공백 제거 (날짜 비교 정확도를 위해)
        title_clean = title.replace(" ", "")
        
        # 1. 오늘 날짜가 제목에 포함되어 있는지 확인
        if date_filter in title_clean:
            # 2. 우리가 찾는 식당인지 확인
            for rest_name in RESTAURANTS:
                # 이미 찾은 식당이면 패스
                if rest_name in found_menus:
                    continue
                
                # 식당 이름이 제목에 포함되면 당첨!
                if rest_name in title:
                    print(f"✅ 발견: {rest_name} -> {title}")
                    
                    # 게시글 안으로 들어가서 본문 내용 긁기
                    try:
                        content_res = requests.get(link, headers=headers)
                        content_soup = BeautifulSoup(content_res.text, "html.parser")
                        
                        # 본문 찾기 (네이버 에디터 버전에 따라 태그가 다름)
                        content_div = content_soup.select_one("div.se-main-container") # 신규 에디터
                        if not content_div:
                            content_div = content_soup.select_one("div.ContentRenderer") # 구형 에디터
                        
                        if content_div:
                            # 텍스트만 깔끔하게 추출
                            menu_text = content_div.get_text("\n").strip()
                            # 내용이 너무 길면 슬랙 보기에 안 좋으니 자르기
                            if len(menu_text) > 300:
                                menu_text = menu_text[:300] + "...\n(더보기 클릭)"
                        else:
                            menu_text = "본문 내용을 불러오지 못했습니다."
                            
                        found_menus[rest_name] = {
                            "text": menu_text,
                            "link": link
                        }
                    except Exception as e:
                        print(f"❌ 에러 발생 ({rest_name}): {e}")

    # --- 슬랙 메시지 꾸미기 (Block Kit) ---
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🍚 {display_date} 판교 점심 메뉴"
            }
        },
        {"type": "divider"}
    ]

    # 찾은 메뉴가 하나도 없을 때
    if not found_menus:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "😭 아직 카페에 오늘 메뉴가 안 올라왔어요!\n(또는 날짜 형식이 다를 수 있습니다)"}
        })
        blocks.append({
             "type": "section",
             "text": {"type": "mrkdwn", "text": f"*바로가기*\n<{list_url}|게시판 직접 확인하기>"}
        })
    else:
        # 찾은 메뉴들을 하나씩 블록으로 추가
        for name in RESTAURANTS:
            if name in found_menus:
                info = found_menus[name]
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{name}*\n{info['text']}"
                    },
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "사진/전체보기"},
                        "url": info['link']
                    }
                })
                blocks.append({"type": "divider"})

    return {"text": "오늘의 점심 메뉴 도착!", "blocks": blocks}

if __name__ == "__main__":
    payload = get_menu_message()
    # 슬랙으로 전송
    requests.post(SLACK_WEBHOOK_URL, json=payload)
