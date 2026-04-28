"""
이터널리턴 패치노트 대시보드
실행: streamlit run er_dashboard.py
"""

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── 상수 ──────────────────────────────────────────────────────────────────────

# 스크립트 파일 위치 기준 상대경로 — 실행 디렉터리와 무관하게 동작
CSV_PATH = Path(__file__).parent / "patchnote_changes.csv"
ARMOR_SLOTS = frozenset({"옷","모자","머리","팔","발","목","장갑","허리","반지","귀걸이","보조"})

# 이터널리턴 실험체(캐릭터) 공식 이름 목록
# 무기 타입·시스템 항목·아이템명 등 비캐릭터 항목 파싱 오류를 방지하기 위한 화이트리스트
ER_CHARACTERS: frozenset[str] = frozenset({
    "가넷", "나딘", "나타폰", "다르코", "띠아",
    "라우라", "레녹스", "레니", "레온", "로지",
    "르노어", "리 다이린", "마르티나", "마이", "마커스",
    "매그너스", "미르카", "바바라", "버니스", "비앙카",
    "샬럿", "셀린", "쇼우", "쇼이치", "수아",
    "슈린", "시셀라", "실비아", "아델라", "아디나",
    "아르다", "아비게일", "아야", "아이솔", "아이작",
    "알렉스", "알론소", "얀", "에스텔", "에이든",
    "에키온", "엘레나", "엠마", "윌리엄", "유스티나",
    "유키", "이렘", "이바", "이슈트반", "이안",
    "일레븐", "제니", "츠바메", "카밀로", "칼라",
    "캐시", "케네스", "코렐라인", "클로에", "키아라",
    "타지아", "테오도르", "펜리르", "프리야", "피오라",
    "피올로", "헤이즈", "헨리", "현우", "혜진",
})

COLOR_BUFF   = "#27AE60"
COLOR_NERF   = "#E74C3C"
COLOR_NEUTRAL= "#95A5A6"
COLOR_BN = {"버프": COLOR_BUFF, "너프": COLOR_NERF, "중립": COLOR_NEUTRAL}

TYPE_COLORS = {
    "실험체 스킬":      "#3498DB",
    "실험체 기본 스탯":  "#1ABC9C",
    "방어구":           "#F39C12",
    "코발트 인퓨전":    "#9B59B6",
    "코발트 모드 보정":  "#BDC3C7",
}

# ── 데이터 로딩 & 전처리 ──────────────────────────────────────────────────────

def version_key(v: str):
    m = re.match(r"(\d+)\.(\d+)([a-z]?)", str(v))
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else (0, 0, "")


def classify_type(row) -> str:
    char  = str(row["캐릭터"])
    skill = str(row["스킬"])
    if "인퓨전" in char:                                    return "코발트 인퓨전"
    if "사용 시" in skill:                                  return "코발트 모드 보정"
    if skill in ARMOR_SLOTS:                               return "방어구"
    if re.search(r"\((?:[QWERPD]|과전하|패시브)", skill):  return "실험체 스킬"
    return "실험체 기본 스탯"


def avg_numbers(s: str) -> float | None:
    nums = [float(x) for x in re.findall(r"\d+\.?\d*", str(s))]
    return sum(nums) / len(nums) if nums else None


def classify_buff_nerf(row) -> str:
    item   = str(row["항목"])
    before = avg_numbers(row["변경전"])
    after  = avg_numbers(row["변경후"])
    if before is None or after is None or before == after:
        return "중립"
    increased = after > before
    # 이 항목들은 증가가 너프 (쿨다운 길어짐, 받는 피해량 증가)
    if any(kw in item for kw in ["쿨다운", "받는 피해량"]):
        return "너프" if increased else "버프"
    return "버프" if increased else "너프"


@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    df["유형"]   = df.apply(classify_type,     axis=1)
    df["버프너프"] = df.apply(classify_buff_nerf, axis=1)
    # 버전 정렬용 키
    df["_ver_key"] = df["패치버전"].apply(version_key)
    df = df.sort_values("_ver_key").drop(columns=["_ver_key"])
    return df


def is_character_row(df: pd.DataFrame) -> pd.Series:
    """실험체(캐릭터) 행만 True — 유형 조건 + ER_CHARACTERS 화이트리스트 동시 적용"""
    return (
        df["유형"].isin(["실험체 스킬", "실험체 기본 스탯"]) &
        df["캐릭터"].isin(ER_CHARACTERS)
    )


