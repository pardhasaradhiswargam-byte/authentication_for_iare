from flask import Blueprint, jsonify, request, g
from firebase_init import get_db
from utils.auth_decorators import token_required, admin_required
from utils.firestore_counter import count_firestore_read

students_bp = Blueprint('students', __name__)

@students_bp.route('/api/students', methods=['GET'])
@token_required
@admin_required
def get_students(current_user):
    """
    Get all students with optional filtering.
    Query params:
    - limit (optional): Maximum number of students to return (defaults to ALL)
    - search (optional): Search term for filtering
    """
    try:
        db = get_db()
        students_ref = db.collection('students')
        
        # Get limit parameter (optional, defaults to None = fetch all)
        limit_param = request.args.get('limit')
        limit = int(limit_param) if limit_param else None
        
        # Get search parameter
        search_param = request.args.get('search', '').lower()
        
        # Fetch students
        # For filtering and sorting, it's often easier to fetch all and then process in memory
        # if the dataset size is manageable. For very large datasets, more advanced Firestore queries
        # or pagination would be needed.
        docs = list(students_ref.stream())
        
        count_firestore_read(len(docs))
        
        students_data = []
        for doc in docs:
            student_data = doc.to_dict()
            student_data['studentId'] = doc.id
            
            # Apply search filter if provided
            if search_param:
                name = student_data.get('name', '').lower()
                roll = student_data.get('rollNumber', '').lower()
                email = student_data.get('email', '').lower()
                
                if search_param not in name and search_param not in roll and search_param not in email:
                    continue
            
            # Ensure all required fields exist with safe defaults
            if 'companyStatus' not in student_data:
                student_data['companyStatus'] = {}
            if 'selectedCompanies' not in student_data:
                student_data['selectedCompanies'] = []
            if 'currentStatus' not in student_data:
                student_data['currentStatus'] = 'not_placed'
            if 'totalOffers' not in student_data:
                student_data['totalOffers'] = 0
            
            students_data.append(student_data)
        
        # Sort by name
        students_data.sort(key=lambda x: x.get('name', ''))
        
        # Calculate stats
        total = len(students_data)
        placed = sum(1 for s in students_data if s.get('currentStatus') == 'placed')
        not_placed = sum(1 for s in students_data if s.get('currentStatus') == 'not_placed')
        
        return jsonify({
            'students': students_data,
            'total': total,
            'placed': placed,
            'notPlaced': not_placed,
            'hasMore': False
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch students: {str(e)}'}), 500


@students_bp.route('/api/students/count', methods=['GET'])
@token_required
@admin_required
def get_students_count(current_user):
    try:
        db = get_db()
        docs = list(db.collection('students').stream())
        return jsonify({'total': len(docs)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@students_bp.route('/api/students/stats', methods=['GET'])
@token_required
@admin_required
def get_students_stats(current_user):
    """Get student statistics based on search and filter"""
    try:
        from firebase_init import get_db
        db = get_db()
        
        search_term = request.args.get('search', '').lower()
        status_filter = request.args.get('status', 'all')
        
        # Fetch all students for counting (we need to apply filters)
        all_students = list(db.collection('students').stream())
        
        total_count = 0
        placed_count = 0
        not_placed_count = 0
        total_offers = 0
        
        for doc in all_students:
            student_data = doc.to_dict()
            
            # Apply search filter
            if search_term:
                name_match = search_term in student_data.get('name', '').lower()
                roll_match = search_term in student_data.get('rollNumber', '').lower()
                email_match = search_term in student_data.get('email', '').lower()
                
                if not (name_match or roll_match or email_match):
                    continue
            
            # Apply status filter
            current_status = student_data.get('currentStatus', 'not_placed')
            if status_filter != 'all' and current_status != status_filter:
                continue
            
            # Count this student
            total_count += 1
            if current_status == 'placed':
                placed_count += 1
            else:
                not_placed_count += 1
            
            # Add offers
            total_offers += student_data.get('totalOffers', 0)
        
        avg_offers = round(total_offers / total_count, 2) if total_count > 0 else 0
        
        return jsonify({
            'total': total_count,
            'placed': placed_count,
            'notPlaced': not_placed_count,
            'totalOffers': total_offers,
            'avgOffers': avg_offers
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@students_bp.route('/api/students/<student_id>', methods=['GET'])
@token_required
@admin_required
def get_student(current_user, student_id):
    try:
        db = get_db()
        student_doc = db.collection('students').document(student_id).get()
        if not student_doc.exists:
            return jsonify({'error': 'Student not found'}), 404
        
        student_data = student_doc.to_dict()
        student_data['studentId'] = student_doc.id
        
        # Ensure all required fields exist with safe defaults
        if 'companyStatus' not in student_data:
            student_data['companyStatus'] = {}
        if 'selectedCompanies' not in student_data:
            student_data['selectedCompanies'] = []
        if 'currentStatus' not in student_data:
            student_data['currentStatus'] = 'not_placed'
        if 'totalOffers' not in student_data:
            student_data['totalOffers'] = 0
        
        return jsonify(student_data), 200
    except Exception as e:
        return jsonify({'error': f'Failed to fetch student: {str(e)}'}), 500


@students_bp.route('/api/students', methods=['POST'])
@token_required
@admin_required
def create_student(current_user):
    """
    Create a new student manually.
    
    Request body:
    {
        "name": str (required),
        "rollNumber": str (required, unique),
        "email": str (required)
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        name = data.get('name', '').strip()
        roll_number = data.get('rollNumber', '').strip()
        email = data.get('email', '').strip()
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not roll_number:
            return jsonify({'error': 'Roll number is required'}), 400
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Basic email validation
        if '@' not in email or '.' not in email:
            return jsonify({'error': 'Invalid email format'}), 400
        
        db = get_db()
        
        # Check if roll number already exists
        existing_students = db.collection('students').where(field_path='rollNumber', op_string='==', value=roll_number).limit(1).stream()
        if len(list(existing_students)) > 0:
            return jsonify({'error': f'Student with roll number {roll_number} already exists'}), 409
        
        # Check if email already exists
        existing_email = db.collection('students').where(field_path='email', op_string='==', value=email).limit(1).stream()
        if len(list(existing_email)) > 0:
            return jsonify({'error': f'Student with email {email} already exists'}), 409
        
        # Create student document
        from datetime import datetime
        
        student_data = {
            'name': name,
            'rollNumber': roll_number,
            'email': email,
            'companyStatus': {},
            'selectedCompanies': [],
            'currentStatus': 'not_placed',
            'totalOffers': 0,
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow()
        }
        
        # Add to Firestore
        doc_ref = db.collection('students').document()
        doc_ref.set(student_data)
        
        student_id = doc_ref.id
        
        return jsonify({
            'message': f'Student "{name}" created successfully',
            'student': {
                'studentId': student_id,
                'name': name,
                'rollNumber': roll_number,
                'email': email,
                'currentStatus': 'not_placed',
                'totalOffers': 0
            }
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Failed to create student: {str(e)}'}), 500


@students_bp.route('/api/students/<student_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_student(current_user, student_id):
    """
    Delete a student with cascading updates
    Admin only
    """
    try:
        from services.student_deletion import delete_student_cascade
        
        result = delete_student_cascade(student_id)
        return jsonify(result), 200
        
    except ValueError as e:
        # Student not found
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        # Other errors
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting student {student_id}: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to delete student: {str(e)}'}), 500
