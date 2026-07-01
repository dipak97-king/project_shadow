import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

# Firebase Initialize
if os.getenv("FIREBASE_CREDENTIALS"):
    cred_dict = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

def init_db():
    # Firebase mein initialize ki zaroorat nahi hoti, bas pass kar dein
    pass

def add_worker(phone_number):
    db.collection("workers").document(phone_number).set({"status": "active"})

def get_all_workers():
    docs = db.collection("workers").stream()
    return [doc.id for doc in docs]

def save_session(phone_number, session_string):
    db.collection("sessions").document(phone_number).set({"session_string": session_string})

def get_session(phone_number):
    doc = db.collection("sessions").document(phone_number).get()
    return doc.to_dict().get("session_string") if doc.exists else None

