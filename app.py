from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import jwt
import bcrypt
from functools import wraps
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from flask_compress import Compress
from firebase_init import (
    initialize_firebase, 
    get_user_by_username, 
    get_user_by_id,
    create_user, 
    get_all_users, 
    update_user_role, 
    delete_user,
    update_user_refresh_token,
    get_user_by_refresh_token
)

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=[
    'http://localhost:5000', 
    'http://localhost:5173',
    'https://excel-to-db-iare.onrender.com',
    'https://ai-to-db-iare.onrender.com',
    'https://authentication-for-iare.onrender.com',
    'https://frontend-iare-pat.vercel.app'
])
Compress(app)

# ✅ Request tracking middleware - Count Firestore operations
@app.before_request
def before_request():
    """Initialize read counter for each request"""
    from flask import g
    import time
    g.start_time = time.time()
    g.firestore_reads = 0

@app.after_request
def after_request(response):
    """Log request details including Firestore reads"""
    from flask import g
    import time
    
    duration = time.time() - getattr(g, 'start_time', time.time())
    reads = getattr(g, 'firestore_reads', 0)
    
    if request.path.startswith('/api/'):
        pass # print(f"📊 {request.method:6} {request.path:40} | Reads: {reads:4} | {duration*1000:.0f}ms")
    return response

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_REFRESH_SECRET_KEY'] = os.getenv('JWT_REFRESH_SECRET_KEY')
app.config['ACCESS_TOKEN_EXPIRY'] = int(os.getenv('ACCESS_TOKEN_EXPIRY', 900))
app.config['REFRESH_TOKEN_EXPIRY'] = int(os.getenv('REFRESH_TOKEN_EXPIRY', 604800))

# print("🔥 Initializing Firebase...")
if not initialize_firebase():
    pass # print("⚠️  Warning: Firebase initialization failed. Please check your credentials.")

from routes.years import years_bp
from routes.companies import companies_bp
from routes.students import students_bp

app.register_blueprint(years_bp)
app.register_blueprint(companies_bp)
app.register_blueprint(students_bp)

# print("✓ API routes registered and protected with admin authentication")


def generate_access_token(user_id, username, role):
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'exp': datetime.utcnow() + timedelta(seconds=app.config['ACCESS_TOKEN_EXPIRY']),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')

