import requests
import datetime
import logging
import sys
import json
import os
import re
from pathlib import Path

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('output.log', encoding='utf-8', mode='w')
    ]
)
logger = logging.getLogger("LunchBot")


class NaverCafeApiCrawler:
    """
    네이버 카페 내부 API(JSON)를 직접 호출하는 SOTA 크롤러
    게시글의 이미지와 텍스트 메뉴를 추출하고 슬랙으로 발송합니다.
    """
    
    def __init__(self, club_id: int, menu_id: int):
        self.club_id = club_id
        self.menu_id = menu_id
        
        # 슬랙 웹훅 URL (환경변수에서 가져오기)
        self.slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL', '')
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        })
        
        self.target_keywords = self._generate_date_keywords()

    def _generate_date_keywords(self):
        now = datetime.datetime.now()
        keywords = [
            now.strftime("%m월%d일"),     
            now.strftime("%m월 %d일"),    
            f"{now.month}월 {now.day}일", 
            f"{now.month}월{now.day}일",  
        ]
        # Windows용 포맷 추가 시도
        try:
            keywords.extend([
                now.strftime("%#m월 %#d일"),  
                now.strftime("%#m월%#d일"),   
            ])
        except:
            pass
        keywords = list(dict.fromkeys(keywords))
        logger.info(f"📅 검색 키워드: {keywords}")
        return keywords

    def clean_html(self, text):
        """HTML 태그 및 엔티티 제거"""
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&quot;', '"')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
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
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Referer': f'https://m.cafe.naver.com/ca-fe/web/cafes/{self.club_id}/menus/{self.menu_id}',
        }
        
        try:
            logger.info("📡 게시글 목록 API 호출 중...")
            response = self.session.get(api_url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('message', {}).get('result', {}).get('articleList', [])
        except Exception as e:
            logger.error(f"❌ 게시글 목록 API 실패: {e}")
        return []

    def fetch_article_detail(self, article_id):
        """개별 게시글 본문 API 호출"""
        api_url = f"https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{self.club_id}/articles/{article_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Referer': f'https://m.cafe.naver.com/ca-fe/web/cafes/{self.club_id}/articles/{article_id}',
        }
        
        try:
            response = self.session.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"게시글 상세 API 실패 (article {article_id}): {e}")
        return None

    def extract_images_from_content(self, content_html):
        """HTML 본문에서 이미지 URL 추출"""
        if not content_html:
            return []
        
        patterns = [
            r'src="(https?://[^"]+\.(?:jpg|jpeg|png|gif|webp)[^"]*)"',
            r'(https?://cafeptthumb-phinf\.pstatic\.net/[^\s"<>]+)',
            r'(https?://postfiles\.pstatic\.net/[^\s"<>]+)',
        ]
        
        images = []
        for pattern in patterns:
            matches = re.findall(pattern, content_html, re.IGNORECASE)
            images.extend(matches)
        
        seen = set()
        unique_images = []
        for img in images:
            img = img.split('?')[0]
            if img not in seen and ('cafeptthumb' in img or 'postfiles' in img):
                seen.add(img)
                unique_images.append(img)
        
        return unique_images

    def extract_text_menu(self, content_html):
        """HTML 본문에서 텍스트 메뉴 추출"""
        if not content_html:
            return ""
        
        text = re.sub(r'<br\s*/?>', '\n', content_html, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = self.clean_html(text)
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)

    def get_high_quality_image_url(self, thumbnail_url):
        """썸네일 URL을 고화질 원본 URL로 변환"""
        if not thumbnail_url:
            return None
        return thumbnail_url.split('?')[0]

    def send_to_slack(self, menus):
        """슬랙으로 메뉴 발송"""
        if not self.slack_webhook_url:
            logger.warning("⚠️ SLACK_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
            return False
        
        today = datetime.datetime.now().strftime('%Y년 %m월 %d일 (%a)')
        
        # 슬랙 Block Kit 메시지 구성
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🍱 오늘의 점심 메뉴 ({len(menus)}개 식당)",
                    "emoji": True
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📅 {today}"
                    }
                ]
            },
            {"type": "divider"}
        ]
        
        for menu in menus:
            # 식당 제목
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🏪 {menu['title']}*\n<{menu['link']}|게시글 보기>"
                }
            })
            
            # 이미지가 있는 경우
            if menu.get('images') and len(menu['images']) > 0:
                # 첫 번째 이미지만 표시 (슬랙 제한)
                blocks.append({
                    "type": "image",
                    "image_url": menu['images'][0],
                    "alt_text": menu['title']
                })
                
                if len(menu['images']) > 1:
                    blocks.append({
                        "type": "context",
                        "elements": [{
                            "type": "mrkdwn",
                            "text": f"📸 +{len(menu['images'])-1}개 이미지 더 있음 (게시글에서 확인)"
                        }]
                    })
            
            # 텍스트 메뉴가 있는 경우
            if menu.get('text_menu'):
                # 텍스트가 너무 길면 자르기
                text_preview = menu['text_menu'][:500]
                if len(menu['text_menu']) > 500:
                    text_preview += "\n...(더 보기)"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{text_preview}```"
                    }
                })
            
            blocks.append({"type": "divider"})
        
        # 슬랙 웹훅으로 발송
        payload = {
            "blocks": blocks,
            "text": f"🍱 오늘의 점심 메뉴 ({len(menus)}개 식당)"  # fallback text
        }
        
        try:
            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("✅ 슬랙 메시지 발송 성공!")
                return True
            else:
                logger.error(f"❌ 슬랙 발송 실패: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 슬랙 발송 오류: {e}")
            return False

    def run(self):
        """메인 실행"""
        logger.info("🚀 네이버 카페 점심 메뉴 크롤러 시작!")
        
        # 1. 게시글 목록 가져오기
        articles = self.fetch_article_list()
        
        if not articles:
            logger.error("❌ 게시글 목록을 가져올 수 없습니다.")
            return
        
        logger.info(f"📋 총 {len(articles)}개 게시글 발견")
        
        # 2. 오늘 날짜 메뉴 필터링
        today_menus = []
        
        for article in articles:
            subject = self.clean_html(article.get('subject', ''))
            article_id = article.get('articleId')
            thumbnail_url = article.get('thumbnailImageUrl', '')
            writer = article.get('memberNickName', '')
            
            if not any(k in subject for k in self.target_keywords):
                continue
            
            logger.info(f"✅ 오늘 메뉴 발견: {subject}")
            
            menu_data = {
                'title': subject,
                'article_id': article_id,
                'writer': writer,
                'link': f"https://m.cafe.naver.com/ca-fe/web/cafes/{self.club_id}/articles/{article_id}",
                'thumbnail_url': thumbnail_url,
                'images': [],
                'text_menu': '',
            }
            
            # 3. 게시글 상세 본문 가져오기
            detail = self.fetch_article_detail(article_id)
            
            if detail:
                result = detail.get('result', {})
                article_data = result.get('article', {})
                content_html = article_data.get('contentHtml', '') or article_data.get('content', '')
                
                content_images = self.extract_images_from_content(content_html)
                text_menu = self.extract_text_menu(content_html)
                
                if content_images:
                    menu_data['images'] = content_images
                    logger.info(f"   📸 이미지 {len(content_images)}개 발견")
                
                if text_menu:
                    menu_data['text_menu'] = text_menu
                    logger.info(f"   📝 텍스트 메뉴 발견")
            
            # 상세 API 실패 시 썸네일 사용
            if not menu_data['images'] and thumbnail_url:
                high_quality_url = self.get_high_quality_image_url(thumbnail_url)
                if high_quality_url:
                    menu_data['images'] = [high_quality_url]
                    logger.info(f"   📸 썸네일 이미지 사용")
            
            today_menus.append(menu_data)
        
        if not today_menus:
            logger.info("📭 오늘 날짜의 메뉴 글이 없습니다.")
            # 메뉴가 없어도 슬랙에 알림
            if self.slack_webhook_url:
                self._send_no_menu_notification()
            return
        
        # 4. 결과 저장
        self._save_results(today_menus)
        
        # 5. 슬랙 발송
        self.send_to_slack(today_menus)
        
        # 6. 요약 출력
        self._print_summary(today_menus)

    def _send_no_menu_notification(self):
        """메뉴가 없을 때 슬랙 알림"""
        today = datetime.datetime.now().strftime('%Y년 %m월 %d일 (%a)')
        
        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📭 *{today}*\n\n아직 오늘의 점심 메뉴가 올라오지 않았습니다."
                    }
                }
            ],
            "text": "오늘의 점심 메뉴가 아직 없습니다."
        }
        
        try:
            requests.post(self.slack_webhook_url, json=payload, timeout=10)
        except:
            pass

    def _save_results(self, menus):
        """결과를 JSON으로 저장"""
        results = {
            'date': datetime.datetime.now().strftime('%Y-%m-%d'),
            'found_count': len(menus),
            'menus': []
        }
        
        for menu in menus:
            results['menus'].append({
                'title': menu['title'],
                'writer': menu['writer'],
                'link': menu['link'],
                'image_urls': menu['images'],
                'text_menu': menu['text_menu'],
            })
        
        with open('results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 결과 저장: results.json")

    def _print_summary(self, menus):
        """결과 요약 출력"""
        logger.info("\n" + "="*60)
        logger.info(f"🍱 오늘의 점심 메뉴 ({len(menus)}개 식당)")
        logger.info("="*60)
        
        for i, menu in enumerate(menus, 1):
            logger.info(f"\n{i}. {menu['title']}")
            logger.info(f"   작성자: {menu['writer']}")
            logger.info(f"   링크: {menu['link']}")
            
            if menu.get('images'):
                logger.info(f"   📸 이미지: {len(menu['images'])}개")
            
            if menu['text_menu']:
                logger.info(f"   📝 메뉴 텍스트 있음")
        
        logger.info("\n" + "="*60)


if __name__ == "__main__":
    CLUB_ID = 30487307
    MENU_ID = 26
    
    bot = NaverCafeApiCrawler(CLUB_ID, MENU_ID)
    bot.run()
