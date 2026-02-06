import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv

load_dotenv()

# Global DB client instance
_db_client = None

def initialize_firebase():
    try:
        cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
        if not cred_path or not os.path.exists(cred_path):
            raise Exception(f"Firebase credentials file not found at: {cred_path}")
        
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("✓ Firebase initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Firebase initialization failed: {e}")
        return False

def get_db():
    """Get or initialize Firestore client (Singleton)"""
    global _db_client
    if _db_client is None:
        try:
            _db_client = firestore.client()
        except Exception as e:
            print(f"Error initializing Firestore client: {e}")
            raise e
    return _db_client

def get_user_by_username(username):
    db = get_db()
    users_ref = db.collection('users')
    query = users_ref.where('username', '==', username).limit(1)
    docs = query.stream()
    
    for doc in docs:
        user_data = doc.to_dict()
        user_data['id'] = doc.id
        return user_data
    return None

def get_user_by_id(user_id):
    db = get_db()
    doc = db.collection('users').document(user_id).get()
    if doc.exists:
        user_data = doc.to_dict()
        user_data['id'] = doc.id
        return user_data
    return None

def create_user(username, password_hash, role='student'):
    db = get_db()
    user_data = {
        'username': username,
        'password': password_hash,
        'role': role,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    doc_ref = db.collection('users').add(user_data)
    return doc_ref[1].id

def get_all_users():
    db = get_db()
    users_ref = db.collection('users')
    docs = users_ref.stream()
    
    users = []
    for doc in docs:
        user_data = doc.to_dict()
        user_data['id'] = doc.id
        user_data.pop('password', None)
        users.append(user_data)
    return users

def update_user_role(user_id, new_role):
    db = get_db()
    db.collection('users').document(user_id).update({'role': new_role})
    return True

def delete_user(user_id):
    db = get_db()
    db.collection('users').document(user_id).delete()
    return True

def get_user_by_refresh_token(refresh_token):
    db = get_db()
    users_ref = db.collection('users')
    query = users_ref.where('refresh_token', '==', refresh_token).limit(1)
    docs = query.stream()
    
    for doc in docs:
        user_data = doc.to_dict()
        user_data['id'] = doc.id
        return user_data
    return None

def update_user_refresh_token(user_id, refresh_token):
    db = get_db()
    db.collection('users').document(user_id).update({'refresh_token': refresh_token})
    return True
