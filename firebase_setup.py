import firebase_admin
from firebase_admin import credentials, firestore

# Firebase 인증 및 초기화
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

# Firestore 클라이언트
db = firestore.client()
