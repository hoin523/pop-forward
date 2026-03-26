import json
import os
import time
import requests
from datetime import datetime

# 슬랙 설정
SLACK_WEBHOOK_URL = ""
SLACK_CHANNEL = ""
SLACK_BOT_TOKEN = ""

# 파일 경로 관련
def get_deploy_filename(date_str):
    return f"release/release_info_{date_str}.json"

def load_deploy_list(date_str):
    filename = get_deploy_filename(date_str)
    if not os.path.exists(filename):
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_deploy_list(date_str, data):
    filename = get_deploy_filename(date_str)
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Slack 사용자 ID 조회
def find_slack_user_id_by_email(email):
    url = "https://slack.com/api/users.lookupByEmail"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    params = {"email": email}
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if data.get("ok"):
            return data["user"]["id"]
        else:
            print(f"Slack 사용자 조회 실패: {data.get('error')}")
            return None
    except Exception as e:
        print(f"Slack 사용자 조회 예외 발생: {e}")
        return None

# 채널 알림 전송
def send_reminder_to_channel(deploy):
    msg = f"""
🚨 *배포 알림 10분 뒤 반영 예정* 🚨
*제목:* {deploy['title']}
*시간:* {deploy['release_dt']}
""".strip()

    attachments = [{
        "fallback": f"{deploy['title']} - {deploy['release_dt']}",
        "color": "#36a64f",
        "pretext": msg,
        "mrkdwn_in": ["pretext"],
    }]

    if deploy.get("url"):
        attachments[0]["actions"] = [{
            "type": "button",
            "text": "내역 확인",
            "url": deploy["url"],
            "style": "danger"
        }]

    payload = {
        "channel": SLACK_CHANNEL,
        "attachments": attachments
    }

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        print(f"[채널 알림] Slack 전송 상태: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"[채널 알림] Slack 전송 실패: {e}")
        return False

# 개인 DM 전송
def send_reminder_dm(user_id, deploy):
    text = f"""
🚨 *배포 알림 10분 뒤 반영 예정* 🚨
*제목:* {deploy['title']}
*시간:* {deploy['release_dt']}
"""
    blocks = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": text.strip()}
    }]

    if deploy.get("url"):
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "내역 확인"},
                "url": deploy["url"],
                "style": "danger"
            }]
        })

    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "channel": user_id,
        "blocks": blocks,
        "text": f"{deploy['title']} - {deploy['release_dt']}"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        result = response.json()
        if result.get("ok"):
            print(f"[DM 알림] 사용자({user_id})에게 전송 성공")
            return True
        else:
            print(f"[DM 알림] 전송 실패: {result.get('error')}")
            return False
    except Exception as e:
        print(f"[DM 알림] 전송 예외 발생: {e}")
        return False

# 단일 배포 알림 처리
def send_reminder(deploy):
    ok = True
    # 채널 알림을 원할 경우 아래 주석 해제
    # ok = send_reminder_to_channel(deploy)

    if deploy.get("owners_email"):
        for email in deploy.get("owners_email"):
            user_id = find_slack_user_id_by_email(email)
            if user_id:
                ok = send_reminder_dm(user_id, deploy) and ok
    return ok

# 전체 배포 알림 루프
def run_reminder():
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    deploys = load_deploy_list(date_str)
    changed = False

    for deploy in deploys:
        if deploy.get("sent", False):
            continue
        deploy_time = datetime.strptime(deploy['time'], "%Y-%m-%d %H:%M")
        if now >= deploy_time:
            success = send_reminder(deploy)
            print(f"[발송 시도] {deploy.get('title')} - 성공: {success}")
            if success:
                deploy["sent"] = True
                changed = True

    if changed:
        save_deploy_list(date_str, deploys)

# 실행 루프
if __name__ == '__main__':
    while True:
        run_reminder()
        time.sleep(10)
