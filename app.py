import streamlit as st
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode, RTCConfiguration
import numpy as np
import cv2
import pyzbar.pyzbar as pyzbar
import re

# 🔑 관리자 QR코드 값 (실전에서는 firestore/secret 등에서 로드)
ADMIN_QR_CODE = "admin123"

# ✅ Firestore 인증 (딕셔너리 방식만 사용!)
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

# === QR코드 로그인 ===
def qr_login():
    st.header("🔑 QR 코드로 관리자 로그인")
    st.info("관리자 QR 코드를 카메라에 비춰주세요.")

    class QRVideoProcessor(VideoProcessorBase):
        def __init__(self):
            self.last_code = None

        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            decoded = pyzbar.decode(img)
            for obj in decoded:
                qr_val = obj.data.decode("utf-8")
                self.last_code = qr_val
                cv2.rectangle(img, (obj.rect.left, obj.rect.top),
                              (obj.rect.left + obj.rect.width, obj.rect.top + obj.rect.height),
                              (0, 255, 0), 2)
                cv2.putText(img, qr_val, (obj.rect.left, obj.rect.top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            return img

    ctx = webrtc_streamer(
        key="qr_login",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=QRVideoProcessor,
        rtc_configuration=RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}),
        media_stream_constraints={"video": True, "audio": False},
    )

    if ctx.video_processor and ctx.video_processor.last_code:
        qr_val = ctx.video_processor.last_code
        if qr_val == ADMIN_QR_CODE:
            st.session_state.is_admin = True
            st.session_state.is_logged_in = True
            st.session_state.user_name = "관리자"
            st.success("관리자 로그인 성공! 메뉴가 열렸습니다.")
            st.experimental_rerun()
        else:
            st.warning(f"이 QR코드는 권한이 없습니다.({qr_val})")
            # 일반 유저로 로그인하려면 별도 로직 추가

# === 로그인 (관리자/사용자 선택) ===
if not st.session_state.is_logged_in:
    st.title("🚀 캠프 수리 시스템 로그인")
    # 일반 유저는 이름만 선택해서 로그인 (QR 없음)
    st.subheader("일반 사용자 로그인")
    name = st.selectbox("작성자", authors)
    if st.button("일반 사용자로 로그인"):
        st.session_state.is_logged_in = True
        st.session_state.user_name = name
        st.experimental_rerun()
    st.markdown("---")
    qr_login()
    st.stop()

# === 메뉴 및 권한 ===
st.sidebar.title("메뉴")
if st.session_state.is_admin:
    menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "보고서 수정/삭제", "고장 대수 입력", "통계 조회", "로그아웃"])
else:
    menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "로그아웃"])

if menu == "로그아웃":
    st.session_state.is_logged_in = False
    st.session_state.is_admin = False
    st.session_state.user_name = ""
    st.success("로그아웃 되었습니다.")
    st.experimental_rerun()

# === 메뉴별 화면 ===
if menu == "보고서 제출":
    st.title("🔧 수리 보고서 제출")
    name = st.session_state.user_name

    if "scan_mode" not in st.session_state:
        st.session_state.scan_mode = False

    if st.button("📷 QR 스캔하기"):
        st.session_state.scan_mode = not st.session_state.scan_mode

    if st.session_state.scan_mode:
        st.info("카메라가 활성화 되었습니다. (QR 인식은 별도 구현 필요)")
        st.write("※ 실제 QR 코드 인식 로직은 추가 구현 필요합니다.")
    else:
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

if menu == "보고서 수정/삭제" and st.session_state.is_admin:
    st.title("✏️ 보고서 수정 및 삭제")

    selected_name = st.selectbox("작성자 선택", authors)
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
            st.experimental_rerun()

        if st.button("삭제"):
            db.collection("repair_reports").document(selected_report["id"]).delete()
            st.success("🗑️ 삭제 완료")
            st.experimental_rerun()
    else:
        st.info("선택한 작성자의 보고서가 없습니다.")

if menu == "고장 대수 입력" and st.session_state.is_admin:
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

if menu == "통계 조회" and st.session_state.is_admin:
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

