import streamlit as st
from datetime import datetime, date, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import re

# ========== 설정 ==========
ADMIN_PASSWORD = "eogns2951!"
CAMPS = ["내유캠프", "독산캠프", "장안캠프"]
DEVICES = ["S9", "디어", "W1", "W9", "I9"]
ISSUES_COUNT = [
    "리어데코 커버", "모터", "배터리 커버락", "브레이크 레버", "브레이크 LED",
    "스로틀", "컨트롤러", "킥스탠드", "핸들바", "IOT", "기타(증상 파악중)"
]

# ========== Firebase 인증 ==========
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["FIREBASE_CRED"]))
    firebase_admin.initialize_app(cred)
db = firestore.client()

# ========== 옵션 캐싱 ==========
@st.cache_resource(ttl=600)
def get_options():
    def fetch(doc_name):
        doc_ref = db.collection("options").document(doc_name)
        doc = doc_ref.get()
        return doc.to_dict().get(doc_name, []) if doc.exists else []
    return fetch("authors"), fetch("issues"), fetch("parts")
AUTHORS, ISSUES, PARTS = get_options()

# ========== 세션 초기화 ==========
for key, val in [("is_admin", False), ("is_logged_in", False), ("user_name", "")]:
    if key not in st.session_state:
        st.session_state[key] = val

params = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
raw_url = params.get("url", [""])[0] if "url" in params else ""
def extract_equipment_id(url):
    match = re.search(r'(\w{2}\d{4})$', url)
    return match.group(1) if match else ""
default_equipment_id = extract_equipment_id(raw_url or params.get("qr", [""])[0] if "qr" in params else "")

# ========== 로그인 ==========
if not st.session_state.is_logged_in:
    st.title("🚀 캠프 수리 시스템 로그인")
    tab1, tab2 = st.tabs(["일반 사용자", "관리자"])
    with tab1:
        name = st.selectbox("작성자", AUTHORS)
        if st.button("일반 사용자로 로그인"):
            st.session_state.update({"is_logged_in": True, "user_name": name, "is_admin": False})
            st.rerun()
    with tab2:
        pw = st.text_input("관리자 비밀번호", type="password")
        if st.button("관리자로 로그인"):
            if pw == ADMIN_PASSWORD:
                st.session_state.update({"is_logged_in": True, "user_name": "관리자", "is_admin": True})
                st.success("관리자 로그인 성공!")
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    st.stop()

# ========== 메뉴 ==========
st.sidebar.title("메뉴")
menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "보고서 수정/삭제", "고장 대수 입력", "통계 조회", "로그아웃"])

if menu == "로그아웃":
    st.session_state.update({"is_logged_in": False, "is_admin": False, "user_name": ""})
    st.success("로그아웃 되었습니다.")
    st.rerun()

# ========== 보고서 제출 ==========
if menu == "보고서 제출":
    st.title("🔧 수리 보고서 제출")
    name = st.session_state.user_name
    equipment = st.text_input("장비 ID", value=default_equipment_id)
    issue = st.selectbox("고장 내용", ISSUES)
    selected_parts = [st.selectbox(f"사용 부품 {i}", [""] + PARTS, key=f"part_{i}") for i in range(1, 11)]
    selected_parts = [p for p in selected_parts if p]

    if st.button("제출"):
        try:
            report_data = {
                "author": name, "equipment_id": equipment, "issue": issue,
                "parts": selected_parts, "created_at": datetime.now().isoformat()
            }
            db.collection("repair_reports").add(report_data)
            st.success(f"✅ {name}님의 보고서가 저장되었습니다!")
        except Exception as e:
            st.error(f"저장 실패: {e}")

    # --- 보고서 내역 캐싱 (최적화: 1회만 읽기) ---
    @st.cache_data(ttl=120)
    def fetch_reports(admin, user):
        col = db.collection("repair_reports")
        if admin:
            docs = col.order_by("created_at", direction=firestore.Query.DESCENDING).limit(100).stream()
        else:
            docs = col.where("author", "==", user).order_by("created_at", direction=firestore.Query.DESCENDING).limit(50).stream()
        return [doc.to_dict() for doc in docs]
    reports_list = fetch_reports(st.session_state.is_admin, name)
    st.markdown("### 📋 제출된 수리 보고서")
    if reports_list:
        df = pd.DataFrame(reports_list)
        show_cols = ["author", "equipment_id", "issue", "parts", "created_at"] if st.session_state.is_admin else ["equipment_id", "issue", "parts", "created_at"]
        st.dataframe(df[show_cols])
    else:
        st.info("제출된 보고서가 없습니다.")

