## 🔗 Slack Webhook 발급 방법

1. [Slack API Apps 페이지](https://api.slack.com/apps) 에 접속
2. **"Create New App"** → **"From scratch"** 선택 후 앱 이름과 워크스페이스를 지정
3. 생성된 앱 설정 화면에서 **Incoming Webhooks** 메뉴로 이동합니다.
4. **Activate Incoming Webhooks** 를 **ON** 으로 변경합니다.![img.png](img.png)
5. 같은 화면에서 **"Add New Webhook to Workspace"** 버튼을 눌러 메시지를 보낼 **채널**을 선택합니다.
6. 권한을 허용하면 Webhook URL이 발급됩니다. 예:

```
https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
```
7. 발급받은 Webhook URL과 채널명을 `.env` 파일에 추가합니다.

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#your_channel
```

좋습니다. README 이어 붙일 수 있도록, 방금 보내주신 소스 기준으로 기능 설명을 깔끔하게 정리해드릴게요.

---

## 📌 기능 설명

이 프로젝트는 **이메일(IMAP)을 주기적으로 확인**하고, 특정 조건에 맞는 메일을 **Slack으로 알림**을 전송하는 스크립트입니다. 또한 메일 본문에 포함된 `#release` 태그를 파싱하여 배포 일정을 자동으로 관리할 수 있습니다.

### 주요 기능

1. **이메일 수신 (IMAP)**

    * IMAP 서버에 주기적으로 연결하여 새로운 메일을 확인합니다.
    * 읽지 않은 메일(UNSEEN)만 가져옵니다.

2. **메일 필터링**

    * 메일 **제목**에 고객사명 + 특정 키워드(예: `문의접수`, `고객사답변`)가 포함되어 있는 경우
    * 메일 **보낸 사람의 도메인**이 허용된 리스트(`ALLOWED_DOMAINS`)에 포함된 경우
      → 조건을 만족하면 Slack으로 전달합니다.

3. **Slack 알림 전송**

    * 조건에 맞는 메일을 Slack으로 전송합니다.
    * 메일 제목과 함께 버튼을 추가하여 관련 요청 URL을 클릭할 수 있습니다.

4. **배포 일정 관리 (#release 파싱)**

    * 메일 본문에 `#release` 태그가 포함된 경우, 배포 일정을 자동으로 추출합니다.

        * 예시:

          ```
          #release 2025-08-05 09:00 @user1,user2
          ```
        * 배포 시간(`release_dt`)을 파싱하고, 실제 배포 10분 전 시간으로 보정하여 저장합니다.
        * 담당자 이메일(`@user1, user2`)도 추출합니다.
    * 추출된 정보는 `release/release_info_YYYYMMDD.json` 파일에 저장됩니다.
    * 동일한 제목+시간이 이미 저장되어 있다면 중복 저장하지 않습니다.

5. **자동 실행**

    * `while True:` 루프에서 10초마다 메일함을 확인합니다.
    * 새로운 메일이 있으면 위 과정을 반복 실행합니다.

---

### 실행 흐름 요약

1. IMAP 서버에서 새 메일 확인
2. 본문/제목/보낸 사람 정보 추출
3. `#release` 태그 파싱 → JSON 파일 저장
4. 필터 조건 검사
5. 조건 만족 시 Slack으로 알림 전송
6. 메일 읽음 처리 후 종료

---
