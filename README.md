# 이터널리턴 패치노트 QA 자동화 파이프라인

> 패치노트 크롤링부터 테스트 케이스 생성, 분석 대시보드까지 — 반복적인 수동 TC 작성을 자동화한 QA 포트폴리오 프로젝트입니다.
>
> 패치 1회당 평균 30~60개의 TC를 자동 생성합니다.

🔗 **대시보드 배포 URL:** https://er-patchnote-dashboard.streamlit.app

---

## 왜 만들었나요?

게임 QA에서 패치노트가 나올 때마다 수십~수백 개의 테스트 케이스를 수작업으로 작성하는 일은 반복적이고 오류가 발생하기 쉽습니다.

이 프로젝트는 다음 문제를 해결합니다.

- **패치노트 수동 열람** → 크롤러가 자동 수집
- **변경 수치 직접 파악** → 파서가 구조화된 CSV로 추출
- **TC 문서 수작업 작성** → 생성기가 Excel TC 파일 자동 출력
- **버프/너프 흐름 감으로 파악** → 대시보드에서 버전별·캐릭터별 시각화

---

## 기술 스택

| 분류 | 사용 기술 |
|------|-----------|
| 크롤링 | Python, Playwright (async), Next.js SPA 대응 |
| 파싱 | Python, 정규식, 섹션 기반 상태 머신 |
| TC 생성 | Python, openpyxl |
| 대시보드 | Streamlit, Plotly, pandas |
| 배포 | Streamlit Community Cloud |
| 자동화 | GitHub Actions (cron 스케줄, workflow_dispatch) |

---

## 파이프라인 구조

```
1. 크롤링         er_patchnote_crawler.py
   └─ 이터널리턴 공식 홈페이지 패치노트 페이지 수집
   └─ window.__NEXT_DATA__ → API 인터셉트 → DOM 평가 3단계 추출
   └─ 출력: er_patchnotes/patchnotes.csv

2. 파싱           er_patchnote_parser.py
   └─ 실험체 스킬 / 실험체 기본 스탯 섹션 기반 상태 머신 파싱
   └─ 캐릭터명, 스킬명, 항목, 변경 전/후 수치, 패치버전 추출
   └─ 출력: patchnote_changes.csv

3. TC 생성        er_tc_generator.py
   └─ 변경 유형(실험체 스킬 / 실험체 기본 스탯) 분류
   └─ TC ID, 사전조건, 테스트 절차, 기댓값 자동 생성
   └─ 패치버전당 평균 30~60개 TC 생성
   └─ 출력: er_patchnotes/patchnote_TC.xlsx

4. 대시보드       er_dashboard.py
   └─ 패치버전별 변경 건수 추이
   └─ 캐릭터별 버프/너프 횟수 순위
   └─ 캐릭터 검색 → 패치 히스토리 조회
   └─ 이번 패치 테스트 우선순위 자동 산정 (변경 수치 폭 + 너프 1.5배 가중치 기반)
```

---

## 파일 구성

```
er-patchnote-dashboard/
├── er_patchnote_crawler.py   # 크롤러
├── er_patchnote_parser.py    # 파서
├── er_tc_generator.py        # TC 생성기
├── er_dashboard.py           # Streamlit 대시보드
├── pipeline.py               # 자동화 파이프라인 (크롤링→파싱→TC생성 통합 실행)
├── patchnote_changes.csv     # 파싱 결과 데이터 (대시보드 입력)
├── patchnote_TC.xlsx         # TC 생성 결과
├── data/
│   └── last_patch.json       # 마지막 처리 버전 기록
├── .github/
│   └── workflows/
│       └── weekly-patch.yml  # GitHub Actions 자동 실행 워크플로우
└── requirements.txt
```

---

## 자동화 실행 (GitHub Actions)

패치 감지부터 TC 생성, GitHub 커밋까지 자동으로 실행됩니다.

| 항목 | 내용 |
|------|------|
| 자동 실행 | 매주 목요일 12:00 KST |
| 감지 방식 | `data/last_patch.json`에 기록된 버전과 비교 |
| 새 패치 없으면 | 파이프라인 즉시 종료 (불필요한 실행 방지) |
| 새 패치 있으면 | 크롤링 → 파싱 → TC생성 → 자동 커밋 → Streamlit 갱신 |

**수동 실행 방법:**
GitHub 저장소 → Actions 탭 → "이터널리턴 패치노트 자동 업데이트" → Run workflow

**통합 파이프라인 직접 실행:**

```bash
python pipeline.py           # 새 패치 있을 때만 실행
python pipeline.py --force   # 강제 전체 실행
python pipeline.py --pages 2 # 2페이지 크롤링
```

---

## 실행 방법

### 1. 환경 설정

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 크롤링 (선택 — CSV 이미 포함됨)

```bash
python er_patchnote_crawler.py --pages 3
```

| 옵션 | 설명 |
|------|------|
| `--pages N` | 수집할 목록 페이지 수 (기본 1) |
| `--list-only` | 목록만 수집하고 상세 페이지 크롤링 생략 |
| `--show-browser` | 브라우저 창 표시 (headless 해제) |

### 3. 파싱

```bash
python er_patchnote_parser.py
```

### 4. TC 생성

```bash
python er_tc_generator.py
```

`er_patchnotes/patchnote_TC.xlsx` 파일이 생성됩니다.

### 5. 대시보드 실행

```bash
streamlit run er_dashboard.py
```

브라우저에서 `http://localhost:8501` 접속

---

## 대시보드 주요 기능

- **패치 개요** — 버전별 변경 건수 막대그래프, 버프/너프 비율 차트
- **캐릭터 순위** — 누적 버프/너프 횟수 Top 15, 패치 빈도 히트맵
- **캐릭터 검색** — 특정 캐릭터의 전체 패치 이력 조회 및 상세 테이블
- **테스트 우선순위** — 변경 수치 폭 기준 자동 산정, 너프 항목 1.5배 가중치 적용

---

## TC 생성 예시

| TC ID | 테스트 항목 | 기댓값 |
|-------|------------|--------|
| TC-10.7-001 | [실험체] 아이솔 - 공명(Q) 피해량 수치 확인 | 피해량: 70/105/140/175/210 (변경 전: 65/100/135/170/205) |
| TC-10.7-002 | [실험체] 혜진 - 기의 흐름(W) 스킬 재사용 대기 시간 확인 | 스킬 재사용 대기 시간: 2.5초 (변경 전: 2초) |

---

## 라이선스

개인 포트폴리오 목적으로 제작되었습니다. 이터널리턴 콘텐츠의 저작권은 Nimble Neuron에 있습니다.