# ── 시각화 헬퍼 ────────────────────────────────────────────────────────────────

def chart_version_char_count(df: pd.DataFrame) -> go.Figure:
    """패치버전별 변경 캐릭터 수 막대그래프"""
    char_df = df[is_character_row(df)]
    agg = (
        char_df.groupby("패치버전")["캐릭터"]
        .nunique()
        .reset_index(name="변경 캐릭터 수")
    )
    # 버전 순 정렬
    agg["_k"] = agg["패치버전"].apply(version_key)
    agg = agg.sort_values("_k").drop(columns=["_k"])

    fig = px.bar(
        agg, x="패치버전", y="변경 캐릭터 수",
        color="변경 캐릭터 수",
        color_continuous_scale=["#AED6F1", "#1A5276"],
        text="변경 캐릭터 수",
        title="패치버전별 변경 캐릭터 수",
    )
    fig.update_traces(textposition="outside", marker_line_width=0)
    fig.update_coloraxes(showscale=False)
    fig.update_layout(
        xaxis_title="패치버전", yaxis_title="캐릭터 수",
        plot_bgcolor="white", paper_bgcolor="white",
        title_font_size=15,
    )
    return fig


def chart_version_type_stack(df: pd.DataFrame) -> go.Figure:
    """패치버전별 유형별 변경 건수 누적 막대"""
    agg = (
        df.groupby(["패치버전", "유형"])
        .size().reset_index(name="건수")
    )
    agg["_k"] = agg["패치버전"].apply(version_key)
    agg = agg.sort_values("_k").drop(columns=["_k"])

    fig = px.bar(
        agg, x="패치버전", y="건수", color="유형",
        color_discrete_map=TYPE_COLORS,
        barmode="stack",
        title="패치버전별 변경 유형 분포",
        text_auto=False,
    )
    fig.update_layout(
        xaxis_title="패치버전", yaxis_title="변경 건수",
        plot_bgcolor="white", paper_bgcolor="white",
        legend_title="유형", title_font_size=15,
    )
    return fig


def chart_version_buff_nerf(df: pd.DataFrame) -> go.Figure:
    """패치버전별 버프/너프 건수 그룹 막대"""
    char_df = df[is_character_row(df)]
    agg = (
        char_df.groupby(["패치버전", "버프너프"])
        .size().reset_index(name="건수")
    )
    agg["_k"] = agg["패치버전"].apply(version_key)
    agg = agg.sort_values(["_k", "버프너프"]).drop(columns=["_k"])

    fig = px.bar(
        agg, x="패치버전", y="건수", color="버프너프",
        color_discrete_map=COLOR_BN,
        barmode="group",
        title="패치버전별 버프 / 너프 건수 (실험체)",
    )
    fig.update_layout(
        xaxis_title="패치버전", yaxis_title="건수",
        plot_bgcolor="white", paper_bgcolor="white",
        legend_title="구분", title_font_size=15,
    )
    return fig


def chart_ranking(df: pd.DataFrame, bn: str, top_n: int) -> go.Figure:
    """버프 또는 너프 횟수 상위 캐릭터 수평 막대"""
    char_df = df[is_character_row(df) & (df["버프너프"] == bn)]
    agg = (
        char_df.groupby("캐릭터").size()
        .reset_index(name="횟수")
        .nlargest(top_n, "횟수")
        .sort_values("횟수")
    )
    color = COLOR_BUFF if bn == "버프" else COLOR_NERF
    fig = px.bar(
        agg, y="캐릭터", x="횟수", orientation="h",
        text="횟수",
        title=f"{bn} 상위 {top_n}캐릭터",
        color_discrete_sequence=[color],
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        xaxis_title="횟수", yaxis_title="",
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False, title_font_size=14,
        height=max(320, top_n * 28),
        margin=dict(l=10, r=40, t=50, b=30),
    )
    return fig


