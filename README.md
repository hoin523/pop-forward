# pop-forward

Gmail로 수신된 메일을 실시간 감시하여 조건에 맞는 메일을 팀별 Slack 채널로 자동 전달하고, OpenAI로 본문을 요약해주는 자동화 봇입니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| IMAP 메일 감시 | Gmail IMAP으로 안 읽은 메일을 주기적으로 폴링 |
| 팀별 라우팅 | 제목의 고객사명 또는 발신자 도메인으로 담당 팀 자동 판별 |
| AI 요약 | OpenAI GPT로 메일 본문을 3줄로 요약 |
| Slack 알림 | 팀별 Webhook으로 요약 + 버튼 형태 알림 발송 |
| 중복 방지 | 처리 즉시 `\Seen` 플래그를 설정해 이중 처리 차단 |

---

## 동작 원리

```
┌─────────────┐     IMAP(SSL)     ┌──────────────┐
│   Gmail     │ ───────────────▶  │ fetch_and_   │
│  (UNSEEN)   │                   │ forward()    │
└─────────────┘                   └──────┬───────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │       필터링 단계             │
                          │  1. 수신자에 SUPPORT_EMAIL?  │
                          │  2. 제목에 키워드 포함?       │
                          │  3. 고객사명 / 도메인 매칭   │
                          └──────────────┬──────────────┘
                                         │ 매칭된 팀 목록
                          ┌──────────────▼──────────────┐
                          │    OpenAI GPT 요약           │
                          │  (팀 API 키 사용, 3줄 출력)  │
                          └──────────────┬──────────────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │  팀별 Slack Webhook 발송     │
                          │  - 메일 제목                 │
                          │  - AI 요약                   │
                          │  - 요청 URL 버튼 (있을 때)   │
                          └─────────────────────────────┘
```

### 단계별 상세 설명

#### 1. 메일 수신 (IMAP 폴링)
- 5초마다 Gmail IMAP에 접속하여 `UNSEEN` 메일을 조회합니다.
- Gmail 앱 비밀번호 방식으로 인증합니다 (2단계 인증 필수).

#### 2. 필터링 (`get_matched_teams`)
세 가지 조건을 순서대로 검사합니다.

1. **수신자 필터**: `To` 또는 `Cc`에 `SUPPORT_EMAIL`이 포함되지 않으면 즉시 스킵
2. **키워드 필터**: 메일 제목에 `KEYWORDS` 목록의 단어가 없으면 스킵
3. **팀 매칭**:
   - **1단계 (제목)**: 제목에 고객사명이 언급된 팀을 추출
   - **2단계 (도메인)**: 발신자 이메일 도메인이 팀 도메인 목록과 일치하는 팀을 추출
   - 두 결과를 합산하여 최종 알림 대상 팀 결정

#### 3. AI 요약 (`summarize_email_with_openai`)
- 매칭된 팀 중 `openai_key`가 설정된 첫 번째 팀의 키를 사용합니다.
- GPT에게 아래 형식의 3줄 요약을 요청합니다:
  - **1줄**: 핵심 요청
  - **2줄**: 관련 주제/배경
  - **3줄**: 필요한 조치

#### 4. Slack 알림 (`send_to_slack`)
- 팀별 Webhook URL로 `attachments` 형식의 메시지를 발송합니다.
- HTML 본문에서 추출한 특정 도메인 URL이 있으면 버튼으로 첨부합니다.

#### 5. 중복 처리 방지
- 팀 매칭 성공 후 즉시 `\Seen` 플래그를 설정합니다.
- 매칭 실패한 메일도 `\Seen` 처리하여 재검사하지 않습니다.

---

## 설정 방법

### 1. 환경 준비

```bash
pip install -r requirements.txt
```

### 2. Gmail 앱 비밀번호 발급

1. Google 계정 → **보안** → **2단계 인증** 활성화
2. **앱 비밀번호** 생성 (앱: 메일, 기기: 기타)
3. 발급된 16자리 비밀번호를 `EMAIL_PASS`에 입력

### 3. Slack Webhook 발급

1. [Slack API Apps](https://api.slack.com/apps) 접속
2. **Create New App** → **From scratch** 선택
3. **Incoming Webhooks** 메뉴 → **Activate Incoming Webhooks** ON
4. **Add New Webhook to Workspace** → 채널 선택
5. 발급된 Webhook URL을 `TEAMS_CONFIG`의 `webhook`에 입력

### 4. `pop_gmail.py` 설정

```python
# Gmail 계정 정보
EMAIL_USER = 'your-email@gmail.com'
EMAIL_PASS = 'your-app-password'

# 수신 대상 이메일 (메일의 To/Cc에 있어야 처리됨)
SUPPORT_EMAIL = "support@your-domain.com"

# 필터 키워드 (메일 제목에 반드시 포함되어야 함)
KEYWORDS = ['키워드1', '키워드2']

# 팀 설정
TEAMS_CONFIG = {
    "1팀": {
        "webhook": "https://hooks.slack.com/services/...",
        "openai_key": "sk-proj-...",
        "channel": "#your-channel",
        "companies": ["고객사A", "고객사B"],   # 제목 매칭용 고객사명
        "domains": ["company-a.com"],           # 발신자 도메인 매칭
        "notify_to": ["1팀", "2팀"]             # 알림 받을 팀 목록
    },
    ...
}
```

### 5. 실행

```bash
python pop_gmail.py
```

백그라운드 실행 (Linux/Mac):

```bash
nohup python pop_gmail.py &
```

---

## 파일 구조

```
pop-forward/
├── pop_gmail.py        # 메인 스크립트
├── requirements.txt    # 패키지 의존성
├── email_summary.log   # 실행 로그 (자동 생성)
└── README.md
```

---

## 로그

`email_summary.log` 파일에 아래 형식으로 기록됩니다.

```
[2025-01-01 09:00:00] INFO - [SKIP] 키워드 미포함 메일: 일반 문의 메일...
[2025-01-01 09:00:05] INFO - [REQ] 메일 요약 요청 (길이=512자)
[2025-01-01 09:00:07] INFO - [OK] 요약 성공 (응답 길이=95): 핵심 요청 내용...
[2025-01-01 09:00:07] INFO - [RESULT] 최종 알림 대상 팀: ['1팀', '5팀']
```

---

## 의존성

| 패키지 | 용도 |
|--------|------|
| `openai` | GPT 요약 |
| `requests` | Slack Webhook 호출 |
| `python-dotenv` | 환경변수 로드 |

---

## 주의사항

- `EMAIL_PASS`와 `openai_key`, `webhook` URL은 절대 코드에 하드코딩하지 마세요. `.env` 파일 또는 환경변수로 관리하세요.
- `.env` 파일은 반드시 `.gitignore`에 추가하세요.
- Gmail IMAP은 기본적으로 비활성화 상태입니다. Gmail 설정 → **전달 및 POP/IMAP** → **IMAP 사용**을 활성화해야 합니다.
