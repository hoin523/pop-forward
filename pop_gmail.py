import imaplib
import email
import re
import requests
import json
import os
from email.header import decode_header
import time
from datetime import datetime, timedelta
import imgkit
from slack_sdk import WebClient

# Slack Webhook
SLACK_WEBHOOK_URL = "" #your slack webhook url
SLACK_CHANNEL = "" # your slack channel

# Gmail IMAP env
IMAP_HOST = "" # your IMAP_HOST
IMAP_PORT = 0 # your IMAP_PORT
EMAIL_USER = "" #your EMAIL_USER
EMAIL_PASS = "" #your EMAIL_PASS

def get_data_path(release_date=None):
    if release_date:
        today_str = release_date  # 이미 'YYYYMMDD' 형식으로 전달받는다고 가정
    else:
        today_str = datetime.now().strftime("%Y%m%d")
    return f"release/release_info_{today_str}.json"

def load_release_info(release_date=None):
    path = get_data_path(release_date)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ JSON 파싱 에러 - 빈 리스트 반환")
                return []
    else:
        return []

def save_release_info(data):
    path = get_data_path()
    # 모든 datetime -> 문자열 변환
    for item in data:
        if isinstance(item.get("release_dt"), datetime):
            item["release_dt"] = item["release_dt"].strftime("%Y-%m-%d %H:%M:%S")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_release_info(text):
    try:
        # 날짜+시간 또는 시간만 추출 (예: #release 2025-08-05 09:00 또는 #release 09:00)
        # TODO 정규식 수정 필요
        matches = re.findall(r'#release\s+((?:\d{4}-\d{2}-\d{2}\s+)?\d{1,2}:\d{2})', text)
        print(text)
        if not matches:
            return None

        raw_time_str = matches[0].strip()

        # 날짜가 없으면 오늘 날짜로 보정
        if re.match(r'^\d{1,2}:\d{2}$', raw_time_str):
            today = datetime.now().strftime('%Y-%m-%d')
            raw_time_str = f"{today} {raw_time_str}"

        release_dt = datetime.strptime(raw_time_str, '%Y-%m-%d %H:%M')
        adjusted_dt = release_dt - timedelta(minutes=10)
        adjusted_time_str = adjusted_dt.strftime('%Y-%m-%d %H:%M')

        # 이메일 아이디 추출: @이후 콤마로 구분된 아이디
        email_ids_match = re.search(r'#release\s+[^\n]*@([\w,\s]+)', text)
        if email_ids_match:
            email_ids_str = email_ids_match.group(1)
            email_ids = [e.strip() for e in email_ids_str.split(',') if e.strip()]
            owners_email = [f"{email_id}@unipost.co.kr" for email_id in email_ids]
        else:
            owners_email = []

        return {
            "title": "(제목없음)",
            "release_dt": release_dt,
            "time": adjusted_time_str,
            "url": None,
            "sent": False,
            "owners_email": owners_email
        }

    except Exception as e:
        print(f"#release 정보 파싱 실패: {e}")
        return None

def extract_first_link_from_html(html):
    try:
        match = re.search(r'href=["\'](.*?)["\']', html)
        if match:
            url = match.group(1)
            return url.replace("&amp;", "&")  # &amp; 변환
    except Exception as e:
        print("링크 추출 오류:", e)
    return None

def send_html_to_slack(subject, html_content):
    try:
        # HTML → PNG 변환
        img_file = "mail_preview.png"
        imgkit.from_string(html_content, img_file)

        # Slack에 업로드
        client.files_upload(
            channels=SLACK_CHANNEL,
            file=img_file,
            title=f"📧 {subject}",
            initial_comment=f"*새 이메일 도착!* 제목: {subject}"
        )
        print("✅ Slack 업로드 성공")
    except Exception as e:
        print(f"Slack 전송 실패: {e}")

def send_to_slack(subject, sender, request_url):

    attachments = [
        {
            "fallback": subject,
            "pretext": f"*메일 제목:* {subject}",
            "mrkdwn_in": ["text"]
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
        "channel": SLACK_CHANNEL,
        "text": "*새로운 이메일이 도착했습니다!*",
        "attachments": attachments
    }

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        print(f"Slack 전송 상태: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"Slack 전송 중 오류 발생: {e}")
        return False

ALLOWED_COMPANIES = []
ALLOWED_DOMAINS = []
KEYWORDS = ['KEYWORD', '특정 단어']

def normalize(text):
    return text.replace(" ", "").lower()

def should_forward(subject, sender):
    norm_subject = normalize(subject)
    norm_sender = normalize(sender)
    domain_part = norm_sender.split('@')[-1].split('.')[0].lower()

    # 조건 1: 키워드 + 고객사 이름이 모두 제목에 포함
    if any(normalize(k) in norm_subject for k in KEYWORDS) and \
       any(normalize(c) in norm_subject for c in ALLOWED_COMPANIES):
        return True

    # 조건 2: 보낸 사람 이메일 도메인이 허용 리스트에 포함
    if any(d in domain_part for d in ALLOWED_DOMAINS):
        return True

    return False

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
                            url = extract_first_link_from_html(html_content)
                            if url and "114.unipost.co.kr" not in url:
                                url = None
                        except:
                            pass
            else:
                content_type = msg.get_content_type()
                if content_type == "text/plain":
                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors='ignore')



            # #release 정보가 있으면 일정에 저장 (10분 전 시간으로 조정)
            print(body)
            release_info = extract_release_info(body)
            print(release_info)
            if release_info: # 고객사에서 보낸 메일이 아닌 경우에만 체크
                release_info["title"] = subject

                # URL 필터링
                if url and "114.unipost.co.kr" in url:
                    release_info["url"] = url
                else:
                    release_info["url"] = None  # 도메인 포함 안 되면 저장 X

                release_info["sent"] = False

                # 배포 날짜를 release_info["time"]에서 추출해서 YYYYMMDD 포맷으로 변환
                release_date_str = release_info["time"].split()[0]  # 'YYYY-MM-DD' 가정
                release_date = release_date_str.replace("-", "")  # 'YYYYMMDD'

                data = load_release_info(release_date)

                # 중복 체크 (제목 + 시간)
                exists = any(
                    item["title"] == release_info["title"] and
                    item["time"] == release_info["time"]
                    for item in data
                )
                if not exists:
                    data.append(release_info)
                    save_release_info(data)

            # 필터링 조건 확인
            if not should_forward(subject, from_email):
                mail.store(num, '+FLAGS', '\\Seen')
                continue

            # 슬랙으로 발송
            send_to_slack(subject, from_email, url)

            mail.store(num, '+FLAGS', '\\Seen')

        mail.logout()

    except Exception as e:
        print(f"메일 처리 중 오류 발생: {e}")

if __name__ == "__main__":
    while True:
        fetch_and_forward()
        time.sleep(10)

