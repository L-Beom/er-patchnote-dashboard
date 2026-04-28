"""
이터널리턴 패치노트 파서
- 입력: er_patchnotes/patchnotes.csv (content 컬럼)
- 출력: er_patchnotes/patchnote_changes.csv
- 컬럼: [캐릭터, 스킬, 항목, 변경전, 변경후, 패치버전]
"""

import re
import csv
from pathlib import Path

INPUT_CSV  = Path("er_patchnotes/patchnotes.csv")
OUTPUT_CSV = Path("er_patchnotes/patchnote_changes.csv")

# ── 상수 ──────────────────────────────────────────────────────────────────────

SECTION_HEADERS = frozenset({
    "실험체", "무기 스킬", "방어구", "코발트 프로토콜",
    "버그 수정 및 개선 사항",
})

# 파싱 대상 섹션 (나머지는 건너뜀)
TARGET_SECTIONS = frozenset({"실험체", "무기 스킬", "방어구", "코발트 프로토콜"})

# 방어구 슬롯 이름 (캐릭터명으로 오인 방지)
ARMOR_SLOTS = frozenset({"옷", "모자", "머리", "팔", "발", "목", "장갑", "허리", "반지", "귀걸이", "보조"})

# 방어구/아이템 스탯명 (긴 것 먼저 → greedy 매칭)
STAT_NAMES = sorted([
    "공격 속도 증가", "공격 속도",
    "이동 속도 증가", "이동 속도",
    "스킬 증폭 증가", "스킬 증폭",
    "쿨다운 감소", "기본 공격 증폭",
    "레벨 당 체력", "최대 체력", "기본 체력",
    "방어력 감소", "방어력 증가", "방어력",
    "공격력 감소", "공격력 증가", "공격력",
    "보호막 획득량", "체력 재생", "흡혈",
    "관통력", "체력", "쿨다운",
], key=len, reverse=True)

# 스킬 키 패턴: 스킬명(Q), 스킬명(W), 과전하 Q, 패시브 등
SKILL_KEY_RE = re.compile(
    r'^.+?\((?:[QWERPD]|과전하\s*[QWER]|패시브)\)\s*$'
)

# ── 버전 추출 ──────────────────────────────────────────────────────────────────

def extract_version(title: str) -> str:
    """제목에서 패치 버전 번호 추출 (예: '10.7', '10.7b')
    날짜 형식(2026.04.16)보다 게임 버전 형식(10.7) 우선.
    """
    # 2자리 정수로 시작하는 버전: 10.7b, 11.0 등 (연도 형식 제외)
    m = re.search(r'\b([1-9]\d{0,2}\.\d{1,2}[a-z]?)\b', title, re.IGNORECASE)
    return m.group(1) if m else title.strip()


# ── 변경 라인 파싱 헬퍼 ────────────────────────────────────────────────────────

def split_item_before(left: str) -> tuple[str, str]:
    """
    '항목 변경전값' → (항목, 변경전값)
    변경전값은 첫 번째 숫자 또는 '최대/추가' 키워드부터 시작한다고 가정.
    """
    tokens = left.split()
    for i, tok in enumerate(tokens):
        if re.match(r"^\d", tok):
            # 숫자로 시작 → 값의 시작
            return " ".join(tokens[:i]), " ".join(tokens[i:])
        if re.match(r"^최대", tok) and i > 0:
            # '최대 체력의 N%' 형태의 공식 참조 (추가는 항목명에도 등장하므로 제외)
            return " ".join(tokens[:i]), " ".join(tokens[i:])
    return left, ""


def parse_change_line(line: str) -> tuple[str, str, str, str]:
    """
    '(스킬명(키) )?항목 변경전 → 변경후' 형태를 파싱.
    반환: (inline_skill, 항목, 변경전, 변경후)
    """
    # 스킬명이 인라인으로 포함된 경우: "스킬명(Q) 항목 전 → 후"
    # ※ (Q/W/E/R/P/D/과전하/패시브) 키 패턴만 매칭 — 수치 공식 (N%) 오인식 방지
    m_inline = re.match(
        r'^(?P<skill>.+?\((?:[QWERPD]|과전하\s*[QWER]|패시브)\))\s+(?P<rest>\S.+→.+)$',
        line
    )
    if m_inline:
        inline_skill = m_inline.group("skill").strip()
        parts = m_inline.group("rest").split("→", 1)
        item, before = split_item_before(parts[0].strip())
        return inline_skill, item, before, parts[1].strip()

    # 일반: "항목 전 → 후"
    parts = line.split("→", 1)
    item, before = split_item_before(parts[0].strip())
    return "", item, before, parts[1].strip()


