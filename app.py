import streamlit as st
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import re
import io

# 🔑 관리자 비밀번호 (여기만 바꿔주세요!)
ADMIN_PASSWORD = "eogns2951!"

# Firestore 인증 (Cloud 호환)
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

# === 메뉴 및 권한 ===
st.sidebar.title("메뉴")
if st.session_state.is_admin:
    menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "보고서 수정/삭제", "고장 대수 입력", "통계 조회", "로그아웃"])
else:
    menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "고장 대수 입력", "로그아웃"])

if menu == "로그아웃":
    st.session_state.is_logged_in = False
    st.session_state.is_admin = False
    st.session_state.user_name = ""
    st.success("로그아웃 되었습니다.")
    st.rerun()

# === 1. 보고서 제출/조회 ===
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

    st.markdown("### 📋 제출된 수리 보고서 (엑셀 양식)")

    # ---- 관리자 : 전체+필터/검색+엑셀 ----
    if st.session_state.is_admin:
        all_reports = db.collection("repair_reports").stream()
        reports_list = [doc.to_dict() for doc in all_reports]
        if reports_list:
            df = pd.DataFrame(reports_list)
            if "created_at" not in df.columns:
                df["created_at"] = pd.NaT
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            df = df.dropna(subset=["created_at"])
            if not df.empty:
                df = df.sort_values("created_at", ascending=False)
                df["날짜"] = df["created_at"].dt.date.astype(str)
                # 필터 UI
                date_options = df["날짜"].unique()
                select_dates = st.multiselect("날짜 선택", date_options, default=list(date_options)[:1])
                authors_list = sorted(df["author"].unique())
                select_authors = st.multiselect("작성자 선택", authors_list, default=authors_list)
                equipment_kw = st.text_input("장비 ID(검색)", value="")
                issue_kw = st.text_input("고장 내용(검색)", value="")
                parts_kw = st.text_input("부품명(검색)", value="")
                show_df = df.copy()
                if select_dates:
                    show_df = show_df[show_df["날짜"].isin(select_dates)]
                if select_authors:
                    show_df = show_df[show_df["author"].isin(select_authors)]
                if equipment_kw:
                    show_df = show_df[show_df["equipment_id"].str.contains(equipment_kw, na=False, case=False)]
                if issue_kw:
                    show_df = show_df[show_df["issue"].str.contains(issue_kw, na=False, case=False)]
                if parts_kw:
                    show_df = show_df[show_df["parts"].apply(lambda x: any(parts_kw in str(part) for part in x))]
                view_cols = ["author", "equipment_id", "issue", "parts", "created_at"]
                st.dataframe(show_df[view_cols])
                # 엑셀 다운로드
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    show_df[view_cols].to_excel(writer, index=False, sheet_name="보고서내역")
                st.download_button(
                    label="⬇️ 이 표 엑셀(xlsx) 다운로드",
                    data=excel_buffer.getvalue(),
                    file_name=f"repair_reports_filtered.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("유효한 created_at 날짜가 있는 보고서가 없습니다.")
        else:
            st.info("제출된 보고서가 없습니다.")
    # ---- 일반 사용자 : 본인 내역+엑셀 ----
    else:
        user_reports = db.collection("repair_reports").where("author", "==", name).stream()
        user_reports_list = [doc.to_dict() for doc in user_reports]
        if user_reports_list:
            df = pd.DataFrame(user_reports_list)
            if "created_at" not in df.columns:
                df["created_at"] = pd.NaT
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            df = df.dropna(subset=["created_at"])
            if not df.empty:
                df = df.sort_values("created_at", ascending=False)
                view_cols = ["equipment_id", "issue", "parts", "created_at"]
                st.dataframe(df[view_cols])
                # 엑셀
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    df[view_cols].to_excel(writer, index=False, sheet_name="내보고서")
                st.download_button(
                    label="⬇️ 내역 엑셀(xlsx) 다운로드",
                    data=excel_buffer.getvalue(),
                    file_name=f"my_repair_reports.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("유효한 created_at 날짜가 있는 보고서가 없습니다.")
        else:
            st.info("제출된 보고서가 없습니다.")

# === 2. 보고서 수정/삭제 (관리자만) ===
if menu == "보고서 수정/삭제" and st.session_state.is_admin:
    st.title("✏️ 보고서 수정 및 삭제")
    selected_name = st.selectbox("작성자 선택", authors)
    docs = db.collection("repair_reports").where("author", "==", selected_name).stream()
    reports = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    if reports:
        df = pd.DataFrame(reports)
        if "created_at" not in df.columns:
            df["created_at"] = pd.NaT
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df = df.dropna(subset=["created_at"])
        if not df.empty:
            df = df.sort_values("created_at", ascending=False)
            display_list = []
            for r in df.to_dict("records"):
                created_at_str = r["created_at"]
                try:
                    created_at_str = pd.to_datetime(created_at_str).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
                display_list.append(f"{r['equipment_id']} / {r['issue']} / {created_at_str} / {r['id'][:6]}")
            selected_display = st.selectbox("보고서 선택", display_list)
            selected_report = next(r for r, d in zip(df.to_dict("records"), display_list) if d == selected_display)
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
            # 내역표+엑셀
            edit_cols = ["author", "equipment_id", "issue", "parts", "created_at"]
            st.markdown("#### ✏️ 수정/삭제 내역 (엑셀 스타일)")
            st.dataframe(df[edit_cols])
            excel_buffer2 = io.BytesIO()
            with pd.ExcelWriter(excel_buffer2, engine='xlsxwriter') as writer:
                df[edit_cols].to_excel(writer, index=False, sheet_name="수정삭제내역")
            st.download_button(
                label="⬇️ 엑셀(xlsx) 다운로드 (수정/삭제 내역)",
                data=excel_buffer2.getvalue(),
                file_name="repair_reports_edit.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("유효한 created_at 날짜가 있는 보고서가 없습니다.")
    else:
        st.info("선택한 작성자의 보고서가 없습니다.")

# === 3. 고장 대수 입력/조회 ===
if menu == "고장 대수 입력":
    st.title("🏕 캠프별 고장 대수 입력/조회")
    camps = ["내유캠프", "독산캠프", "장안캠프"]
    devices = ["S9", "디어", "W1", "W9", "I9"]
    issues_count = [
        "리어데코 커버", "모터", "배터리 커버락", "브레이크 레버", "브레이크 LED",
        "스로틀", "컨트롤러", "킥스탠드", "핸들바", "IOT", "기타(증상 파악중)"
    ]
    selected_date = st.date_input("날짜 선택", value=date.today())
    date_str = selected_date.strftime("%Y-%m-%d")

    if not st.session_state.is_admin:
        name = st.session_state.user_name
        st.markdown(f"**[{name}] 님의 {date_str} 입력 내역**")
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
                            "author": name,
                            "date": date_str,
                            "camp": camp,
                            "device": device,
                            "issue": issue,
                            "count": count
                        })
                if st.button(f"{camp} 저장", key=f"save_{camp}"):
                    existing = db.collection("issue_counts").where("date", "==", date_str).where("camp", "==", camp).where("author", "==", name).stream()
                    for doc in existing:
                        db.collection("issue_counts").document(doc.id).delete()
                    for row in count_data:
                        db.collection("issue_counts").add(row)
                    st.success(f"{camp} 고장 대수 저장 완료")
        my_counts = db.collection("issue_counts").where("date", "==", date_str).where("author", "==", name).stream()
        my_counts_list = [doc.to_dict() for doc in my_counts]
        if my_counts_list:
            camp_cols = ["author", "date", "camp", "device", "issue", "count"]
            camp_df = pd.DataFrame(my_counts_list)[camp_cols]
            st.markdown("#### 🏕️ 입력내역 (엑셀)")
            st.dataframe(camp_df)
            excel_buffer3 = io.BytesIO()
            with pd.ExcelWriter(excel_buffer3, engine='xlsxwriter') as writer:
                camp_df.to_excel(writer, index=False, sheet_name="고장대수")
            st.download_button(
                label="⬇️ 엑셀(xlsx) 다운로드 (고장대수)",
                data=excel_buffer3.getvalue(),
                file_name=f"my_issue_counts_{date_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("입력 내역이 없습니다.")
    else:
        st.markdown(f"### {date_str} 전체 입력내역 (엑셀)")
        total_counts = db.collection("issue_counts").where("date", "==", date_str).stream()
        total_counts_list = [doc.to_dict() for doc in total_counts]
        if total_counts_list:
            total_df = pd.DataFrame(total_counts_list)
            st.dataframe(total_df)
            st.markdown("#### 1. 캠프별 기기종류별 총 대수 (엑셀)")
            pivot1 = total_df.groupby(["camp", "device"])["count"].sum().unstack().fillna(0).astype(int)
            st.dataframe(pivot1)
            excel_buffer_pivot1 = io.BytesIO()
            with pd.ExcelWriter(excel_buffer_pivot1, engine='xlsxwriter') as writer:
                pivot1.to_excel(writer, sheet_name="캠프별기종")
            st.download_button(
                label="⬇️ 엑셀(xlsx) 다운로드 (캠프별 기종)",
                data=excel_buffer_pivot1.getvalue(),
                file_name=f"camp_device_summary_{date_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.markdown("#### 2. 캠프별 기종·고장내용별 대수 (엑셀)")
            pivot2 = total_df.pivot_table(index=["camp", "device"], columns="issue", values="count", aggfunc="sum", fill_value=0)
            st.dataframe(pivot2)
            excel_buffer_pivot2 = io.BytesIO()
            with pd.ExcelWriter(excel_buffer_pivot2, engine='xlsxwriter') as writer:
                pivot2.to_excel(writer, sheet_name="캠프별기종증상")
            st.download_button(
                label="⬇️ 엑셀(xlsx) 다운로드 (캠프별 기종·증상)",
                data=excel_buffer_pivot2.getvalue(),
                file_name=f"camp_device_issue_{date_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            excel_buffer_raw = io.BytesIO()
            with pd.ExcelWriter(excel_buffer_raw, engine='xlsxwriter') as writer:
                total_df.to_excel(writer, index=False, sheet_name="전체입력")
            st.download_button(
                label="⬇️ 전체 원본 데이터 엑셀(xlsx) 다운로드",
                data=excel_buffer_raw.getvalue(),
                file_name=f"all_issue_counts_{date_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("해당 날짜의 전체 입력 내역이 없습니다.")

# === 4. 통계 조회 (관리자만) ===
if menu == "통계 조회" and st.session_state.is_admin:
    st.title("📊 고장 통계 (엑셀)")
    issue_data = db.collection("issue_counts").stream()
    records = [doc.to_dict() for doc in issue_data]
    if not records:
        st.warning("❌ 데이터 없음")
    else:
        df = pd.DataFrame(records)
        df["count"] = pd.to_numeric(df["count"], errors="coerce")
        st.markdown("#### 1. 캠프별 총 대수")
        grouped_camp = df.groupby("camp")["count"].sum().reset_index()
        st.dataframe(grouped_camp)
        excel_buffer_g1 = io.BytesIO()
        with pd.ExcelWriter(excel_buffer_g1, engine='xlsxwriter') as writer:
            grouped_camp.to_excel(writer, index=False, sheet_name="캠프별합계")
        st.download_button(
            label="⬇️ 엑셀(xlsx) 다운로드 (캠프별합계)",
            data=excel_buffer_g1.getvalue(),
            file_name=f"camp_total.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.markdown("#### 2. 기기별 총 대수")
        grouped_dev = df.groupby("device")["count"].sum().reset_index()
        st.dataframe(grouped_dev)
        excel_buffer_g2 = io.BytesIO()
        with pd.ExcelWriter(excel_buffer_g2, engine='xlsxwriter') as writer:
            grouped_dev.to_excel(writer, index=False, sheet_name="기기별합계")
        st.download_button(
            label="⬇️ 엑셀(xlsx) 다운로드 (기기별합계)",
            data=excel_buffer_g2.getvalue(),
            file_name=f"device_total.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.markdown("#### 3. 고장내용별 총 대수")
        grouped_issue = df.groupby("issue")["count"].sum().reset_index()
        st.dataframe(grouped_issue)
        excel_buffer_g3 = io.BytesIO()
        with pd.ExcelWriter(excel_buffer_g3, engine='xlsxwriter') as writer:
            grouped_issue.to_excel(writer, index=False, sheet_name="고장별합계")
        st.download_button(
            label="⬇️ 엑셀(xlsx) 다운로드 (고장별합계)",
            data=excel_buffer_g3.getvalue(),
            file_name=f"issue_total.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.markdown("#### 4. 날짜별 총 대수")
        grouped_date = df.groupby("date")["count"].sum().reset_index()
        st.dataframe(grouped_date)
        excel_buffer_g4 = io.BytesIO()
        with pd.ExcelWriter(excel_buffer_g4, engine='xlsxwriter') as writer:
            grouped_date.to_excel(writer, index=False, sheet_name="날짜별합계")
        st.download_button(
            label="⬇️ 엑셀(xlsx) 다운로드 (날짜별합계)",
            data=excel_buffer_g4.getvalue(),
            file_name=f"date_total.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
