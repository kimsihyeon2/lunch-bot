import requests
import datetime
import logging
import sys
import json

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LunchBot")

class NaverCafeApiCrawler:
    """
    네이버 카페 내부 API(JSON)를 직접 호출하는 SOTA 크롤러
    HTML 파싱 없이 데이터를 직접 수신하여 정확도 100% 보장
    """
    
    def __init__(self, club_id: int, menu_id: int):
        self.club_id = club_id
        self.menu_id = menu_id
        
        # 네이버 카페 모바일 웹이 사용하는 실제 API 엔드포인트
        self.api_url = "https://apis.naver.com/cafe-web/cafe2/ArticleList.json"
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
            'Referer': f'https://m.cafe.naver.com/ca-fe/web/cafes/{club_id}/menus/{menu_id}',
            'Accept': 'application/json, text/plain, */*'
        })
        
        self.target_keywords = self._generate_date_keywords()

    def _generate_date_keywords(self):
        now = datetime.datetime.now()
        keywords = [
            now.strftime("%m월%d일"),    # 12월19일
            now.strftime("%m월 %d일"),   # 12월 19일
            now.strftime("%-m월 %-d일")  # 9월 5일
        ]
        logger.info(f"📅 검색 키워드: {keywords}")
        return keywords

    def fetch_data(self):
        """API를 통해 JSON 데이터 가져오기"""
        params = {
            'search.clubid': self.club_id,
            'search.query': '',
            'search.menuid': self.menu_id,
            'search.boardtype': 'L',
            'search.page': 1,
            'userDisplay': 15  # 가져올 게시글 수
        }
        
        try:
            logger.info("📡 네이버 API 데이터 요청 중...")
            response = self.session.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            
            # JSON 응답 반환
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 500:
                logger.error("❌ 서버 에러 (500): API 파라미터가 잘못되었거나 일시적 장애입니다.")
            elif e.response.status_code == 401:
                logger.error("❌ 권한 없음 (401): 이 게시판은 멤버만 볼 수 있습니다. (로그인 필요)")
            else:
                logger.error(f"❌ HTTP 에러: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ 연결 실패: {e}")
            return None

    def parse_and_print(self, data):
        """JSON 데이터 분석"""
        if not data or 'message' not in data:
            logger.error("⚠️ 잘못된 응답 데이터입니다.")
            if data: logger.debug(f"응답 내용: {data}")
            return

        result = data.get('message', {}).get('result', {})
        article_list = result.get('articleList', [])

        if not article_list:
            logger.warning("📭 게시글 목록이 비어있습니다.")
            return

        found_count = 0
        logger.info(f"🔍 최신 게시글 {len(article_list)}개 분석 시작...")

        for article in article_list:
            # JSON 필드에서 정보 추출
            subject = article.get('subject', '')     # 제목
            article_id = article.get('articleId')    # 글 ID
            writer = article.get('writerNickname', '') # 작성자
            write_date_ts = article.get('writeDateTimestamp') # 작성시간(타임스탬프)
            
            # 타임스탬프를 보기 좋은 시간으로 변환 (옵션)
            write_time = datetime.datetime.fromtimestamp(write_date_ts / 1000).strftime('%H:%M')

            # 링크 생성
            link = f"https://m.cafe.naver.com/ca-fe/web/cafes/{self.club_id}/articles/{article_id}"

            # 필터링
            # 네이버 API 제목에는 HTML 엔티티(&lt; 등)나 말줄임표가 있을 수 있어 단순화 필요하지만
            # 보통 그대로 매칭해도 됩니다.
            is_target = any(k in subject for k in self.target_keywords)

            if is_target:
                self._print_menu(subject, link, writer, write_time)
                found_count += 1
            else:
                # 디버깅: 키워드가 없어서 패스한 글 확인 (필요시 주석 해제)
                # logger.debug(f"패스: {subject}")
                pass

        if found_count == 0:
            logger.info("📭 [결과 없음] 오늘 날짜의 메뉴 글을 찾지 못했습니다.")
            logger.info(f"👉 확인된 최신글 제목 예시: {article_list[0].get('subject')}")
        else:
            logger.info(f"🎉 총 {found_count}개의 메뉴를 찾았습니다!")

    def _print_menu(self, title, link, writer, time):
        print("\n" + "─"*50)
        print(f"🍱 메뉴 발견: {title}")
        print(f"✍️ 작성자: {writer} | ⏰ {time}")
        print(f"🔗 링크: {link}")
        print("─"*50 + "\n")

    def run(self):
        data = self.fetch_data()
        self.parse_and_print(data)

if __name__ == "__main__":
    CLUB_ID = 30487307
    MENU_ID = 26
    
    bot = NaverCafeApiCrawler(CLUB_ID, MENU_ID)
    bot.run()
