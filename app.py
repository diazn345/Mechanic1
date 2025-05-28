import streamlit as st
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd

from streamlit_webrtc import webrtc_streamer, VideoProcessorBase

# Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 옵션 리스트 불러오기
def get_option_list(doc_name):
    doc_ref = db.collection("options").document(doc_name)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get(doc_name, [])
    return []

authors = get_option_list("authors")
issues = get_option_list("issues")
parts = get_option_list("parts")

# URL 파라미터 가져오기 (안전하게 최신 API 사용)
params = st.query_params

raw_url = params.get("url", [""])[0] if "url" in params else ""
if raw_url:
    default_equipment_id = raw_url.rstrip('/').split('/')[-1]
else:
    default_equipment_id = params.get("qr", [""])[0] if "qr" in params else ""

# 메뉴
menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "보고서 수정/삭제", "고장 대수 입력", "통계 조회"])

class DummyVideoProcessor(VideoProcessorBase):
    def recv(self, frame):
        # 단순히 들어오는 프레임 그대로 반환 (여기서 QR 코드 처리 등 추가 가능)
        return frame

def camera_stream():
    webrtc_streamer(key="example", video_processor_factory=DummyVideoProcessor)

# 보고서 제출
if menu == "보고서 제출":
    st.title("🔧 수리 보고서 제출")

    name = st.selectbox("작성자", authors)

    # QR 스캔 버튼 토글용 세션 상태 초기화
    if "scan_mode" not in st.session_state:
        st.session_state.scan_mode = False

    # 스캔 버튼
    if st.button("📷 QR 스캔하기"):
        st.session_state.scan_mode = not st.session_state.scan_mode

    # 스캔 모드일 때만 카메라 실행
    if st.session_state.scan_mode:
        st.info("카메라가 활성화 되었습니다. QR 코드를 보여주세요.")
        camera_stream()
        st.write("※ 실제 QR 코드 인식 로직은 추가 구현 필요합니다.")
    else:
        equipment = st.text_input("장비 ID", value=default_equipment_id)

        issue = st.selectbox("고장 내용", issues)
        selected_parts = [st.selectbox(f"사용 부품 {i}", [""] + parts, key=f"part_{i}") for i in range(1, 11)]

        if st.button("제출"):
            report_data = {
                "author": name,
                "equipment_id": equipment,
                "issue": issue,
                "parts": selected_parts,
                "created_at": datetime.now()
            }
            db.collection("repair_reports").add(report_data)
            st.success(f"✅ {name}님의 보고서가 저장되었습니다!")

# 이하 보고서 수정/삭제, 고장 대수 입력, 통계 조회 부분은 기존 코드 동일

elif menu == "보고서 수정/삭제":
    st.title("✏️ 보고서 수정 및 삭제")

    selected_name = st.selectbox("작성자 선택", authors)
    docs = db.collection("repair_reports").where("author", "==", selected_name).stream()
    reports = [{"id": doc.id, **doc.to_dict()} for doc in docs]

    if reports:
        display_list = []
        for r in reports:
            created_at_str = r["created_at"]
            if hasattr(created_at_str, "strftime"):
                created_at_str = created_at_str.strftime("%Y-%m-%d %H:%M")
            display_list.append(f"{r['equipment_id']} / {r['issue']} / {created_at_str}")

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

        if st.button("수정 저장"):
            db.collection("repair_reports").document(selected_report["id"]).update({
                "equipment_id": new_equipment,
                "issue": new_issue,
                "parts": new_parts,
            })
            st.success("✅ 수정 완료")

        if st.button("삭제"):
            db.collection("repair_reports").document(selected_report["id"]).delete()
            st.success("🗑️ 삭제 완료")
    else:
        st.info("선택한 작성자의 보고서가 없습니다.")

elif menu == "고장 대수 입력":
    st.title("🏕 캠프별 고장 대수 입력")
    camps = ["내유캠프", "독산캠프", "장안캠프"]
    devices = ["S9", "디어", "W1", "W9", "I9"]
    issues_count = [
        "리어데코 커버", "모터", "배터리 커버락", "브레이크 레버", "브레이크 LED",
        "스로틀", "컨트롤러", "킥스탠드", "핸들바", "IOT", "기타(증상 파악중)"
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
                        "count": count
                    })

            if st.button(f"{camp} 저장", key=f"save_{camp}"):
                existing = db.collection("issue_counts").where("date", "==", date_str).where("camp", "==", camp).stream()
                for doc in existing:
                    db.collection("issue_counts").document(doc.id).delete()
                for row in count_data:
                    db.collection("issue_counts").add(row)
                st.success(f"{camp} 고장 대수 저장 완료")

elif menu == "통계 조회":
    st.title("📊 고장 통계")

    issue_data = db.collection("issue_counts").stream()
    records = [doc.to_dict() for doc in issue_data]

    if not records:
        st.warning("❌ 데이터 없음")
    else:
        df = pd.DataFrame(records)
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
