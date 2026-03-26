import imaplib
import email
import email.utils
import os
import re
import requests
from email.header import decode_header
import time

from dotenv import load_dotenv
import logging
from openai import OpenAI

load_dotenv()

# 팀별 설정 정보 — 민감한 값은 반드시 환경변수(.env)로 관리하세요.
# .env 예시:
#   TEAM1_WEBHOOK=<Slack Webhook URL>
#   TEAM1_OPENAI_KEY=<OpenAI API Key>
TEAMS_CONFIG = {
    "1팀": {
        "webhook": os.getenv("TEAM1_WEBHOOK", ""),
        "openai_key": os.getenv("TEAM1_OPENAI_KEY", ""),
        "channel": "#your-channel-1",
        "companies": [
            # 담당 고객사명을 리스트로 입력 (예: "회사A", "회사B")
        ],
        "domains": [
            # 고객사 이메일 도메인을 리스트로 입력 (예: "example.com", "company.co.kr")
        ],
        "notify_to": ["1팀", "5팀"]
    },
    "2팀": {
        "webhook": os.getenv("TEAM2_WEBHOOK", ""),
        "openai_key": os.getenv("TEAM2_OPENAI_KEY", ""),
        "channel": "#your-channel-2",
        "companies": [],
        "domains": [],
        "notify_to": ["2팀", "6팀"]
    },
    "3팀": {
        "webhook": os.getenv("TEAM3_WEBHOOK", ""),
        "openai_key": os.getenv("TEAM3_OPENAI_KEY", ""),
        "channel": "#your-channel-3",
        "companies": [],
        "domains": [],
        "notify_to": ["3팀", "5팀"]
    },
    "4팀": {
        "webhook": os.getenv("TEAM4_WEBHOOK", ""),
        "openai_key": os.getenv("TEAM4_OPENAI_KEY", ""),
        "channel": "#your-channel-4",
        "companies": [],
        "domains": [],
        "notify_to": ["4팀", "6팀"]
    },
    "5팀": {
        "webhook": os.getenv("TEAM5_WEBHOOK", ""),
        "channel": "#your-channel-5",
        "companies": [],
        "domains": [],
        "notify_to": ["5팀"]
    },
    "6팀": {
        "webhook": os.getenv("TEAM6_WEBHOOK", ""),
        "channel": "#your-channel-6",
        "companies": [],
        "domains": [],
        "notify_to": ["6팀"]
    }
}


# Gmail IMAP 정보 (.env 파일에서 관리 권장)
IMAP_HOST = 'imap.gmail.com'
IMAP_PORT = 993
EMAIL_USER = 'your-email@gmail.com'   # Gmail 주소
EMAIL_PASS = 'your-app-password'       # Gmail 앱 비밀번호 (2단계 인증 필요)