# ========== 보고서 수정/삭제 ==========
if menu == "보고서 수정/삭제":
    st.title("✏️ 보고서 수정 및 삭제")
    author_list = AUTHORS if st.session_state.is_admin else [st.session_state.user_name]
    selected_name = st.selectbox("작성자 선택", author_list)

    @st.cache_data(ttl=60)
    def fetch_my_reports(name):
        return [{"id": doc.id, **doc.to_dict()}
                for doc in db.collection("repair_reports")
                .where("author", "==", name)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(50).stream()]
    reports = fetch_my_reports(selected_name)

    if reports:
        df = pd.DataFrame(reports)
        df["created_at_str"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
        df["parts_str"] = df["parts"].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))

        # 🔍 검색 필터
        search = st.text_input("🔍 장비ID/고장내용/부품/날짜로 검색", "")
        if search:
            mask = df.apply(lambda row: search in row["equipment_id"]
                                         or search in row["issue"]
                                         or search in row["parts_str"]
                                         or search in row["created_at_str"], axis=1)
            df = df[mask]

        # 목록 옵션
        option_list = [
            f"{r['equipment_id']} / {r['issue']} / {r['created_at_str']} / {r['id'][:6]}"
            for _, r in df.iterrows()
        ]
        if option_list:
            selected_display = st.selectbox("수정/삭제할 보고서 선택", option_list)
            selected_report = next(r for r, d in zip(reports, option_list) if d == selected_display)

            new_equipment = st.text_input("장비 ID", value=selected_report["equipment_id"])
            new_issue = st.selectbox("고장 내용", ISSUES, index=ISSUES.index(selected_report["issue"]) if selected_report["issue"] in ISSUES else 0)
            new_parts = []
            for i in range(10):
                current_part = selected_report["parts"][i] if i < len(selected_report["parts"]) else ""
                options_list = [""] + PARTS
                index = options_list.index(current_part) if current_part in options_list else 0
                part = st.selectbox(f"사용 부품 {i+1}", options_list, index=index, key=f"edit_part_{i}")
                new_parts.append(part)
            new_parts = [p for p in new_parts if p]
            if st.button("수정 저장"):
                db.collection("repair_reports").document(selected_report["id"]).update({
                    "equipment_id": new_equipment,
                    "issue": new_issue,
                    "parts": new_parts,
                })
                st.success("✅ 수정 완료")
                st.rerun()
            if st.button("삭제"):
                db.collection("repair_reports").document(selected_report["id"]).delete()
                st.success("🗑️ 삭제 완료")
                st.rerun()
        else:
            st.info("검색 결과가 없습니다.")
    else:
        st.info("선택한 작성자의 보고서가 없습니다.")

