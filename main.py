import requests
import datetime
import logging
import sys
import json
import os
import re
from datetime import timedelta, timezone

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("LunchBot")


class NaverCafeApiCrawler:
    """
    네이버 카페 점심 메뉴 크롤러 (GitHub Actions 호환)
    - UTC 서버에서도 KST 기준으로 날짜 검색
    - 슬랙 웹훅으로 메뉴 발송
    """
    
    def __init__(self, club_id: int, menu_id: int):
        self.club_id = club_id
        self.menu_id = menu_id
        
        # 슬랙 웹훅 URL 확인
        self.slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL', '')
        if not self.slack_webhook_url:
            logger.warning("⚠️ 경고: SLACK_WEBHOOK_URL 환경변수가 없습니다! 슬랙 메시지가 발송되지 않습니다.")

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        })
        
        self.target_keywords = self._generate_date_keywords()

    def _get_kst_now(self):
        """서버 시간(UTC)과 상관없이 무조건 한국 시간(KST) 구하기"""
        # UTC 시간 가져오기
        utc_now = datetime.datetime.now(timezone.utc)
        # 한국 시간(KST) = UTC + 9시간
        kst_timezone = timezone(timedelta(hours=9))
        return utc_now.astimezone(kst_timezone)

    def _generate_date_keywords(self):
        """KST 기준으로 오늘 날짜 키워드 생성"""
        now = self._get_kst_now()
        
        logger.info(f"🕒 현재 기준 시간(KST): {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        keywords = [
            now.strftime("%m월%d일"),      # 12월19일
            now.strftime("%m월 %d일"),     # 12월 19일
            f"{now.month}월 {now.day}일",  # 12월 19일 (포맷 보장)
            f"{now.month}월{now.day}일",   # 12월19일
        ]
        
        # 중복 제거
        keywords = list(dict.fromkeys(keywords))
        logger.info(f"📅 검색 키워드: {keywords}")
        return keywords

    def clean_html(self, text):
        """HTML 태그 및 엔티티 제거"""
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&quot;', '"').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&nbsp;', ' ')
        return text.strip()

    def fetch_article_list(self):
        """게시글 목록 API 호출"""
        api_url = "https://apis.naver.com/cafe-web/cafe-mobile/CafeMobileWebArticleSearchListV3"
        params = {
            'cafeId': self.club_id,
            'menuId': self.menu_id,
            'page': 1,
            'perPage': 20,
            'adUnit': 'MW_CAFE_BOARD',
            'query': '',
        }
        
        try:
            logger.info("📡 게시글 목록 API 호출 중...")
            response = self.session.get(api_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get('message', {}).get('result', {}).get('articleList', [])
        except Exception as e:
            logger.error(f"❌ 목록 API 실패: {e}")
        return []

    def fetch_article_detail(self, article_id):
        """개별 게시글 상세 API 호출"""
        api_url = f"https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{self.club_id}/articles/{article_id}"
        try:
            response = self.session.get(api_url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"❌ 상세 API 실패: {e}")
        return None

    def extract_images_from_content(self, content_html):
        """HTML 본문에서 이미지 URL 추출"""
        if not content_html:
            return []
        
        # 고화질 원본(postfiles) 위주로 추출
        patterns = [
            r'src="(https?://postfiles\.pstatic\.net/[^"]+)"',
            r'src="(https?://cafeptthumb-phinf\.pstatic\.net/[^"]+)"'
        ]
        images = []
        for pattern in patterns:
            images.extend(re.findall(pattern, content_html))
        
        # 쿼리 파라미터 제거 및 중복 제거
        clean_images = []
        seen = set()
        for img in images:
            img_clean = img.split('?')[0]
            if img_clean not in seen:
                seen.add(img_clean)
                clean_images.append(img_clean)
        return clean_images

    def extract_text_menu(self, content_html):
        """HTML 본문에서 텍스트 메뉴 추출"""
        if not content_html:
            return ""
        text = re.sub(r'<br\s*/?>', '\n', content_html, flags=re.IGNORECASE)
        text = re.sub(r'</?p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = self.clean_html(text)
        return '\n'.join([line.strip() for line in text.split('\n') if line.strip()])

    def send_to_slack(self, menus):
        """슬랙으로 메뉴 발송"""
        if not self.slack_webhook_url:
            logger.warning("⚠️ 슬랙 웹훅 URL이 없어 발송을 건너뜁니다.")
            return False
        
        # 헤더: KST 시간 표시
        today_str = self._get_kst_now().strftime('%Y년 %m월 %d일 (%a)')
        
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🍱 오늘의 점심 메뉴 ({len(menus)}곳)", "emoji": True}
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"📅 {today_str} | 판교 테크노밸리"}]
            },
            {"type": "divider"}
        ]
        
        for menu in menus:
            # 텍스트 메뉴 미리보기 (최대 300자)
            text_preview = menu['text_menu'][:300] + ("..." if len(menu['text_menu']) > 300 else "")
            if not text_preview:
                text_preview = "(이미지 참고)"

            section = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🏪 <{menu['link']}|{menu['title']}>*\n\n{text_preview}"
                }
            }
            
            # 슬랙 썸네일 추가 (네이버 차단 대비: 일단 시도)
            if menu['images']:
                section["accessory"] = {
                    "type": "image",
                    "image_url": menu['images'][0],
                    "alt_text": "점심 메뉴 이미지"
                }
            
            blocks.append(section)
            blocks.append({"type": "divider"})
        
        payload = {"blocks": blocks, "text": f"🍱 오늘 점심 메뉴 {len(menus)}개 도착"}
        
        try:
            res = requests.post(self.slack_webhook_url, json=payload, timeout=10)
            if res.status_code == 200:
                logger.info("✅ 슬랙 발송 완료")
                return True
            else:
                logger.error(f"❌ 슬랙 발송 실패: {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"❌ 슬랙 에러: {e}")
            return False

    def run(self):
        """메인 실행"""
        logger.info("🚀 크롤러 시작")
        
        articles = self.fetch_article_list()
        if not articles:
            logger.error("❌ 게시글 목록 없음")
            return

        logger.info(f"📋 총 {len(articles)}개 게시글 발견")
        
        today_menus = []
        for article in articles:
            subject = self.clean_html(article.get('subject', ''))
            if not any(k in subject for k in self.target_keywords):
                continue
                
            logger.info(f"✅ 메뉴 발견: {subject}")
            article_id = article.get('articleId')
            
            detail = self.fetch_article_detail(article_id)
            if not detail:
                continue
            
            content = detail.get('result', {}).get('article', {}).get('contentHtml', '')
            
            menu_info = {
                'title': subject,
                'link': f"https://m.cafe.naver.com/ca-fe/web/cafes/{self.club_id}/articles/{article_id}",
                'images': self.extract_images_from_content(content),
                'text_menu': self.extract_text_menu(content)
            }
            today_menus.append(menu_info)

        if today_menus:
            logger.info(f"🎉 총 {len(today_menus)}개 메뉴 발견!")
            self.send_to_slack(today_menus)
        else:
            logger.info("📭 오늘 메뉴 없음")
            # 메뉴가 없어도 슬랙에 알림 (옵션)
            if self.slack_webhook_url:
                self._send_no_menu_notification()

    def _send_no_menu_notification(self):
        """메뉴가 없을 때 슬랙 알림"""
        today_str = self._get_kst_now().strftime('%Y년 %m월 %d일 (%a)')
        payload = {
            "text": f"📭 {today_str} - 아직 오늘의 점심 메뉴가 올라오지 않았습니다."
        }
        try:
            requests.post(self.slack_webhook_url, json=payload, timeout=10)
        except:
            pass


if __name__ == "__main__":
    bot = NaverCafeApiCrawler(30487307, 26)
    bot.run()