def split_armor_line(line: str) -> tuple[str, str, str, str]:
    """
    '아이템명 스탯 변경전 → 변경후' (방어구 한 줄 형식) 파싱.
    반환: (아이템명, 스탯, 변경전, 변경후)
    """
    parts = line.split("→", 1)
    if len(parts) != 2:
        return "", "", "", ""
    left, after = parts[0].strip(), parts[1].strip()

    # 알려진 스탯명을 오른쪽(뒤)에서 찾기 (줄 맨 앞 포함)
    for stat in STAT_NAMES:
        idx = left.rfind(stat)
        if idx >= 0:
            item_name  = left[:idx].strip()   # 아이템명 (스탯이 맨 앞이면 빈 문자열)
            after_stat = left[idx + len(stat):].strip()  # 변경전값
            return item_name, stat, after_stat, after

    # 스탯명 미매칭 → 단순 분리
    item, before = split_item_before(left)
    return item, "", before, after


# ── 섹션별 파서 ────────────────────────────────────────────────────────────────

def is_char_name(line: str) -> bool:
    """짧고 순수 텍스트인 줄 → 캐릭터/피사체 이름으로 판단"""
    if len(line) > 20 or not line:
        return False
    if "→" in line or "(" in line:
        return False
    if re.search(r"\d", line):
        return False
    if line in SECTION_HEADERS or line in ARMOR_SLOTS:
        return False
    return bool(re.search(r"[가-힣a-zA-Z]", line))


def parse_실험체(lines: list[str], version: str) -> list[dict]:
    records = []
    char = skill = ""

    for line in lines:
        # 스킬 헤더
        if SKILL_KEY_RE.match(line):
            skill = line
            continue

        # 변경 라인
        if "→" in line:
            inline_skill, item, before, after = parse_change_line(line)
            records.append({
                "캐릭터": char,
                "스킬":   inline_skill or skill,
                "항목":   item,
                "변경전": before,
                "변경후": after,
                "패치버전": version,
            })
            continue

        # 캐릭터명
        if is_char_name(line):
            char  = line
            skill = ""

    return records


def parse_무기스킬(lines: list[str], version: str) -> list[dict]:
    records = []
    weapon = skill = ""

    for line in lines:
        # 무기 스킬 헤더: "돌격 소총 - 과열(D)"
        m = re.match(r"^(?P<weapon>.+?)\s*-\s*(?P<skill>.+\([QWERPD]\))\s*$", line)
        if m:
            weapon = m.group("weapon").strip()
            skill  = m.group("skill").strip()
            continue

        if "→" in line:
            _, item, before, after = parse_change_line(line)
            records.append({
                "캐릭터": weapon, "스킬": skill,
                "항목": item, "변경전": before, "변경후": after,
                "패치버전": version,
            })

    return records


def parse_방어구(lines: list[str], version: str) -> list[dict]:
    records = []
    slot         = ""
    current_item = ""  # 이전 줄에서 단독으로 나온 아이템명

    for line in lines:
        if line in ARMOR_SLOTS:
            slot = line
            current_item = ""
            continue

        if "→" in line:
            item_name, stat, before, after = split_armor_line(line)
            # 스탯이 줄 맨 앞이라 item_name이 비어있으면 이전 줄 아이템명 사용
            char = item_name if item_name else current_item
            records.append({
                "캐릭터": char,
                "스킬":   slot,
                "항목":   stat if stat else before,
                "변경전": before if stat else "",
                "변경후": after,
                "패치버전": version,
            })
            # 인라인 아이템명이 있으면 다음 줄도 같은 아이템일 수 있으므로 갱신
            if item_name:
                current_item = item_name
            continue

        # 변경 라인도 슬롯도 아닌 짧은 줄 → 아이템명 (두 줄 형식)
        if line and len(line) < 20 and not re.search(r"\d", line):
            current_item = line

    return records


