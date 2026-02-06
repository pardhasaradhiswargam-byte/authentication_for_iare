from flask import Blueprint, jsonify, g
from firebase_init import get_db
from utils.auth_decorators import token_required, admin_required
from utils.firestore_counter import count_firestore_read

years_bp = Blueprint('years', __name__)

@years_bp.route('/api/years', methods=['GET'])
@token_required
@admin_required
def get_years(current_user):
    try:
        db = get_db()
        years_ref = db.collection('years')
        docs = list(years_ref.stream())
        count_firestore_read(len(docs))  # Count reads
        
        years_data = []
        for doc in docs:
            year_data = doc.to_dict()
            year_data['year'] = int(doc.id)
            years_data.append(year_data)
        
        years_data.sort(key=lambda x: x['year'], reverse=True)
        
        return jsonify(years_data), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch years data: {str(e)}'}), 500
