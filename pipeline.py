import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

"""
이터널리턴 패치노트 자동화 파이프라인
실행: python pipeline.py [--force] [--pages N]

옵션:
  --force     새 패치 없어도 강제 전체 실행
  --pages N   크롤링할 목록 페이지 수 (기본: 1)

실행 흐름:
  1. er_patchnote_crawler.py  → er_patchnotes/patchnotes.csv
  2. er_patchnote_parser.py   → er_patchnotes/patchnote_changes.csv
  3. 버전 비교 → 새 패치 없으면 종료
  4. 새 버전 행만 patchnote_changes.csv(루트)에 병합
  5. er_tc_generator.py       → patchnote_TC.xlsx
  6. data/last_patch.json 업데이트
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── 경로 ──────────────────────────────────────────────────────────────────────

_DIR            = Path(__file__).parent
DATA_DIR        = _DIR / "data"
LAST_PATCH_JSON = DATA_DIR / "last_patch.json"
PARSED_CSV      = _DIR / "er_patchnotes" / "patchnote_changes.csv"
ROOT_CSV        = _DIR / "patchnote_changes.csv"

# ── 버전 유틸 ─────────────────────────────────────────────────────────────────

def ver_key(v: str) -> tuple:
    m = re.match(r"(\d+)\.(\d+)([a-z]?)", str(v))
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else (0, 0, "")


# ── last_patch.json ───────────────────────────────────────────────────────────

def load_last_version() -> str | None:
    """data/last_patch.json에서 마지막으로 처리한 패치 버전을 반환"""
    if not LAST_PATCH_JSON.exists():
        return None
    try:
        return json.loads(LAST_PATCH_JSON.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def save_last_version(version: str) -> None:
    """처리 완료한 최신 버전을 data/last_patch.json에 기록"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAST_PATCH_JSON.write_text(
        json.dumps(
            {"version": version, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ── CSV 유틸 ──────────────────────────────────────────────────────────────────

def read_csv_versions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8-sig") as f:
        return {r["패치버전"] for r in csv.DictReader(f) if r.get("패치버전")}


def latest_version_in(path: Path) -> str | None:
    versions = read_csv_versions(path)
    return max(versions, key=ver_key) if versions else None


# ── 단계별 실행 ───────────────────────────────────────────────────────────────

def run_step(label: str, cmd: list[str]) -> None:
    """서브프로세스로 단계 실행. 실패 시 즉시 종료."""
    print(f"\n[{label}] 실행: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(_DIR))
    if result.returncode != 0:
        print(f"[오류] {label} 실패 (exit {result.returncode})")
        sys.exit(result.returncode)
    print(f"[{label}] 완료")


def merge_new_versions(new_versions: set[str]) -> int:
    """
    PARSED_CSV에서 new_versions에 해당하는 행을 ROOT_CSV 상단에 추가.
    반환: 추가된 행 수
    """
    with open(PARSED_CSV, encoding="utf-8-sig") as f:
        parsed_rows = list(csv.DictReader(f))

    new_rows = [r for r in parsed_rows if r.get("패치버전") in new_versions]
    if not new_rows:
        return 0

    # 최신 버전이 위로 오도록 내림차순 정렬
    new_rows.sort(key=lambda r: ver_key(r.get("패치버전", "")), reverse=True)

    existing_rows: list[dict] = []
    if ROOT_CSV.exists():
        with open(ROOT_CSV, encoding="utf-8-sig") as f:
            existing_rows = list(csv.DictReader(f))

    fields = ["캐릭터", "스킬", "항목", "변경전", "변경후", "패치버전"]
    with open(ROOT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(new_rows + existing_rows)

    return len(new_rows)


# ── Claude API 연동 stub ──────────────────────────────────────────────────────
# 여기에 Claude API 연동 추가 가능
# 현재는 rule-based TC 생성(er_tc_generator.py)만 사용

def generate_tc_with_claude(changes: list[dict]) -> list[dict]:
    """
    Claude API를 활용한 TC 자동 생성 (미구현 stub).

    rule-based 생성기(er_tc_generator.py)를 보완하여,
    복잡한 서술형 변경사항이나 신규 메카닉에 대한 TC를 Claude가 생성하도록 할 수 있음.

    구현 방향:
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        # 응답을 TC 포맷으로 파싱하여 반환

    인자:
        changes: [{"캐릭터":..., "스킬":..., "항목":...,
                   "변경전":..., "변경후":..., "패치버전":...}, ...]

    반환:
        TC 딕셔너리 리스트 (er_tc_generator.py 출력과 동일한 포맷)
    """
    # TODO: Claude API 연동 구현 후 main()의 지정 위치에서 호출
    raise NotImplementedError


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main(force: bool = False, pages: int = 1) -> None:
    print("=" * 52)
    print("  이터널리턴 패치노트 자동화 파이프라인")
    print("=" * 52)

    last_version = load_last_version()
    print(f"\n마지막 처리 버전 : {last_version or '없음'}")

    # ── 1단계: 크롤링 ─────────────────────────────────────────────────────────
    run_step("크롤링", [sys.executable, "er_patchnote_crawler.py", "--pages", str(pages)])

    # ── 2단계: 파싱 ───────────────────────────────────────────────────────────
    run_step("파싱", [sys.executable, "er_patchnote_parser.py"])

    # ── 버전 비교 ─────────────────────────────────────────────────────────────
    latest_version = latest_version_in(PARSED_CSV)
    if not latest_version:
        print("\n[오류] 파싱 결과에서 버전 정보를 찾을 수 없음")
        sys.exit(1)

    print(f"최신 크롤링 버전 : {latest_version}")

    if not force and last_version and ver_key(latest_version) <= ver_key(last_version):
        print(f"\n새 패치 없음 ({latest_version} ≤ {last_version}). 파이프라인을 종료합니다.")
        sys.exit(0)

    print(f"\n새 패치 감지: {last_version or '최초 실행'} → {latest_version}")

    # ── 새 버전 데이터 병합 ────────────────────────────────────────────────────
    new_versions = read_csv_versions(PARSED_CSV) - read_csv_versions(ROOT_CSV)

    if new_versions:
        print(f"추가할 버전: {sorted(new_versions, key=ver_key)}")
        added = merge_new_versions(new_versions)
        print(f"  → {added}행 추가됨 (patchnote_changes.csv)")
    else:
        print("병합할 새 버전 데이터 없음 (이미 포함되어 있음)")

    # ── 3단계: TC 생성 (rule-based) ───────────────────────────────────────────
    run_step("TC 생성", [sys.executable, "er_tc_generator.py"])

    # ── [여기에 Claude API 연동 추가 가능] ────────────────────────────────────
    # 아래 주석을 해제하고 generate_tc_with_claude()를 구현하면 Claude TC도 생성됨
    #
    # with open(ROOT_CSV, encoding="utf-8-sig") as f:
    #     all_rows = list(csv.DictReader(f))
    # new_rows = [r for r in all_rows if r["패치버전"] in new_versions]
    # claude_tcs = generate_tc_with_claude(new_rows)
    # # claude_tcs를 patchnote_TC.xlsx에 병합하는 로직 추가

    # ── last_patch.json 업데이트 ──────────────────────────────────────────────
    save_last_version(latest_version)
    print(f"\nlast_patch.json 업데이트 완료 → {latest_version}")
    print("\n" + "=" * 52)
    print("  파이프라인 완료")
    print("=" * 52)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="이터널리턴 패치노트 자동화 파이프라인")
    parser.add_argument("--force", action="store_true", help="새 패치 없어도 강제 전체 실행")
    parser.add_argument("--pages", type=int, default=1, help="크롤링할 목록 페이지 수 (기본: 1)")
    args = parser.parse_args()
    main(force=args.force, pages=args.pages)