def generate_refresh_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=app.config['REFRESH_TOKEN_EXPIRY']),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, app.config['JWT_REFRESH_SECRET_KEY'], algorithm='HS256')

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Try Authorization header first (for cross-origin requests)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        # Fallback to cookie (for same-origin requests)
        if not token:
            token = request.cookies.get('accessToken')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            current_user = get_user_by_id(data['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        user = get_user_by_username(username)
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        access_token = generate_access_token(user['id'], user['username'], user['role'])
        refresh_token = generate_refresh_token(user['id'])
        
        update_user_refresh_token(user['id'], refresh_token)
        
        response = make_response(jsonify({
            'message': 'Login successful',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user['role']
            },
            'accessToken': access_token,
            'refreshToken': refresh_token
        }))
        
        response.set_cookie(
            'accessToken', 
            access_token, 
            httponly=True,
            max_age=app.config['ACCESS_TOKEN_EXPIRY'],
            samesite='None',  # For Render cross-subdomain
            secure=True,      # HTTPS only
            path='/'
        )
        response.set_cookie(
            'refreshToken', 
            refresh_token, 
            httponly=True,
            max_age=app.config['REFRESH_TOKEN_EXPIRY'],
            samesite='None',  # For Render cross-subdomain
            secure=True,      # HTTPS only
            path='/'
        )

        
        return response, 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/refresh', methods=['POST'])
def refresh():
    try:
        refresh_token = request.cookies.get('refreshToken')
        
        if not refresh_token:
            return jsonify({'error': 'Refresh token missing'}), 401
        
        try:
            data = jwt.decode(refresh_token, app.config['JWT_REFRESH_SECRET_KEY'], algorithms=['HS256'])
            user = get_user_by_id(data['user_id'])
            
            if not user:
                return jsonify({'error': 'User not found'}), 401
            
            if user.get('refresh_token') != refresh_token:
                return jsonify({'error': 'Invalid refresh token'}), 401
            
            new_access_token = generate_access_token(user['id'], user['username'], user['role'])
            
            response = make_response(jsonify({
                'message': 'Token refreshed',
                'accessToken': new_access_token
            }))
            
            response.set_cookie(
                'accessToken', 
                new_access_token, 
                httponly=True,
                max_age=app.config['ACCESS_TOKEN_EXPIRY'],
                samesite='None',
                secure=True,
                path='/'
            )
            
            return response, 200
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Refresh token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid refresh token'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    response = jsonify({'message': 'Logged out successfully'})
    
    # Clear both cookies by setting max_age=0 and empty value
    response.set_cookie(
        'accessToken',
        '',
        max_age=0,
        samesite='None',
        secure=True,
        path='/'
    )
    response.set_cookie(
        'refreshToken',
        '',
        max_age=0,
        samesite='None',
        secure=True,
        path='/'
    )
    
    return response, 200

@app.route('/api/auth/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    try:
        data = request.get_json()
        current_password = data.get('currentPassword')
        new_password = data.get('newPassword')
        
        if not current_password or not new_password:
            return jsonify({'error': 'Current password and new password required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters'}), 400
        
        if not bcrypt.checkpw(current_password.encode('utf-8'), current_user['password'].encode('utf-8')):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        new_password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        from firebase_init import get_db
        db = get_db()
        db.collection('users').document(current_user['id']).update({'password': new_password_hash})
        
        return jsonify({'message': 'Password changed successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    return jsonify({
        'id': current_user['id'],
        'username': current_user['username'],
        'role': current_user['role']
    }), 200

@app.route('/api/users', methods=['GET'])
@token_required
@admin_required
def get_users(current_user):
    try:
        users = get_all_users()
        return jsonify(users), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users', methods=['POST'])
@token_required
@admin_required
def create_new_user(current_user):
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'student')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        if role not in ['student', 'faculty', 'admin']:
            return jsonify({'error': 'Invalid role'}), 400
        
        existing_user = get_user_by_username(username)
        if existing_user:
            return jsonify({'error': 'Username already exists'}), 400
        
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user_id = create_user(username, password_hash, role)
        
        return jsonify({
            'message': 'User created successfully',
            'user': {
                'id': user_id,
                'username': username,
                'role': role
            }
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['PUT'])
@token_required
@admin_required
def update_user(current_user, user_id):
    try:
        data = request.get_json()
        new_role = data.get('role')
        
        if not new_role or new_role not in ['student', 'faculty', 'admin']:
            return jsonify({'error': 'Invalid role'}), 400
        
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        update_user_role(user_id, new_role)
        
        return jsonify({
            'message': 'User updated successfully',
            'user': {
                'id': user_id,
                'username': user['username'],
                'role': new_role
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_user_endpoint(current_user, user_id):
    try:
        if user_id == current_user['id']:
            return jsonify({'error': 'Cannot delete your own account'}), 400
        
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        delete_user(user_id)
        
        return jsonify({'message': 'User deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>/reset-password', methods=['POST'])
@token_required
@admin_required
def reset_user_password(current_user, user_id):
    try:
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        default_password = 'iare'
        password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        from firebase_init import get_db
        db = get_db()
        db.collection('users').document(user_id).update({'password': password_hash})
        
        return jsonify({'message': f"Password for user {user['username']} reset to '{default_password}'"}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Server is running'}), 200

@app.route('/api/summary/dashboard', methods=['GET'])
@token_required
@admin_required
def get_dashboard_summary(current_user):
    """
    Optimized dashboard endpoint using systemStats/dashboard
    BEFORE: 5,000-10,000 reads
    AFTER: 7 reads (99.9% reduction)
    """
    try:
        from firebase_init import get_db
        from utils.system_stats import get_system_stats
        from flask import g
        from google.cloud import firestore  # ✅ Import firestore for Query
        
        db = get_db()
        
        # ✅ 1 READ - Get pre-calculated stats from systemStats/dashboard
        stats = get_system_stats()
        g.firestore_reads = getattr(g, 'firestore_reads', 0) + 1  # Count this read
        
        # ✅ Use CURRENT YEAR (2026) instead of trying to find "latest"
        current_year = 2026
        year_ref = db.collection('years').document(str(current_year))
        year_doc = year_ref.get()
        g.firestore_reads = getattr(g, 'firestore_reads', 0) + 1  # Count read
        
        latest_year = None
        if year_doc.exists:
            latest_year = {
                'year': current_year,
                **year_doc.to_dict()
            }
            print(f"✅ Found year {current_year} data with companyWise")
        else:
            # If no year doc exists, create basic structure
            print(f"⚠️ No year document for {current_year}, will build from companies")
            latest_year = {
                'year': current_year,
                'companyWise': {},
                'totalCompanies': 0,
                'totalPlaced': 0
            }
        
        # ✅ If companyWise is empty, build it from actual companies
        if not latest_year.get('companyWise') or len(latest_year.get('companyWise', {})) == 0:
            print(f"🔧 Building companyWise from companies collection for year {current_year}")
            companies_docs = list(
                db.collection('companies')
                .where('year', '==', current_year)
                .stream()
            )
            g.firestore_reads = getattr(g, 'firestore_reads', 0) + len(companies_docs)
            
            company_wise = {}
            for doc in companies_docs:
                data = doc.to_dict()
                company_wise[doc.id] = {
                    'companyName': data.get('companyName', 'Unknown'),
                    'placed': data.get('totalPlaced', 0),
                    'status': data.get('status', 'unknown')
                }
            
            latest_year['companyWise'] = company_wise
            print(f"✅ Built companyWise with {len(company_wise)} companies")
        
        # ✅ 5 READS - Get only 5 recent companies (sorted by updatedAt)
        recent_companies_docs = list(
            db.collection('companies')
            .order_by('updatedAt', direction=firestore.Query.DESCENDING)
            .limit(5)
            .stream()
        )
        g.firestore_reads = getattr(g, 'firestore_reads', 0) + len(recent_companies_docs)  # Count reads
        
        recent_companies = []
        for doc in recent_companies_docs:
            data = doc.to_dict()
            recent_companies.append({
                'companyYearId': doc.id,
                **data
            })
        
        return jsonify({
            'counts': {
                'years': stats.get('totalYears', 0),
                'companies': stats.get('totalCompanies', 0),
                'students': stats.get('totalStudents', 0)
            },
            'stats': {
                'totalCompanies': stats.get('totalCompanies', 0),
                'completedCompanies': stats.get('completedCompanies', 0),
                'runningCompanies': stats.get('runningCompanies', 0),
                'totalPlaced': stats.get('totalPlaced', 0)
            },
            'latestYear': latest_year,
            'recentCompanies': recent_companies
        }), 200
        
    except Exception as e:
        print(f"❌ Dashboard error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/initialize-stats', methods=['POST'])
@token_required
@admin_required
def initialize_stats_endpoint(current_user):
    """
    Initialize systemStats/dashboard from existing data
    Should be called once after deployment
    """
    try:
        from utils.system_stats import initialize_system_stats
        result = initialize_system_stats()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


if __name__ == '__main__':
    # Use PORT from environment (for Render deployment) or fallback to FLASK_PORT
    port = int(os.environ.get('PORT', os.getenv('FLASK_PORT', 5000)))
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    debug = os.getenv('FLASK_DEBUG', 'False') == 'True'
    
    # print(f"\n{'='*50}")
    # print(f"🚀 JWT Authentication Server")
    # print(f"{'='*50}")
    # print(f"📍 Server running on: http://{host}:{port}")
    # print(f"🔐 Default Admin Credentials:")
    # print(f"   Username: admin")
    # print(f"   Password: admin")
    # print(f"{'='*50}\n")
    
    app.run(host=host, port=port, debug=debug)