# ========== 고장 대수 입력 ==========
if menu == "고장 대수 입력":
    st.title("🏕 캠프별 고장 대수 입력")
    selected_date = st.date_input("날짜 선택", value=date.today())
    date_str = selected_date.strftime("%Y-%m-%d")
    tabs = st.tabs(CAMPS)
    for tab, camp in zip(tabs, CAMPS):
        with tab:
            st.subheader(f"{camp}")
            @st.cache_data(ttl=120)
            def fetch_issue_counts(date_str, camp, user, is_admin):
                q = db.collection("issue_counts").where("date", "==", date_str).where("camp", "==", camp)
                if not is_admin:
                    q = q.where("author", "==", user)
                return {(d.to_dict()["device"], d.to_dict()["issue"]): d.to_dict().get("count", 0) for d in q.stream()}
            exist_dict = fetch_issue_counts(date_str, camp, st.session_state.user_name, st.session_state.is_admin)
            count_data = []
            for device in DEVICES:
                st.markdown(f"#### {device}")
                for issue in ISSUES_COUNT:
                    prev_count = exist_dict.get((device, issue), 0)
                    count = st.number_input(f"{device} - {issue}", min_value=0, step=1, value=int(prev_count), key=f"{camp}_{device}_{issue}")
                    count_data.append({
                        "date": date_str, "camp": camp, "device": device, "issue": issue, "count": count, "author": st.session_state.user_name
                    })
            if st.button(f"{camp} 저장", key=f"save_{camp}"):
                # 배치(Batch) 삭제/저장
                batch = db.batch()
                q = db.collection("issue_counts").where("date", "==", date_str).where("camp", "==", camp)
                if not st.session_state.is_admin:
                    q = q.where("author", "==", st.session_state.user_name)
                for doc in q.stream():
                    batch.delete(doc.reference)
                for row in count_data:
                    if row["count"] > 0:
                        batch.set(db.collection("issue_counts").document(), row)
                batch.commit()
                st.success(f"{camp} 고장 대수 저장 완료")
            # --- 내역 바로 보기 ---
            my_counts = db.collection("issue_counts").where("camp", "==", camp).where("date", "==", date_str)
            if not st.session_state.is_admin:
                my_counts = my_counts.where("author", "==", st.session_state.user_name)
            my_counts_list = [doc.to_dict() for doc in my_counts.stream()]
            if my_counts_list:
                df = pd.DataFrame(my_counts_list)
                show_cols = ["author", "date", "device", "issue", "count"] if st.session_state.is_admin else ["date", "device", "issue", "count"]
                st.dataframe(df[show_cols])
            else:
                st.info(f"{camp} 캠프에 내역이 없습니다.")

# ========== 통계 조회 ==========
if menu == "통계 조회" and st.session_state.is_admin:
    st.title("📊 고장 통계 (관리자 전용)")
    # **최근 30일치만 캐싱**
    min_date = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    @st.cache_data(ttl=120)
    def fetch_issue_stats(min_date):
        return [doc.to_dict() for doc in db.collection("issue_counts").where("date", ">=", min_date).stream()]
    all_records = fetch_issue_stats(min_date)
    if not all_records:
        st.warning("❌ 데이터 없음")
    else:
        df = pd.DataFrame(all_records)
        df["count"] = pd.to_numeric(df["count"], errors="coerce")
        group_mode = st.selectbox("통계 기준", ["날짜별", "캠프별", "기기별", "고장내용별"])
        if group_mode == "날짜별":
            grouped = df.groupby("date")["count"].sum().reset_index()
        elif group_mode == "캠프별":
            grouped = df.groupby("camp")["count"].sum().reset_index()
        elif group_mode == "기기별":
            grouped = df.groupby("device")["count"].sum().reset_index()
        else:
            grouped = df.groupby("issue")["count"].sum().reset_index()
        st.dataframe(grouped)
        st.bar_chart(grouped.set_index(grouped.columns[0]))

        # === 🔍 하루치 상세 포맷 ===
        st.markdown("---")
        st.subheader("🔍 하루치 고장대수 상세 조회 (관리자 전용)")
        sel_date = st.date_input("조회 날짜 선택", value=date.today(), key="조회용날짜")
        camp_options = sorted(df["camp"].dropna().unique())
        if camp_options:
            sel_camp = st.selectbox("캠프 선택", camp_options, key="조회용캠프")
            day_df = df[(df["date"] == sel_date.strftime("%Y-%m-%d")) & (df["camp"] == sel_camp)]
            # 🎯 1️⃣ 기기별 총합(엑셀 양식)
            if st.button("기기별 합계로 보기"):
                result = day_df.groupby("device")["count"].sum().reset_index()
                result.columns = ["기기종류", "총 대수"]
                st.dataframe(result)
            # 🎯 2️⃣ 기기별 + 이슈별 트리형 표 (계층/포맷)
            if st.button("입력양식대로 상세보기"):
                for device in DEVICES:
                    device_df = day_df[day_df["device"] == device]
                    total = device_df["count"].sum()
                    st.markdown(f"**- {device} 총합: {total}대**")
                    for issue in ISSUES_COUNT:
                        row = device_df[device_df["issue"] == issue]
                        if not row.empty and int(row['count'].values[0]) > 0:
                            st.markdown(f"&emsp;• {issue}: {int(row['count'].values[0])}대")
                if day_df.empty:
                    st.info("데이터 없음")

# --- END ---