def chart_total_change_ranking(df: pd.DataFrame, top_n: int) -> go.Figure:
    """총 변경 횟수 상위 캐릭터 (버프+너프 누적)"""
    char_df = df[is_character_row(df) & (df["버프너프"].isin(["버프", "너프"]))]
    agg = (
        char_df.groupby(["캐릭터", "버프너프"])
        .size().reset_index(name="횟수")
    )
    total = char_df.groupby("캐릭터").size().reset_index(name="합계")
    top_chars = total.nlargest(top_n, "합계")["캐릭터"].tolist()

    agg_top = agg[agg["캐릭터"].isin(top_chars)].copy()
    # 합계 기준 정렬
    sort_order = (
        total[total["캐릭터"].isin(top_chars)]
        .sort_values("합계")["캐릭터"].tolist()
    )

    fig = px.bar(
        agg_top, y="캐릭터", x="횟수", color="버프너프",
        color_discrete_map=COLOR_BN,
        barmode="stack", orientation="h",
        title=f"누적 변경 횟수 상위 {top_n}캐릭터",
        category_orders={"캐릭터": sort_order},
    )
    fig.update_layout(
        xaxis_title="총 변경 횟수", yaxis_title="",
        plot_bgcolor="white", paper_bgcolor="white",
        legend_title="구분", title_font_size=14,
        height=max(320, top_n * 28),
        margin=dict(l=10, r=20, t=50, b=30),
    )
    return fig


def chart_char_history_timeline(char_df: pd.DataFrame, char_name: str) -> go.Figure:
    """캐릭터 패치별 변경 건수 타임라인 (버프/너프 스택)"""
    agg = (
        char_df[char_df["버프너프"].isin(["버프", "너프"])]
        .groupby(["패치버전", "버프너프"])
        .size().reset_index(name="건수")
    )
    agg["_k"] = agg["패치버전"].apply(version_key)
    agg = agg.sort_values("_k").drop(columns=["_k"])

    fig = px.bar(
        agg, x="패치버전", y="건수", color="버프너프",
        color_discrete_map=COLOR_BN,
        barmode="group",
        title=f"{char_name} 패치버전별 변경 건수",
    )
    fig.update_layout(
        xaxis_title="패치버전", yaxis_title="건수",
        plot_bgcolor="white", paper_bgcolor="white",
        legend_title="구분", title_font_size=13,
        height=280, margin=dict(t=45, b=30),
    )
    return fig


