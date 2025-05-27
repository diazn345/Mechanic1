# Firebase 기반 Streamlit 앱 (보고서 제출 + 수정/삭제 + 고장 대수 입력 + 통계 조회 기능)

import streamlit as st
from datetime import datetime, date
import urllib.parse
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode
from pyzbar.pyzbar import decode
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd

# 🔐 secrets에서 firebase_config 불러오기
firebase_json = json.loads(st.secrets["firebase_config"])

# Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 옵션 (임시로 직접 입력)
authors = ["김정비", "이수리", "박엔지"]
issues = ["모터 불량", "배터리 문제", "IOT 오류"]
parts = [
    "모터", "배터리", "IOT", "컨트롤러", "브레이크 와이어", "배터리 커버락",
    "모터 케이블", "킥스탠드", "핸들바", "스로틀", "기타"
]

# 메뉴 선택
menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "보고서 수정/삭제", "고장 대수 입력", "통계 조회"])

# QR 코드 영상 처리 클래스
class QRProcessor(VideoProcessorBase):
    def __init__(self):
        self.result = None

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        decoded_objs = decode(img)
        for obj in decoded_objs:
            self.result = obj.data.decode("utf-8")
            break
        return frame

# 보고서 제출
if menu == "보고서 제출":
    st.title("🔧 수리 보고서 제출 (Firebase 저장)")

    ctx = webrtc_streamer(
        key="qr",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=QRProcessor,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )

    equipment_id = ""
    if ctx.video_processor and ctx.video_processor.result:
        qr_data = ctx.video_processor.result.strip()
        parsed_url = urllib.parse.urlparse(qr_data)
        if parsed_url.query:
            query_dict = urllib.parse.parse_qs(parsed_url.query)
            equipment_id = query_dict.get("qr", [""])[0]
        else:
            equipment_id = parsed_url.path.strip("/").split("/")[-1]
        st.success(f"✅ 인식된 장비 ID: {equipment_id}")

    # 작성자 선택
    author = st.selectbox("작성자", authors)
    # 장비 ID (QR 코드에서 자동 채움 가능)
    equipment = st.text_input("장비 ID", value=equipment_id)
    # 고장 내용 선택
    issue = st.selectbox("고장 내용", issues)

    # 사용 부품 최대 10개 선택
    st.markdown("### 사용 부품 (최대 10개 선택)")
    selected_parts = []
    for i in range(10):
        part = st.selectbox(f"사용 부품 {i+1}", [""] + parts, key=f"part_{i}")
        if part:
            selected_parts.append(part)
    # 부품 중복 제거 (선택한 부품만 리스트로)
    selected_parts = list(dict.fromkeys(selected_parts))

    if st.button("제출"):
        if not author:
            st.warning("작성자를 선택해주세요.")
        elif not equipment:
            st.warning("장비 ID를 입력해주세요.")
        elif not issue:
            st.warning("고장 내용을 선택해주세요.")
        else:
            report_data = {
                "author": author,
                "equipment_id": equipment,
                "issue": issue,
                "parts": selected_parts,
                "created_at": datetime.now()
            }
            db.collection("repair_reports").add(report_data)
            st.success(f"✅ 감사합니다, {author}님. 보고서가 Firebase에 저장되었습니다!")

