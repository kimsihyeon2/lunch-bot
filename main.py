import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 1. 설정값
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

# 모바일 페이지 주소 (봇이 읽기 훨씬 쉽습니다)
# 판교 직장인 탐구생활 (ID: 30487307) / 메뉴판 (ID: 26)
MOBILE_URL = "https://m.cafe.naver.com/SectionArticleList.nhn?cafeId=30487307&menuId=26"

# 찾고 싶은 식당 이름들
RESTAURANTS = ["송원식당", "해담가", "정겨운맛풍경", "런치포유"]

def get_menu_message():
    now = datetime.now()
    # 날짜 필터 (예: "12월19일") - 공백 제거하고 비교함
    date_filter = f"{now.month}월{now.day}일"
    display_date = f"{now.month}월 {now.day}일"

    # 봇 위장 (차단 방지)
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    }

    print(f"🔍 [모바일 모드] 크롤링 시작: {display_date} 메뉴 찾는 중...")
    
    try:
        res = requests.get(MOBILE_URL, headers=headers)
        # 한글 깨짐 방지
        res.encoding = 'utf-8' 
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        return {"text": f"❌ 접속 오류: {str(e)}", "blocks": []}

    # 모바일 카페 글 목록 가져오기
    # (li 태그 안에 글들이 들어있음)
    articles = soup.select("li")
    
    found_menus = {}

    for article in articles:
        # 제목 찾기 (모바일은 strong.tit 또는 div.tit 클래스를 씀)
        title_tag = article.select_one("strong.tit") or article.select_one("div.tit") or article.select_one("h3")
        
        if not title_tag:
            continue

        title = title_tag.text.strip()
        
        # 링크 찾기
        link_tag = article.select_one("a")
        link = "https://m.cafe.naver.com" + link_tag["href"] if link_tag else MOBILE_URL

        # 제목에서 공백을 싹 제거하고 날짜 비교 (12월 19일 vs 12월19일 해결)
        title_clean = title.replace(" ", "").replace("\t", "").replace("\n", "")
        
        # 디버깅용 출력 (Actions 로그에서 확인 가능)
        # print(f"읽은 글: {title_clean}") 

        # 1. 오늘 날짜 확인
        if date_filter in title_clean:
            # 2. 식당 이름 확인
            for rest_name in RESTAURANTS:
                if rest_name in found_menus:
                    continue
                
                if rest_name in title:
                    print(f"✅ 발견! {rest_name} -> {title}")
                    
                    # 본문 긁어오기
                    try:
                        content_res = requests.get(link, headers=headers)
                        content_soup = BeautifulSoup(content_res.text, "html.parser")
                        
                        # 본문 내용 (모바일 뷰 기준)
                        content_div = content_soup.select_one("#postContent") or content_soup.select_one("div.se-main-container")
                        
                        if content_div:
                            menu_text = content_div.get_text("\n").strip()
                            if len(menu_text) > 200:
                                menu_text = menu_text[:200] + "...\n(더보기 클릭)"
                        else:
                            menu_text = "메뉴 내용을 읽을 수 없습니다. (사진 위주 게시글일 수 있음)"
                            
                        found_menus[rest_name] = {
                            "text": menu_text,
                            "link": link
                        }
                    except:
                        found_menus[rest_name] = {"text": "본문 로딩 실패", "link": link}

    # --- 슬랙 메시지 만들기 ---
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🍚 {display_date} 판교 점심 메뉴"}},
        {"type": "divider"}
    ]

    if not found_menus:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "😭 *오늘 메뉴를 못 찾았어요!* \n1. 아직 게시글이 안 올라왔거나\n2. 날짜 형식이 다를 수 있습니다.\n(봇은 '12월19일' 같은 제목을 찾습니다)"}
        })
        blocks.append({
             "type": "section",
             "text": {"type": "mrkdwn", "text": f"👉 <{MOBILE_URL}|게시판 직접 확인하기>"}
        })
    else:
        for name in RESTAURANTS:
            if name in found_menus:
                info = found_menus[name]
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{name}*\n{info['text']}"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "사진 보기"},
                        "url": info['link']
                    }
                })
                blocks.append({"type": "divider"})

    return {"text": "점심 메뉴 도착", "blocks": blocks}

if __name__ == "__main__":
    payload = get_menu_message()
    requests.post(SLACK_WEBHOOK_URL, json=payload)
