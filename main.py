import requests
from bs4 import BeautifulSoup
import datetime
import logging
import sys
import re
from typing import List, Optional

# --- 1. 로깅 설정 (SOTA: print 대신 logging 사용) ---
# 로그 포맷: [시간] [로그레벨] 메시지 -> 가독성 확보
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("LunchCrawler")

class NaverCafeCrawler:
    """
    네이버 카페 게시글 크롤러 (Session 활용 및 예외 처리 강화)
    """
    
    # 네이버 봇 차단 방지를 위한 헤더
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://cafe.naver.com/',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    def __init__(self, club_id: int, menu_id: int):
        self.club_id = club_id
        self.menu_id = menu_id
        # SOTA: 매 요청마다 연결을 맺지 않고 Session을 재사용하여 성능 향상
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        
        # 검색할 날짜 키워드 생성 (오늘 날짜)
        self.target_keywords = self._generate_date_keywords()

    def _generate_date_keywords(self) -> List[str]:
        """오늘 날짜를 기반으로 검색할 다양한 포맷의 키워드 생성"""
        now = datetime.datetime.now()
        keywords = [
            now.strftime("%m월%d일"),    # 예: 12월19일
            now.strftime("%m월 %d일"),   # 예: 12월 19일
            now.strftime("%-m월 %-d일")  # 예: 9월 5일 (윈도우에서는 # 대신 - 사용 주의)
        ]
        # 리눅스/유닉스 환경 호환성을 위한 처리
        if sys.platform != 'win32':
             keywords.append(now.strftime("%-m월%-d일"))
             
        logger.info(f"📅 오늘 검색 대상 날짜 키워드: {keywords}")
        return keywords

    def fetch_article_list(self) -> str:
        """게시글 목록 HTML 가져오기"""
        url = "https://cafe.naver.com/ArticleList.nhn"
        params = {
            'search.clubid': self.club_id,
            'search.menuid': self.menu_id,
            'search.boardtype': 'L', # 리스트형 게시판
            'userDisplay': 50        # 한 번에 많이 가져오기
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # 인코딩 자동 감지 및 설정 (euc-kr, cp949 대응)
            response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8'
            
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 네트워크 요청 실패: {e}")
            raise

    def parse_and_find_menus(self, html: str):
        """HTML 파싱 및 메뉴 찾기"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # ArticleList.nhn의 표준 구조: div.article-board > table > tbody > tr
        # 유연성을 위해 a.article 태그를 직접 찾습니다.
        articles = soup.select('a.article')
        
        if not articles:
            logger.warning("⚠️ 게시글 목록을 찾을 수 없습니다. (HTML 구조 변경 또는 봇 차단 의심)")
            # 디버깅을 위해 HTML 일부 로깅 (필요시 주석 해제)
            # logger.debug(soup.prettify()[:500])
            return

        found_count = 0
        logger.info(f"🔍 최신 게시글 {len(articles)}개를 스캔합니다...")

        for article in articles:
            title = article.get_text(strip=True)
            link = "https://cafe.naver.com" + article.get('href')
            
            # 제목에 날짜 키워드가 포함되어 있는지 확인
            if any(keyword in title for keyword in self.target_keywords):
                self._log_success(title, link)
                found_count += 1
            else:
                # 디버깅: 오늘 날짜가 아니더라도 어떤 글을 읽고 있는지 확인하고 싶다면 아래 주석 해제
                # logger.debug(f"PASS (날짜불일치): {title}")
                pass

        if found_count == 0:
            logger.warning("❌ [결과 없음] 오늘 날짜의 메뉴 게시글을 찾지 못했습니다.")
            logger.info("👉 팁: 게시글 제목에 '12월 19일'과 같은 날짜가 정확히 포함되어 있는지 확인하세요.")
        else:
            logger.info(f"🎉 총 {found_count}개의 오늘 점심 메뉴를 찾았습니다.")

    def _log_success(self, title: str, link: str):
        """찾은 결과를 예쁘게 출력"""
        print("\n" + "="*60)
        print(f"🍱 [발견] {title}")
        print(f"🔗 링크: {link}")
        print("="*60 + "\n")

    def run(self):
        """전체 로직 실행"""
        logger.info("🚀 점심 메뉴 크롤러 시작")
        try:
            html = self.fetch_article_list()
            self.parse_and_find_menus(html)
        except Exception as e:
            logger.critical(f"🔥 치명적인 오류 발생: {e}")
        finally:
            logger.info("👋 크롤러 종료")

# --- 실행부 (Main) ---
if __name__ == "__main__":
    # 사용자 설정값 (기존 URL 파라미터 기반)
    CLUB_ID = 30487307
    MENU_ID = 26
    
    bot = NaverCafeCrawler(club_id=CLUB_ID, menu_id=MENU_ID)
    bot.run()
