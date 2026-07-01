import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

# Firebase initialize
if os.getenv("FIREBASE_CREDENTIALS"):
    cred_dict = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
    cred = credentials.Certificate(cred_dict)
else:
    # Local testing ke liye
    cred = credentials.Certificate("firebase-key.json")

firebase_admin.initialize_app(cred)
db = firestore.client()

def add_worker(phone_number, session_name):
    # Firestore mein data save
    db.collection("workers").document(phone_number).set({
        "phone_number": phone_number,
        "session_name": session_name,
        "status": "active"
    })

def get_all_workers():
    # Firestore se data fetch
    docs = db.collection("workers").stream()
    return [(doc.id, doc.to_dict()['session_name']) for doc in docs]

def remove_worker(phone_number):
    db.collection("workers").document(phone_number).delete()