def parse_코발트(lines: list[str], version: str) -> list[dict]:
    records = []
    sub     = ""   # "인퓨전" or "모드 보정"
    tier    = ""   # "2단계 인퓨전" etc.
    char    = ""
    weapon_cond = ""

    for line in lines:
        # 서브섹션 헤더
        if line == "인퓨전":
            sub = "인퓨전"; char = weapon_cond = tier = ""
            continue
        if line == "코발트 프로토콜 모드 보정":
            sub = "모드 보정"; char = weapon_cond = ""
            continue

        if sub == "인퓨전":
            # 단계/레벨 헤더: "2단계 인퓨전", "3레벨 인퓨전"
            if re.match(r"^\d+(?:단계|레벨)\s*인퓨전$", line):
                tier = line; char = ""
                continue
            # 변경 라인
            if "→" in line:
                # 인라인 무기 조건
                m_cond = re.match(r"^(.+사용\s*시)\s+(.+→.+)$", line)
                if m_cond:
                    weapon_cond = m_cond.group(1)
                    rest = m_cond.group(2)
                    _, item, before, after = parse_change_line(rest)
                else:
                    _, item, before, after = parse_change_line(line)
                records.append({
                    "캐릭터": f"{tier} - {char}" if tier else char,
                    "스킬":   weapon_cond,
                    "항목":   item, "변경전": before, "변경후": after,
                    "패치버전": version,
                })
                weapon_cond = ""
                continue
            # 인퓨전 이름
            if is_char_name(line):
                char = line; weapon_cond = ""

        elif sub == "모드 보정":
            # 무기 조건 줄: "기타 사용 시", "돌격 소총 사용 시" 등
            if re.match(r"^.+사용\s*시$", line):
                weapon_cond = line
                continue
            # 변경 라인
            if "→" in line:
                # 인라인 무기 조건
                m_cond = re.match(r"^(.+사용\s*시)\s+(.+→.+)$", line)
                if m_cond:
                    weapon_cond = m_cond.group(1)
                    rest = m_cond.group(2)
                    _, item, before, after = parse_change_line(rest)
                else:
                    _, item, before, after = parse_change_line(line)
                records.append({
                    "캐릭터": char, "스킬": weapon_cond,
                    "항목":   item, "변경전": before, "변경후": after,
                    "패치버전": version,
                })
                weapon_cond = ""
                continue
            # 캐릭터명
            if is_char_name(line):
                char = line; weapon_cond = ""

    return records


# ── 메인 파서 ──────────────────────────────────────────────────────────────────

SECTION_PARSERS = {
    "실험체":           parse_실험체,
    "무기 스킬":        parse_무기스킬,
    "방어구":           parse_방어구,
    "코발트 프로토콜":  parse_코발트,
}


def parse_content(content: str, version: str) -> list[dict]:
    """패치노트 본문 텍스트 → 변경 레코드 리스트"""
    # 줄 단위로 쪼개고 공백 줄 제거
    lines = [ln.strip() for ln in content.splitlines()]
    lines = [ln for ln in lines if ln]

    records      = []
    section      = None
    section_buf  = []

    for line in lines:
        if line in SECTION_HEADERS:
            # 이전 섹션 처리
            if section in TARGET_SECTIONS and section_buf:
                records.extend(SECTION_PARSERS[section](section_buf, version))
            section     = line
            section_buf = []
        else:
            if section in TARGET_SECTIONS:
                section_buf.append(line)

    # 마지막 섹션
    if section in TARGET_SECTIONS and section_buf:
        records.extend(SECTION_PARSERS[section](section_buf, version))

    return records


# ── CSV I/O ────────────────────────────────────────────────────────────────────

def load_patchnotes(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save_changes(records: list[dict], path: Path) -> None:
    fields = ["캐릭터", "스킬", "항목", "변경전", "변경후", "패치버전"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    print(f"[저장] {path}  ({len(records)}행)")


# ── 진입점 ─────────────────────────────────────────────────────────────────────

def main():
    rows    = load_patchnotes(INPUT_CSV)
    all_rec = []

    for row in rows:
        title   = row.get("title", "")
        content = row.get("content", "")
        if not content.strip():
            print(f"  [SKIP] {title}  (content 없음)")
            continue
        version = extract_version(title)
        recs    = parse_content(content, version)
        print(f"  [{version}] {title[:40]}  → {len(recs)}건 추출")
        all_rec.extend(recs)

    # 빈 항목 행 제거
    all_rec = [r for r in all_rec if r["항목"] or r["변경전"] or r["변경후"]]

    save_changes(all_rec, OUTPUT_CSV)
    print(f"\n총 {len(all_rec)}건 변경사항 저장 완료")


if __name__ == "__main__":
    main()
