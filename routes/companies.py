from flask import Blueprint, jsonify, g
from firebase_init import get_db
from utils.auth_decorators import token_required, admin_required
from utils.firestore_counter import count_firestore_read

companies_bp = Blueprint('companies', __name__)

@companies_bp.route('/api/companies', methods=['GET'])
@token_required
@admin_required
def get_companies(current_user):
    try:
        db = get_db()
        companies_ref = db.collection('companies')
        docs = list(companies_ref.stream())
        count_firestore_read(len(docs))  # Count reads
        
        companies_data = []
        for doc in docs:
            company_data = doc.to_dict()
            company_data['companyYearId'] = doc.id
            companies_data.append(company_data)
        
        companies_data.sort(key=lambda x: (x.get('year', 0), x.get('companyName', '')), reverse=True)
        
        return jsonify(companies_data), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch companies data: {str(e)}'}), 500


@companies_bp.route('/api/companies/<company_year_id>', methods=['GET'])
@token_required
@admin_required
def get_company_details(current_user, company_year_id):
    try:
        db = get_db()
        company_doc = db.collection('companies').document(company_year_id).get()
        
        if not company_doc.exists:
            return jsonify({'error': 'Company not found'}), 404
        
        company_data = company_doc.to_dict()
        company_data['companyYearId'] = company_doc.id
        
        placements_ref = db.collection('companies').document(company_year_id).collection('placements')
        placements_docs = placements_ref.stream()
        
        placements_map = {}
        for placement_doc in placements_docs:
            placements_map[placement_doc.id] = placement_doc.to_dict()
        
        company_data['placements'] = placements_map
        
        return jsonify(company_data), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch company details: {str(e)}'}), 500


@companies_bp.route('/api/companies/<company_year_id>/rounds', methods=['GET'])
@token_required
@admin_required
def get_company_rounds(current_user, company_year_id):
    try:
        db = get_db()
        
        company_doc = db.collection('companies').document(company_year_id).get()
        if not company_doc.exists:
            return jsonify({'error': 'Company not found'}), 404
        
        rounds_ref = db.collection('companies').document(company_year_id).collection('rounds')
        rounds_docs = rounds_ref.stream()
        
        rounds_data = []
        for round_doc in rounds_docs:
            round_data = round_doc.to_dict()
            round_data['roundId'] = round_doc.id
            
            data_ref = rounds_ref.document(round_doc.id).collection('data')
            data_docs = data_ref.stream()
            
            data_map = {}
            for data_doc in data_docs:
                data_map[data_doc.id] = data_doc.to_dict()
            
            round_data['data'] = data_map
            rounds_data.append(round_data)
        
        rounds_data.sort(key=lambda x: x.get('roundNumber', 0))
        
        return jsonify(rounds_data), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch rounds data: {str(e)}'}), 500


@companies_bp.route('/api/companies/<company_year_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_company_deprecated(company_year_id):
    """
    DEPRECATED: Delete operations moved to separate microservice
    Use excel_to_delete service (port 5004) instead
    """
    return jsonify({
        'error': 'Delete operations moved to separate service',
        'message': 'Please use DELETE API at http://localhost:5004/api',
        'new_endpoint': f'/api/companies/{company_year_id}',
        'service': 'excel_to_delete'
    }), 410  # 410 Gone - resource permanently moved


@companies_bp.route('/api/companies/<company_year_id>/rounds/<round_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_round_deprecated(current_user, company_year_id, round_id):
    """
    DEPRECATED: Delete operations moved to separate microservice
    Use excel_to_delete service (port 5004) instead
    """
    return jsonify({
        'error': 'Delete operations moved to separate service',
        'message': 'Please use DELETE API at http://localhost:5004/api',
        'new_endpoint': f'/api/companies/{company_year_id}/rounds/{round_id}',
        'service': 'excel_to_delete'
    }), 410  # 410 Gone - resource permanently moved