# 보고서 수정/삭제
elif menu == "보고서 수정/삭제":
    st.title("✏️ 수리 보고서 수정 및 삭제 (Firebase)")

    selected_author = st.selectbox("작성자 선택", authors)
    reports_ref = db.collection("repair_reports").where("author", "==", selected_author)
    docs = reports_ref.stream()
    reports = [{"id": doc.id, **doc.to_dict()} for doc in docs]

    if reports:
        # 보기 편하게 날짜 문자열로 변환
        def format_report(r):
            created_str = r.get("created_at")
            if created_str and hasattr(created_str, "strftime"):
                created_str = created_str.strftime("%Y-%m-%d %H:%M:%S")
            return f"{r.get('equipment_id', '')} / {r.get('issue', '')} / {created_str}"

        selected_display = st.selectbox(
            "수정/삭제할 보고서 선택",
            [format_report(r) for r in reports],
        )

        selected_report = next(r for r in reports if format_report(r) == selected_display)

        new_equipment = st.text_input("장비 ID", value=selected_report.get("equipment_id", ""))
        new_issue = st.selectbox("고장 내용", issues, index=issues.index(selected_report.get("issue", issues[0])) if selected_report.get("issue") in issues else 0)

        st.markdown("### 사용 부품 (최대 10개 선택)")
        old_parts = selected_report.get("parts", [])
        # 10개 슬롯에 기존 부품 값 채우기
        new_parts = []
        for i in range(10):
            default_part = old_parts[i] if i < len(old_parts) else ""
            part = st.selectbox(f"사용 부품 {i+1}", [""] + parts, index=([""] + parts).index(default_part) if default_part in parts else 0, key=f"edit_part_{i}")
            if part:
                new_parts.append(part)
        new_parts = list(dict.fromkeys(new_parts))  # 중복 제거

        if st.button("수정 저장"):
            db.collection("repair_reports").document(selected_report["id"]).update({
                "equipment_id": new_equipment,
                "issue": new_issue,
                "parts": new_parts,
            })
            st.success("✅ 수정이 저장되었습니다!")

        if st.button("삭제"):
            db.collection("repair_reports").document(selected_report["id"]).delete()
            st.success("🗑️ 보고서가 삭제되었습니다!")
    else:
        st.info("선택한 작성자의 보고서가 없습니다.")

# 고장 대수 입력 (Firebase)
elif menu == "고장 대수 입력":
    st.title("🏕 캠프별 고장 기기 대수 입력 (Firebase)")
    camps = ["내유캠프", "독산캠프", "장안캠프"]
    devices = ["S9", "디어", "W1", "W9", "I9"]
    issues_count = [
        "리어데코 커버", "모터", "배터리 커버락", "브레이크 레버", "브레이크 LED",
        "스로틀", "컨트롤러", "킥스탠드", "핸들바", "IOT", "기타(증상 파악중)"
    ]

    selected_date = st.date_input("📅 입력 날짜 선택", value=date.today())
    date_str = selected_date.strftime("%Y-%m-%d")

    tabs = st.tabs(camps)

    for tab, camp in zip(tabs, camps):
        with tab:
            st.subheader(f"📍 {camp}")
            count_data = []
            for device in devices:
                st.markdown(f"### 🛠 {device}")
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
                st.success(f"✅ {camp}의 고장 대수가 저장되었습니다 (기존 내용 덮어쓰기)")

# 통계 조회 (Firebase)
elif menu == "통계 조회":
    st.title("📊 고장 대수 통계 조회")
    issue_data = db.collection("issue_counts").stream()
    records = [doc.to_dict() for doc in issue_data]

    if not records:
        st.warning("❌ 저장된 고장 대수 데이터가 없습니다.")
    else:
        df = pd.DataFrame(records)
        df["count"] = pd.to_numeric(df["count"], errors="coerce")

        group_mode = st.selectbox("통계 기준 선택", ["날짜별 합계", "캠프별 합계", "기기별 합계", "고장내용별 합계"])

        if group_mode == "날짜별 합계":
            grouped = df.groupby("date")["count"].sum().reset_index()
        elif group_mode == "캠프별 합계":
            grouped = df.groupby("camp")["count"].sum().reset_index()
        elif group_mode == "기기별 합계":
            grouped = df.groupby("device")["count"].sum().reset_index()
        else:
            grouped = df.groupby("issue")["count"].sum().reset_index()

        st.dataframe(grouped)
        st.bar_chart(grouped.set_index(grouped.columns[0]))
