# 이터널리턴 패치노트 QA 자동화 파이프라인

> 패치노트 크롤링부터 테스트 케이스 생성, 분석 대시보드까지 — 반복적인 수동 TC 작성을 자동화한 QA 포트폴리오 프로젝트입니다.
>
> 패치 1회당 평균 500개 이상의 TC를 자동 생성합니다.

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

---

## 파이프라인 구조

```
1. 크롤링         er_patchnote_crawler.py
   └─ 이터널리턴 공식 홈페이지 패치노트 페이지 수집
   └─ window.__NEXT_DATA__ → API 인터셉트 → DOM 평가 3단계 추출
   └─ 출력: er_patchnotes/patchnotes.csv

2. 파싱           er_patchnote_parser.py
   └─ 섹션(실험체 / 방어구 / 코발트 프로토콜) 기반 상태 머신 파싱
   └─ 캐릭터명, 스킬명, 항목, 변경 전/후 수치, 패치버전 추출
   └─ 출력: patchnote_changes.csv

3. TC 생성        er_tc_generator.py
   └─ 변경 유형(실험체 스킬 / 기본 스탯 / 방어구 / 코발트 인퓨전 / 모드 보정) 분류
   └─ TC ID, 사전조건, 테스트 절차, 기댓값 자동 생성
   └─ 출력: er_patchnotes/patchnote_TC.xlsx

4. 대시보드       er_dashboard.py
   └─ 패치버전별 변경 건수 추이
   └─ 캐릭터별 버프/너프 횟수 순위
   └─ 캐릭터 검색 → 패치 히스토리 조회
```

---

## 파일 구성

```
er-patchnote-dashboard/
├── er_patchnote_crawler.py   # 크롤러
├── er_patchnote_parser.py    # 파서
├── er_tc_generator.py        # TC 생성기
├── er_dashboard.py           # Streamlit 대시보드
├── patchnote_changes.csv     # 파싱 결과 데이터 (대시보드 입력)
└── requirements.txt
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

- **패치 개요** — 버전별 변경 건수 막대그래프, 버프/너프 비율 파이차트
- **캐릭터 순위** — 누적 버프/너프 횟수 Top 15, 패치 빈도 히트맵
- **캐릭터 검색** — 특정 캐릭터의 전체 패치 이력 조회 및 상세 테이블

---

## TC 생성 예시

| TC ID | 테스트 항목 | 기댓값 |
|-------|------------|--------|
| TC-10.7-001 | [실험체] 아이솔 - 공명(Q) 피해량 수치 확인 | 피해량: 70/105/140/175/210 (변경 전: 65/100/135/170/205) |
| TC-10.7-002 | [방어구] 경량 방탄복 (옷) - 방어력 수치 확인 | 방어력: 22 (변경 전: 20) |

---

## 라이선스

개인 포트폴리오 목적으로 제작되었습니다. 이터널리턴 콘텐츠의 저작권은 Nimble Neuron에 있습니다.