logger = logging.getLogger("email_summarizer")
if not logger.handlers:
    handler = logging.FileHandler("email_summary.log", encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ==========================
# 이메일 요약 함수
# ==========================
def summarize_email_with_openai(text: str, api_key: str):
    """이메일 본문을 요약해서 핵심 내용만 반환"""
    if not api_key:
        logger.warning("[SKIP] API 키가 없어 요약 불가")
        return "요약 생성 실패: API 키가 설정되지 않았습니다."

    if not text or len(text.strip()) < 20:
        logger.warning("[SKIP] 본문 내용이 너무 짧아 요약 불가")
        return "본문 내용이 부족하여 요약할 수 없습니다."

    # 팀별 클라이언트 생성
    temp_client = OpenAI(api_key=api_key)

    prompt = f"""
    너는 이메일 요약 전용 시스템이다.
    아래 규칙을 반드시 지켜라. 하나라도 어기면 실패다.

    [출력 규칙]
    - 정확히 3줄로만 작성 (줄 수 초과/미만 금지)
    - 각 줄은 한 문장으로 작성
    - 불필요한 수식어, 인사말, 추측 금지
    - 결과 외 다른 텍스트 절대 출력 금지

    [요약 기준]
    1줄: 핵심 요청
    2줄: 관련 주제/배경
    3줄: 필요한 조치 (없으면 '조치 필요 없음' 명시)

    --- 이메일 본문 ---
    {text}
    """

    try:
        logger.info(f"[REQ] 메일 요약 요청 (길이={len(text)}자)")
        resp = temp_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        summary = resp.choices[0].message.content.strip()

        # 간단한 유효성 검증
        if not summary or len(summary) < 5:
            logger.warning("[WARN] OpenAI 응답 내용이 비정상적 (짧거나 없음)")
            return "요약 생성 실패: 응답이 비어 있습니다."

        # 로그 남기기
        summary_preview = re.sub(r"\s+", " ", summary)[:100]
        logger.info(f"[OK] 요약 성공 (응답 길이={len(summary)}): {summary_preview}")

        return summary

    except Exception as e:
        logger.error(f"[ERROR] OpenAI 요약 중 예외 발생: {e}", exc_info=True)
        return "요약 생성 중 오류가 발생했습니다."


def extract_first_link_from_html(html):
    try:
        match = re.search(r'href=["\'](.*?)["\']', html)
        if match:
            url = match.group(1)
            return url.replace("&amp;", "&")  # &amp; 변환
    except Exception as e:
        print("링크 추출 오류:", e)
    return None

def send_to_slack(team_name, subject, sender, request_url, summary=None):
    """Slack Webhook으로 메일 알림 전송 + 요약 포함 (팀별 채널 적용)"""
    config = TEAMS_CONFIG.get(team_name)
    if not config:
        print(f"[ERROR] 팀 {team_name}의 설정을 찾을 수 없습니다.")
        return False

    webhook_url = config.get("webhook")
    channel = config.get("channel")

    attachments = [
        {
            "fallback": subject,
            "pretext": f"*{team_name} 알림 - 메일 제목:* {subject}",
            "mrkdwn_in": ["text", "pretext"]
        }
    ]

    if summary:
        attachments[0]["fields"] = [
            {
                "title": "✨AI 요약 내용✨",
                "value": summary,
                "short": False
            }
        ]

    if request_url:
        attachments[0]["actions"] = [
            {
                "type": "button",
                "text": "요청 내역 확인하기",
                "url": request_url,
                "style": "primary"
            }
        ]

    payload = {
        "channel": channel,
        "attachments": attachments
    }

    try:
        response = requests.post(webhook_url, json=payload)
        print(f"[{team_name}] Slack 전송 상태: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"[{team_name}] Slack 전송 중 오류 발생: {e}")
        return False

# 메일 제목에 반드시 포함되어야 하는 키워드
KEYWORDS = ['문의접수', '고객사답변']

def normalize(text):
    return text.replace(" ", "").lower()

# 여러 팀이 공유하는 공통 도메인 (도메인 중복 매칭 방지용)
COMMON_DOMAINS = []

def get_matched_teams(subject, sender, recipients=[]):
    """메일 내용과 매칭되는 모든 팀 리스트 반환 (연동 팀 포함)"""
    norm_subject = normalize(subject)
    norm_sender = normalize(sender)

    # 특정 수신 이메일 필터링: 수신자(To) 또는 참조(Cc)에 반드시 포함되어야 함
    # 아래 이메일을 실제 수신 대상 주소로 교체하세요
    SUPPORT_EMAIL = "support@your-domain.com"
    recipients_lower = [r.lower() for r in recipients]

    if SUPPORT_EMAIL not in recipients_lower:
        logger.info(f"[SKIP] {SUPPORT_EMAIL}이 수신/참조에 없음: {recipients}")
        return []

    norm_recipient = ",".join(recipients_lower)
    sender_domain = norm_sender.split('@')[-1]

    # 키워드가 없으면 무조건 스킵
    if not any(normalize(k) in norm_subject for k in KEYWORDS):
        logger.info(f"[SKIP] 키워드 미포함 메일: {subject[:30]}...")
        return []

    sender_domain = norm_sender.split('@')[-1]

    # 1단계: 제목에서 고객사명 언급 여부 확인
    mentioned_teams = set()
    for team_name, config in TEAMS_CONFIG.items():
        if any(normalize(c) in norm_subject for c in config["companies"]):
            mentioned_teams.add(team_name)

    # 2단계: 발신자 도메인 매칭 (제목 매칭이 없는 경우 보완)
    domain_matched_teams = set()
    for team_name, config in TEAMS_CONFIG.items():
        if any(d == sender_domain or sender_domain.endswith("." + d) for d in config["domains"]):
            domain_matched_teams.add(team_name)

    # 매칭 팀 합산
    all_matched = mentioned_teams.union(domain_matched_teams)

    final_teams = set()
    for team_name in all_matched:
        config = TEAMS_CONFIG.get(team_name)
        if config:
            for target_team in config.get("notify_to", [team_name]):
                final_teams.add(target_team)

    if final_teams:
        logger.info(f"[RESULT] 최종 알림 대상 팀: {list(final_teams)}")
    else:
        logger.info(f"[RESULT] 매칭되는 팀 없음 (Subject={subject[:30]}..., Sender={sender})")

    return list(final_teams)

def fetch_and_forward():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        status, messages = mail.search(None, '(UNSEEN)')
        if status != 'OK' or not messages[0]:
            print("새로운 메일 없음.")
            mail.logout()
            return

        for num in messages[0].split():
            status, data = mail.fetch(num, '(RFC822)')
            if status != 'OK':
                continue

            msg = email.message_from_bytes(data[0][1])
            subject, encoding = decode_header(msg.get("Subject"))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or 'utf-8', errors='ignore')

            from_ = msg.get("From", "")
            from_email_match = re.search(r'<(.+?)>', from_)
            from_email = from_email_match.group(1) if from_email_match else from_

            to_headers = msg.get_all("To", [])
            cc_headers = msg.get_all("Cc", [])
            all_recipients = email.utils.getaddresses(to_headers + cc_headers)
            recipient_emails = [addr for name, addr in all_recipients if addr]

            # 본문 추출
            body = ""
            url = None
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        try:
                            body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors='ignore')
                        except:
                            pass
                    elif content_type == "text/html" and not url:
                        try:
                            html_content = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors='ignore')
                            body = html_content
                            url = extract_first_link_from_html(html_content)
                            # 특정 도메인 URL만 허용 (필요에 따라 수정)
                            if url and "your-domain.com" not in url:
                                url = None
                        except:
                            pass
            else:
                content_type = msg.get_content_type()
                if content_type == "text/plain":
                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors='ignore')

            # 매칭된 팀 확인
            matched_teams = get_matched_teams(subject, from_email, recipient_emails)
            if not matched_teams:
                mail.store(num, '+FLAGS', '\\Seen')
                continue

            # 즉시 \Seen 플래그를 설정하여 중복 처리 방지
            mail.store(num, '+FLAGS', '\\Seen')

            # 매칭된 팀 중 API 키가 있는 팀 하나를 골라 요약 수행
            openai_key = None
            for team in matched_teams:
                openai_key = TEAMS_CONFIG.get(team, {}).get("openai_key")
                if openai_key:
                    break

            summary_text = summarize_email_with_openai(body, openai_key)
            print(f"[ID:{num.decode()}] [요약결과] {summary_text}")
            logger.info(f"[ID:{num.decode()}] 요약 완료: {subject[:30]}")

            # 각 팀별 슬랙으로 발송
            for team in matched_teams:
                send_to_slack(team, subject, from_email, url, summary=summary_text)

        mail.logout()

    except Exception as e:
        print(f"메일 처리 중 오류 발생: {e}")

if __name__ == "__main__":
    while True:
        fetch_and_forward()
        time.sleep(5)