# ── 메인 UI ───────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="이터널리턴 패치노트 대시보드",
        page_icon="⚔️",
        layout="wide",
    )

    # ── 헤더
    st.title("⚔️ 이터널리턴 패치노트 대시보드")
    st.caption("patchnote_changes.csv 기반 자동 분석")

    if not CSV_PATH.exists():
        st.error(f"파일이 없습니다: {CSV_PATH}\ner_patchnote_parser.py를 먼저 실행해주세요.")
        return

    df = load_data()
    all_versions = sorted(df["패치버전"].unique(), key=version_key)
    all_types    = df["유형"].unique().tolist()

    # ── 사이드바 필터
    with st.sidebar:
        st.header("🔧 필터")
        st.markdown("---")

        sel_versions = st.multiselect(
            "패치버전", all_versions, default=all_versions,
            help="분석할 패치버전을 선택하세요"
        )
        sel_types = st.multiselect(
            "변경 유형", all_types, default=all_types,
        )
        st.markdown("---")
        st.markdown("**범례**")
        st.markdown(
            f"🟢 버프 &nbsp;&nbsp; 🔴 너프 &nbsp;&nbsp; ⚪ 중립"
        )
        st.markdown("---")
        st.caption("이터널리턴 패치노트 자동 파싱")

    if not sel_versions or not sel_types:
        st.warning("패치버전과 유형을 하나 이상 선택해주세요.")
        return

    fdf = df[df["패치버전"].isin(sel_versions) & df["유형"].isin(sel_types)]

    # ── KPI 카드
    char_fdf = fdf[is_character_row(fdf)]
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("총 변경 건수",    f"{len(fdf):,}")
    k2.metric("영향 캐릭터 수",   f"{char_fdf['캐릭터'].nunique():,}")
    k3.metric("🟢 버프",
              f"{(char_fdf['버프너프'] == '버프').sum():,}")
    k4.metric("🔴 너프",
              f"{(char_fdf['버프너프'] == '너프').sum():,}")
    k5.metric("분석 패치 수",    f"{fdf['패치버전'].nunique()}")

    st.markdown("---")

    # ── 탭
    tab1, tab2, tab3 = st.tabs(["📊 패치 개요", "🏆 캐릭터 순위", "🔍 캐릭터 검색"])

    # ────────────────── Tab 1: 패치 개요 ──────────────────────────────────────
    with tab1:
        st.subheader("패치버전별 변경 캐릭터 수")
        st.plotly_chart(chart_version_char_count(fdf), use_container_width=True)

        col_l, col_r = st.columns(2)
        with col_l:
            st.plotly_chart(chart_version_type_stack(fdf), use_container_width=True)
        with col_r:
            st.plotly_chart(chart_version_buff_nerf(fdf), use_container_width=True)

        # 패치버전 선택 → 해당 버전 변경 요약 테이블
        st.markdown("---")
        st.subheader("패치버전 상세 요약")
        sel_v = st.selectbox(
            "버전 선택", sorted(fdf["패치버전"].unique(), key=version_key, reverse=True),
            key="tab1_ver"
        )
        vdf = fdf[fdf["패치버전"] == sel_v]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("변경 건수",    len(vdf))
        c2.metric("영향 캐릭터",  vdf[is_character_row(vdf)]["캐릭터"].nunique())
        c3.metric("버프",         (vdf["버프너프"] == "버프").sum())
        c4.metric("너프",         (vdf["버프너프"] == "너프").sum())

        st.dataframe(
            vdf[["유형","캐릭터","스킬","항목","변경전","변경후","버프너프"]]
            .rename(columns={"버프너프": "구분"})
            .reset_index(drop=True),
            use_container_width=True, height=340,
        )

    # ────────────────── Tab 2: 캐릭터 순위 ───────────────────────────────────
    with tab2:
        top_n = st.slider("상위 N개 표시", 5, 30, 15, key="ranking_n")
        st.markdown("")

        col_buff, col_nerf = st.columns(2)
        with col_buff:
            st.plotly_chart(
                chart_ranking(fdf, "버프", top_n), use_container_width=True
            )
        with col_nerf:
            st.plotly_chart(
                chart_ranking(fdf, "너프", top_n), use_container_width=True
            )

        st.markdown("---")
        st.plotly_chart(
            chart_total_change_ranking(fdf, top_n), use_container_width=True
        )

        # 패치버전별 버프/너프 비율 히트맵 (캐릭터 × 버전)
        st.markdown("---")
        st.subheader("캐릭터 × 패치버전 변경 히트맵")

        hm_type = st.radio(
            "표시 기준", ["버프", "너프", "전체"], horizontal=True, key="hm_type"
        )
        hm_df = fdf[is_character_row(fdf)].copy()
        if hm_type != "전체":
            hm_df = hm_df[hm_df["버프너프"] == hm_type]

        pivot = (
            hm_df.groupby(["캐릭터", "패치버전"])
            .size().reset_index(name="건수")
            .pivot(index="캐릭터", columns="패치버전", values="건수")
            .fillna(0)
        )
        # 버전 정렬
        sorted_cols = sorted(pivot.columns, key=version_key)
        pivot = pivot[sorted_cols]
        # 총합 기준 상위 캐릭터만
        top_chars_hm = pivot.sum(axis=1).nlargest(min(top_n, len(pivot))).index
        pivot = pivot.loc[top_chars_hm]

        cscale = "Blues" if hm_type == "버프" else ("Reds" if hm_type == "너프" else "Purples")
        fig_hm = go.Figure(go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale=cscale,
            showscale=True,
            text=pivot.values.astype(int),
            texttemplate="%{text}",
            hovertemplate="캐릭터: %{y}<br>버전: %{x}<br>건수: %{z}<extra></extra>",
        ))
        fig_hm.update_layout(
            title=f"캐릭터 × 패치버전 ({hm_type}) 변경 건수",
            xaxis_title="패치버전", yaxis_title="캐릭터",
            height=max(380, len(top_chars_hm) * 22),
            margin=dict(l=10, r=20, t=50, b=30),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_hm, use_container_width=True)

    # ────────────────── Tab 3: 캐릭터 검색 ───────────────────────────────────
    with tab3:
        st.subheader("캐릭터 패치 히스토리")

        # 캐릭터 목록 (실험체 스킬/기본 스탯 한정)
        char_list = sorted(
            fdf[is_character_row(fdf)]["캐릭터"].dropna().unique()
        )
        if not char_list:
            st.info("선택된 필터에 해당하는 캐릭터가 없습니다.")
        else:
            search_col, _ = st.columns([1, 2])
            with search_col:
                sel_char = st.selectbox(
                    "캐릭터 선택", char_list, key="char_select"
                )

            char_df = fdf[
                is_character_row(fdf) & (fdf["캐릭터"] == sel_char)
            ].copy()

            if char_df.empty:
                st.info(f"'{sel_char}'의 변경 데이터가 없습니다.")
            else:
                # 요약 메트릭
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("총 변경 수", len(char_df))
                m2.metric("🟢 버프",     (char_df["버프너프"] == "버프").sum())
                m3.metric("🔴 너프",     (char_df["버프너프"] == "너프").sum())
                m4.metric("관련 패치 수", char_df["패치버전"].nunique())

                # 히스토리 타임라인 차트
                st.plotly_chart(
                    chart_char_history_timeline(char_df, sel_char),
                    use_container_width=True,
                )

                # 패치 히스토리 상세 테이블
                st.subheader(f"{sel_char} 패치 히스토리")

                # 버전 정렬
                char_df["_k"] = char_df["패치버전"].apply(version_key)
                char_df = char_df.sort_values(["_k", "스킬"], ascending=[False, True])
                char_df = char_df.drop(columns=["_k"])

                def highlight_bn(row):
                    if row["구분"] == "버프":
                        return ["background-color: #D5F5E3"] * len(row)
                    if row["구분"] == "너프":
                        return ["background-color: #FADBD8"] * len(row)
                    return [""] * len(row)

                display_df = char_df[
                    ["패치버전", "유형", "스킬", "항목", "변경전", "변경후", "버프너프"]
                ].rename(columns={"버프너프": "구분"}).reset_index(drop=True)

                st.dataframe(
                    display_df.style.apply(
                        lambda row: highlight_bn(row), axis=1
                    ),
                    use_container_width=True,
                    height=min(60 + len(display_df) * 35, 500),
                )

                # 스킬별 항목 변화 수치 추이 (숫자값인 경우만)
                st.markdown("---")
                st.subheader("항목별 수치 변화 추이")

                # 단순 숫자인 변경전/후만 추출
                numeric_mask = (
                    char_df["변경전"].str.match(r"^\d+\.?\d*$", na=False) &
                    char_df["변경후"].str.match(r"^\d+\.?\d*$", na=False)
                )
                numeric_df = char_df[numeric_mask].copy()

                if numeric_df.empty:
                    st.caption("단순 수치 변화 데이터가 없습니다. (복합 수식 포함 항목 제외)")
                else:
                    numeric_df["변경전_n"] = numeric_df["변경전"].astype(float)
                    numeric_df["변경후_n"] = numeric_df["변경후"].astype(float)
                    numeric_df["레이블"] = numeric_df.apply(
                        lambda r: f"{r['스킬']} {r['항목']}" if r["스킬"] else r["항목"],
                        axis=1,
                    )
                    sel_item = st.selectbox(
                        "항목 선택", numeric_df["레이블"].unique(), key="item_select"
                    )
                    item_df = numeric_df[numeric_df["레이블"] == sel_item].copy()
                    item_df["_k"] = item_df["패치버전"].apply(version_key)
                    item_df = item_df.sort_values("_k")

                    # before/after를 long form으로
                    long = pd.concat([
                        item_df[["패치버전", "변경전_n"]].rename(columns={"변경전_n": "값"}).assign(구분="변경전"),
                        item_df[["패치버전", "변경후_n"]].rename(columns={"변경후_n": "값"}).assign(구분="변경후"),
                    ])

                    fig_trend = px.line(
                        long, x="패치버전", y="값", color="구분",
                        color_discrete_map={"변경전": "#E74C3C", "변경후": "#27AE60"},
                        markers=True,
                        title=f"{sel_char} - {sel_item} 변화 추이",
                    )
                    fig_trend.update_layout(
                        plot_bgcolor="white", paper_bgcolor="white",
                        height=300, margin=dict(t=45, b=30),
                    )
                    st.plotly_chart(fig_trend, use_container_width=True)


if __name__ == "__main__":
    main()
