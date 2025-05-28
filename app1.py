import streamlit as st
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import cv2
import numpy as np
from pyzbar import pyzbar
from streamlit_webrtc import webrtc_streamer

# Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Firestore에서 옵션 리스트 불러오기
def get_option_list(doc_name):
    doc_ref = db.collection("options").document(doc_name)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get(doc_name, [])
    return []

# QR 코드 인식 함수
def detect_qr(frame):
    img = frame.to_ndarray(format="bgr24")
    decoded_objects = pyzbar.decode(img)

    qr_data = None
    for obj in decoded_objects:
        points = obj.polygon
        pts = np.array([(point.x, point.y) for point in points], np.int32)
        pts = pts.reshape((-1, 1, 2))
        cv2.polylines(img, [pts], True, (0, 255, 0), 3)

        qr_data = obj.data.decode("utf-8")
        cv2.putText(img, qr_data, (pts[0][0][0], pts[0][0][1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    if qr_data:
        st.session_state["scanned_qr"] = qr_data

    return img

def video_frame_callback(frame):
    return detect_qr(frame)

# 옵션 리스트 불러오기
authors = get_option_list("authors")
issues = get_option_list("issues")
parts = get_option_list("parts")

# URL 파라미터 가져오기 (최신 방식)
params = st.query_params

# QR URL 혹은 파라미터에서 장비 ID 추출
raw_url = params.get("url", [""])[0] if "url" in params else ""
if raw_url:
    default_equipment_id = raw_url.rstrip('/').split('/')[-1]
else:
    default_equipment_id = params.get("qr", [""])[0] if "qr" in params else ""

# 세션 상태 초기화
if "scanned_qr" not in st.session_state:
    st.session_state["scanned_qr"] = ""
if "camera_on" not in st.session_state:
    st.session_state["camera_on"] = False

menu = st.sidebar.radio("메뉴 선택", ["보고서 제출", "보고서 수정/삭제", "고장 대수 입력", "통계 조회"])

if menu == "보고서 제출":
    st.title("🔧 수리 보고서 제출")

    name = st.selectbox("작성자", authors)
    equipment = st.text_input(
        "장비 ID", 
        value=st.session_state["scanned_qr"] if st.session_state["scanned_qr"] else default_equipment_id
    )
    issue = st.selectbox("고장 내용", issues)
    selected_parts = [st.selectbox(f"사용 부품 {i}", [""] + parts, key=f"part_{i}") for i in range(1, 11)]

    # 카메라 ON/OFF 토글 버튼
    if not st.session_state["camera_on"]:
        if st.button("📷 QR 코드 스캔 시작"):
            st.session_state["camera_on"] = True
    else:
        if st.button("카메라 종료"):
            st.session_state["camera_on"] = False

    # 카메라 켜져 있을 때만 webrtc 실행
    if st.session_state["camera_on"]:
        webrtc_ctx = webrtc_streamer(
            key="qr-code-scanner",
            video_frame_callback=video_frame_callback,
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        )
        if webrtc_ctx.state.playing:
            st.info("카메라가 활성화되었습니다. QR 코드를 비춰주세요.")
        else:
            st.warning("카메라 연결을 확인해주세요.")

    if st.button("제출"):
        if not equipment:
            st.error("장비 ID를 입력하거나 QR 코드를 스캔하세요.")
        else:
            report_data = {
                "author": name,
                "equipment_id": equipment,
                "issue": issue,
                "parts": selected_parts,
                "created_at": datetime.now()
            }
            db.collection("repair_reports").add(report_data)
            st.success(f"✅ {name}님의 보고서가 저장되었습니다!")
            # 제출 후 QR 스캔값 초기화 및 카메라 끄기
            st.session_state["scanned_qr"] = ""
            st.session_state["camera_on"] = False

# 이하 메뉴(보고서 수정/삭제, 고장 대수 입력, 통계 조회) 코드는 이전과 동일하게 유지하세요.
# 생략 가능하지만 필요하면 말씀해 주세요.
