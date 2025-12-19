import requests
from bs4 import BeautifulSoup
import datetime
import logging
import sys
import time

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LunchCrawler")

class NaverCafeMobileCrawler:
    """
    네이버 카페 모바일 웹(m.cafe.naver.com) 크롤러
    PC 버전보다 구조가 단순하고 차단 확률이 낮음
    """
    
    def __init__(self, club_id: int, menu_id: int):
        self.club_id = club_id
        self.menu_id = menu_id
        self.session = requests.Session()
        
        # 모바일 환경처럼 위장
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': f'https://m.cafe.naver.com/SectionArticleList.nhn?cafeId={club_id}&menuId={menu_id}',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        })
        
        self.target_keywords = self._generate_date_keywords()

    def _generate_date_keywords(self):
        now = datetime.datetime.now()
        # 모바일에서도 제목에 날짜가 들어가는 패턴은 동일함
        keywords = [
            now.strftime("%m월%d일"),    # 12월19일
            now.strftime("%m월 %d일"),   # 12월 19일
            now.strftime("%-m월 %-d일"), # 9월 5일 (Mac/Linux)
            now.strftime("%-m월%-d일")   # 9월5일 (Mac/Linux)
        ]
        if sys.platform == 'win32':
             # 윈도우에서는 %-m 지원 안 함, 예외 처리 생략(위의 포맷으로 충분)
             pass
             
        logger.info(f"📅 검색 키워드: {keywords}")
        return keywords

    def fetch_list(self):
        # 모바일 전용 URL
        url = "https://m.cafe.naver.com/SectionArticleList.nhn"
        params = {
            'cafeId': self.club_id,
            'menuId': self.menu_id
        }
        
        try:
            logger.info("📡 네이버 카페(모바일) 접속 중...")
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"❌ 접속 실패: {e}")
            return None

    def parse(self, html):
        if not html: return

        soup = BeautifulSoup(html, 'html.parser')
        
        # 디버깅: 접속한 페이지 제목 확인 (로그인 페이지로 튕겼는지 확인용)
        page_title = soup.title.get_text(strip=True) if soup.title else "제목없음"
        logger.info(f"📄 접속 페이지 제목: {page_title}")

        # 모바일 리스트 선택자: ul.list_area > li
        articles = soup.select('ul.list_area > li')
        
        if not articles:
            # 혹시 모바일 레이아웃이 다른 경우 대비 (카드형 등)
            articles = soup.select('div.list_area > div.board_box') 
            
        if not articles:
            logger.warning("⚠️ 게시글 목록을 찾을 수 없습니다.")
            # HTML 구조가 바뀌었거나 차단되었을 때 HTML 일부 출력
            logger.debug(f"DEBUG HTML: {soup.prettify()[:500]}")
            return

        found_count = 0
        logger.info(f"🔍 최신 글 {len(articles)}개 분석 시작...")

        for item in articles:
            # 제목 태그 찾기 (모바일 구조 기준)
            title_tag = item.select_one('strong.tit') or item.select_one('div.tit')
            
            if not title_tag:
                continue
                
            title = title_tag.get_text(strip=True)
            
            # 링크 찾기
            link_tag = item.select_one('a.txt_area') or item.select_one('a')
            link = "https://m.cafe.naver.com" + link_tag['href'] if link_tag else "링크없음"

            # 작성자/작성일 등 추가 정보 (옵션)
            date_tag = item.select_one('span.time')
            date_text = date_tag.get_text(strip=True) if date_tag else ""

            # 필터링
            is_target = any(k in title for k in self.target_keywords)
            
            if is_target:
                self._print_menu(title, link, date_text)
                found_count += 1

        if found_count == 0:
            logger.info("📭 오늘 날짜 키워드가 포함된 게시글이 없습니다.")
        else:
            logger.info(f"🎉 총 {found_count}개의 메뉴 발견!")

    def _print_menu(self, title, link, date):
        print("\n" + "─"*50)
        print(f"🍱 메뉴 발견: {title}")
        print(f"⏰ 작성시간: {date}")
        print(f"🔗 바로가기: {link}")
        print("─"*50 + "\n")

    def run(self):
        html = self.fetch_list()
        self.parse(html)

if __name__ == "__main__":
    # 판교 테크노밸리 구내식당 정보 공유 카페
    CLUB_ID = 30487307
    MENU_ID = 26
    
    bot = NaverCafeMobileCrawler(CLUB_ID, MENU_ID)
    bot.run()
