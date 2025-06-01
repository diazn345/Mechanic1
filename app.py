import streamlit as st
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import re
import io

# 🔑 관리자 비밀번호
ADMIN_PASSWORD = "eogns2951!"

# Firestore 인증
if not firebase_admin._apps:
    firebase_cred_dict = dict(st.secrets["FIREBASE_CRED"])
    cred = credentials.Certificate(firebase_cred_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

def get_option_list(doc_name):
    doc_ref = db.collection("options").document(doc_name)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get(doc_name, [])
    return []

authors = get_option_list("authors")
issues = get_option_list("issues")
parts = get_option_list("parts")

params = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
raw_url = params.get("url", [""])[0] if "url" in params else ""

def extract_equipment_id(url):
    match = re.search(r'(\w{2}\d{4})$', url)
    return match.group(1) if match else ""

default_equipment_id = extract_equipment_id(raw_url or params.get("qr", [""])[0] if "qr" in params else "")

# === 인증 세션 ===
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_name" not in st.session_state:
    st.session_state.user_name = ""

# === 로그인 화면 ===
if not st.session_state.is_logged_in:
    st.title("🚀 캠프 수리 시스템 로그인")
    tab1, tab2 = st.tabs(["일반 사용자", "관리자"])
    with tab1:
        name = st.selectbox("작성자", authors)
        if st.button("일반 사용자로 로그인"):
            st.session_state.is_logged_in = True
            st.session_state.user_name = name
            st.rerun()
    with tab2:
        pw = st.text_input("관리자 비밀번호", type="password")
        if st.button("관리자로 로그인"):
            if pw == ADMIN_PASSWORD:
                st.session_state.is_admin = True
                st.session_state.is_logged_in = True
                st.session_state.user_name = "관리자"
                st.success("관리자 로그인 성공! 메뉴가 열렸습니다.")
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    st.stop()

# === 메뉴(모두 동일 메뉴) ===
st.sidebar.title("메뉴")
menu = st.sidebar.radio(
    "메뉴 선택",
    ["보고서 제출", "보고서 수정/삭제", "고장 대수 입력", "통계 조회", "로그아웃"]
)

if menu == "로그아웃":
    st.session_state.is_logged_in = False
    st.session_state.is_admin = False
    st.session_state.user_name = ""
    st.success("로그아웃 되었습니다.")
    st.rerun()

# === 보고서 제출 ===
if menu == "보고서 제출":
    st.title("🔧 수리 보고서 제출")
    name = st.session_state.user_name

    equipment = st.text_input("장비 ID", value=default_equipment_id)
    issue = st.selectbox("고장 내용", issues)
    selected_parts = [st.selectbox(f"사용 부품 {i}", [""] + parts, key=f"part_{i}") for i in range(1, 11)]
    selected_parts = [p for p in selected_parts if p]  # 빈값 제거

    if st.button("제출"):
        try:
            report_data = {
                "author": name,
                "equipment_id": equipment,
                "issue": issue,
                "parts": selected_parts,
                "created_at": datetime.now().isoformat()
            }
            db.collection("repair_reports").add(report_data)
            st.success(f"✅ {name}님의 보고서가 저장되었습니다!")
        except Exception as e:
            st.error(f"저장 실패: {e}")

    # === 보고서 내역 보기 (관리자: 전체, 일반: 본인 것만) ===
    st.markdown("### 📋 제출된 수리 보고서")
    if st.session_state.is_admin:
        reports_query = db.collection("repair_reports").stream()
        reports_list = [doc.to_dict() for doc in reports_query]
    else:
        reports_query = db.collection("repair_reports").where("author", "==", name).stream()
        reports_list = [doc.to_dict() for doc in reports_query]
    if reports_list:
        df = pd.DataFrame(reports_list)
        # 날짜 정렬
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            df = df.sort_values("created_at", ascending=False)
        if st.session_state.is_admin:
            df = df[["author", "equipment_id", "issue", "parts", "created_at"]]
        else:
            df = df[["equipment_id", "issue", "parts", "created_at"]]
        st.dataframe(df, use_container_width=True)
        # 관리자 엑셀 다운로드
        if st.session_state.is_admin:
            excel_buf = io.BytesIO()
            df.to_excel(excel_buf, index=False)
            st.download_button("엑셀 다운로드", data=excel_buf.getvalue(), file_name="repair_reports.xlsx")
    else:
        st.info("제출된 보고서가 없습니다.")

# === 보고서 수정/삭제 ===
if menu == "보고서 수정/삭제":
    st.title("✏️ 보고서 수정 및 삭제")
    # 관리자는 전체, 일반 사용자는 본인 것만
    if st.session_state.is_admin:
        selected_name = st.selectbox("작성자 선택", ["전체"] + authors)
        if selected_name == "전체":
            docs = db.collection("repair_reports").stream()
        else:
            docs = db.collection("repair_reports").where("author", "==", selected_name).stream()
    else:
        selected_name = st.session_state.user_name
        docs = db.collection("repair_reports").where("author", "==", selected_name).stream()

    reports = [{"id": doc.id, **doc.to_dict()} for doc in docs]

    if reports:
        display_list = []
        for r in reports:
            created_at_str = r["created_at"]
            try:
                created_at_str = pd.to_datetime(created_at_str).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            display_list.append(f"{r['equipment_id']} / {r['issue']} / {created_at_str} / {r['id'][:6]}")
        selected_display = st.selectbox("보고서 선택", display_list)
        selected_report = next(r for r, d in zip(reports, display_list) if d == selected_display)

        new_equipment = st.text_input("장비 ID", value=selected_report["equipment_id"])
        new_issue = st.selectbox("고장 내용", issues, index=issues.index(selected_report["issue"]) if selected_report["issue"] in issues else 0)
        new_parts = []
        for i in range(10):
            current_part = selected_report["parts"][i] if i < len(selected_report["parts"]) else ""
            options_list = [""] + parts
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
        st.info("선택한 작성자의 보고서가 없습니다.")

# === 고장 대수 입력 ===
if menu == "고장 대수 입력":
    st.title("🏕 캠프별 고장 대수 입력")
    camps = ["내유캠프", "독산캠프", "장안캠프"]
    devices = ["S9", "디어", "W1", "W9", "I9", "I7"]
    issues_count = [
        "전일 고장 재고", "현재 고장 재고", "입고수량", "수리완료"
    ]
    selected_date = st.date_input("날짜 선택", value=date.today())
    date_str = selected_date.strftime("%Y-%m-%d")
    tabs = st.tabs(camps)
    for tab, camp in zip(tabs, camps):
        with tab:
            st.subheader(f"{camp}")
            count_data = []
            for device in devices:
                st.markdown(f"#### {device}")
                for issue in issues_count:
                    count = st.number_input(f"{device} - {issue}", min_value=0, step=1, key=f"{camp}_{device}_{issue}")
                    count_data.append({
                        "date": date_str,
                        "camp": camp,
                        "device": device,
                        "issue": issue,
                        "count": count,
                        "author": st.session_state.user_name   # 작성자 정보 저장
                    })
            if st.button(f"{camp} 저장", key=f"save_{camp}"):
                existing = db.collection("issue_counts").where("date", "==", date_str).where("camp", "==", camp).stream()
                for doc in existing:
                    db.collection("issue_counts").document(doc.id).delete()
                for row in count_data:
                    db.collection("issue_counts").add(row)
                st.success(f"{camp} 고장 대수 저장 완료")
            # === 고장대수 내역 보기 (관리자: 전체, 일반: 본인 것만) ===
            st.markdown(f"### 📋 {camp} 고장대수 내역")
            if st.session_state.is_admin:
                my_counts = db.collection("issue_counts").where("camp", "==", camp).where("date", "==", date_str).stream()
                my_counts_list = [doc.to_dict() for doc in my_counts]
            else:
                my_counts = db.collection("issue_counts").where("camp", "==", camp).where("author", "==", st.session_state.user_name).where("date", "==", date_str).stream()
                my_counts_list = [doc.to_dict() for doc in my_counts]
            if my_counts_list:
                df = pd.DataFrame(my_counts_list)
                show_cols = ["author", "date", "device", "issue", "count"] if st.session_state.is_admin else ["date", "device", "issue", "count"]
                st.dataframe(df[show_cols], use_container_width=True)
                # 관리자 엑셀
                if st.session_state.is_admin:
                    excel_buf = io.BytesIO()
                    df[show_cols].to_excel(excel_buf, index=False)
                    st.download_button("엑셀 다운로드", data=excel_buf.getvalue(), file_name=f"{camp}_고장대수_{date_str}.xlsx")
            else:
                st.info(f"{camp} 캠프에 내역이 없습니다.")

# === 통계 조회 (관리자: 캠프-기종-이슈별 피벗+엑셀) ===
if menu == "통계 조회":
    st.title("📊 고장 통계")
    issue_data = db.collection("issue_counts").stream()
    records = [doc.to_dict() for doc in issue_data]
    if not records:
        st.warning("❌ 데이터 없음")
    else:
        df = pd.DataFrame(records)
        df["count"] = pd.to_numeric(df["count"], errors="coerce")
        selected_date = st.date_input("날짜", value=date.today(), key="통계날짜")
        date_str = selected_date.strftime("%Y-%m-%d")
        df = df[df["date"] == date_str]

        # 캠프, 기종, 이슈 리스트 (필요시 수정)
        camps = ["내유캠프", "독산캠프", "장안캠프"]
        devices = ["S9", "디어", "W1", "W9", "I9", "I7"]
        issues = ["전일 고장 재고", "현재 고장 재고", "입고수량", "수리완료"]

        # === 캠프별 피벗표 ===
        for camp in camps:
            st.markdown(f"### {camp}")
            pivot = df[df["camp"] == camp].pivot_table(
                index="issue",
                columns="device",
                values="count",
                aggfunc="sum",
                fill_value=0
            )
            pivot = pivot.reindex(issues)
            pivot = pivot.reindex(columns=devices, fill_value=0)
            pivot.loc["합계"] = pivot.sum()
            pivot["합계"] = pivot.sum(axis=1)
            st.dataframe(pivot, use_container_width=True)

        # === 전체 TOTAL 표 ===
        st.markdown("### TOTAL")
        pivot_total = df.pivot_table(
            index="issue",
            columns="device",
            values="count",
            aggfunc="sum",
            fill_value=0
        )
        pivot_total = pivot_total.reindex(issues)
        pivot_total = pivot_total.reindex(columns=devices, fill_value=0)
        pivot_total.loc["합계"] = pivot_total.sum()
        pivot_total["합계"] = pivot_total.sum(axis=1)
        st.dataframe(pivot_total, use_container_width=True)

        # --- 엑셀 다운로드 ---
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
            for camp in camps:
                temp = df[df["camp"] == camp].pivot_table(
                    index="issue",
                    columns="device",
                    values="count",
                    aggfunc="sum",
                    fill_value=0
                ).reindex(issues).reindex(columns=devices, fill_value=0)
                temp.loc["합계"] = temp.sum()
                temp["합계"] = temp.sum(axis=1)
                temp.to_excel(writer, sheet_name=camp)
            # TOTAL sheet
            pivot_total.to_excel(writer, sheet_name="TOTAL")
        st.download_button("엑셀 다운로드", data=excel_buffer.getvalue(), file_name=f"캠프별_고장통계_{date_str}.xlsx")
