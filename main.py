import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# --- 설정 ---
# 판교 직장인 탐구생활 (PC 버전 글목록 원본 주소)
TARGET_URL = "https://cafe.naver.com/ArticleList.nhn?search.clubid=30487307&search.menuid=26&search.boardtype=L"
RESTAURANTS = ["송원식당", "해담가", "정겨운맛풍경", "런치포유"]

def test_crawling():
    # 한국 시간 설정
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    
    # 봇이 찾을 날짜 문자열 (공백 제거 버전)
    date_filter = f"{now.month}월{now.day}일"
    print(f"--- 🕵️‍♀️ 테스트 시작 ---")
    print(f"기준 날짜: {date_filter}")
    print(f"접속 주소: {TARGET_URL}\n")

    # 봇 차단 방지 헤더
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        res = requests.get(TARGET_URL, headers=headers)
        res.encoding = 'cp949' # 네이버 카페 PC버전은 euc-kr/cp949 인코딩 사용
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"❌ 사이트 접속 자체를 실패했습니다: {e}")
        return

    # 게시글 행(tr) 가져오기
    articles = soup.select("div.article-board table tbody tr")
    print(f"읽어온 게시글 수: {len(articles)}개\n")

    found_count = 0

    print("--- 🔍 최신 글 5개 제목 확인 (봇이 보고 있는 것) ---")
    for i, article in enumerate(articles):
        # 제목 태그
        title_tag = article.select_one("a.article")
        if not title_tag: 
            continue
            
        raw_title = title_tag.text.strip()
        # 제목에서 공백 제거 (비교용)
        clean_title = raw_title.replace(" ", "").replace("\t", "").replace("\n", "")
        
        # 최신 5개만 로그에 출력해서 확인
        if i < 5:
            print(f"[{i+1}] {raw_title}")

        # 날짜 매칭 확인
        if date_filter in clean_title:
            for rest_name in RESTAURANTS:
                if rest_name in raw_title:
                    print(f"   🎉 [성공] '{rest_name}' 메뉴 발견함!")
                    found_count += 1
    
    print("\n------------------------------------------------")
    if found_count > 0:
        print(f"✅ 결과: 총 {found_count}개의 식당 메뉴를 찾았습니다! (크롤링 정상)")
        print("이제 슬랙 연결 코드로 바꿔도 됩니다.")
    else:
        print(f"❌ 결과: 오늘({date_filter}) 날짜의 메뉴를 하나도 못 찾았습니다.")
        print("이유: 아직 글이 안 올라왔거나, 날짜 형식이 다를 수 있습니다.")

if __name__ == "__main__":
    test_crawling()
