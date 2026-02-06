"""
Student Deletion Service

Handles cascading deletion of student records across all collections
with optimized Firestore read operations.
"""

import logging
from typing import Dict, Any
from firebase_init import get_db
from google.cloud import firestore
from flask import current_app

logger = logging.getLogger(__name__)


def delete_student_cascade(student_id: str) -> Dict[str, Any]:
    """
    Delete a student and cascade updates to all related collections.
    
    Optimized to minimize Firestore reads using:
    - Batch operations where possible
    - Targeted queries instead of full scans
        
    Returns:
        Summary of deletion operations
        
    Raises:
        ValueError: If student not found
        Exception: If deletion fails
    """
    db = get_db()
    
    # Track statistics for response
    stats = {
        'companiesAffected': 0,
        'roundsDeleted': 0,
        'placementsDeleted': 0,
        'yearsAffected': set(),
        'totalOffers': 0
    }
    
    # 1. Fetch student document (1 read)
    logger.info(f"Fetching student: {student_id}")
    student_ref = db.collection('students').document(student_id)
    student_doc = student_ref.get()
    
    if not student_doc.exists:
        raise ValueError(f"Student {student_id} not found")
    
    student_data = student_doc.to_dict()
    current_status = student_data.get('currentStatus', 'not_placed')
    total_offers = student_data.get('totalOffers', 0)
    company_status = student_data.get('companyStatus', {})
    
    stats['totalOffers'] = total_offers
    
    logger.info(f"Student {student_id}: status={current_status}, offers={total_offers}, companies={len(company_status)}")
    
    # 2. Process each company (optimized batch operations)
    batch = db.batch()
    operation_count = 0
    
    for company_year_id, company_info in company_status.items():
        stats['companiesAffected'] += 1
        year = company_info.get('year')
        if year:
            stats['yearsAffected'].add(year)
        
        was_placed = company_info.get('finalSelection', False)
        
        # Delete from placements if student was placed
        if was_placed:
            placement_ref = (db.collection('companies')
                           .document(company_year_id)
                           .collection('placements')
                           .document(student_id))
            batch.delete(placement_ref)
            operation_count += 1
            stats['placementsDeleted'] += 1
            logger.debug(f"Deleting placement: {company_year_id}/{student_id}")
        
        # Delete from all rounds/data (need to query to find which rounds)
        # Use collection group query for efficiency (1 read per company)
        rounds_ref = (db.collection('companies')
                     .document(company_year_id)
                     .collection('rounds'))
        
        rounds = rounds_ref.stream()
        for round_doc in rounds:
            # Delete student's row from round data
            data_query = (round_doc.reference
                         .collection('data')
                         .where('studentId', '==', student_id)
                         .limit(1))
            
            for data_doc in data_query.stream():
                batch.delete(data_doc.reference)
                operation_count += 1
                stats['roundsDeleted'] += 1
                logger.debug(f"Deleting round data: {company_year_id}/{round_doc.id}/{data_doc.id}")
                
                # Commit batch if limit reached
                if operation_count >= 500:
                    batch.commit()
                    logger.info(f"Committed batch of {operation_count} deletions")
                    batch = db.batch()
                    operation_count = 0
        
        # Update company statistics
        company_ref = db.collection('companies').document(company_year_id)
        update_data = {
            'totalApplied': firestore.Increment(-1),  # Student participated
            'updatedAt': firestore.SERVER_TIMESTAMP
        }
        
        if was_placed:
            update_data['totalPlaced'] = firestore.Increment(-1)
        
        batch.update(company_ref, update_data)
        operation_count += 1
        logger.debug(f"Updating company stats: {company_year_id}")
        
        # Commit if needed
        if operation_count >= 500:
            batch.commit()
            logger.info(f"Committed batch of {operation_count} operations")
            batch = db.batch()
            operation_count = 0
    
    # 3. Update year analytics for each year
    for year in stats['yearsAffected']:
        year_ref = db.collection('years').document(str(year))
        year_update = {
            'totalStudentsParticipated': firestore.Increment(-1),
            'updatedAt': firestore.SERVER_TIMESTAMP
        }
        
        # Update placement count and company-wise stats
        total_placed_in_year = 0
        for company_year_id, company_info in company_status.items():
            if company_info.get('year') == year and company_info.get('finalSelection'):
                total_placed_in_year += 1
                # Update company-wise placement count
                year_update[f'companyWise.{company_year_id}.placed'] = firestore.Increment(-1)
        
        if total_placed_in_year > 0:
            year_update['totalPlaced'] = firestore.Increment(-total_placed_in_year)
        
        batch.update(year_ref, year_update)
        operation_count += 1
        logger.debug(f"Updating year analytics: {year}")
    
    # 4. Delete student document
    batch.delete(student_ref)
    operation_count += 1
    logger.debug(f"Deleting student document: {student_id}")
    
    # Commit remaining operations
    if operation_count > 0:
        batch.commit()
        logger.info(f"Committed final batch of {operation_count} operations")
    
    # 5. Delete student document
    batch = db.batch()
    batch.delete(student_ref)
    batch.commit()
    logger.debug(f"Deleting student document: {student_id}")
    
    # Build response
    result = {
        'message': 'Student deleted successfully',
        'studentId': student_id,
        'studentName': student_data.get('name', 'Unknown'),
        'cascadingUpdates': {
            'companiesAffected': stats['companiesAffected'],
            'roundsDeleted': stats['roundsDeleted'],
            'placementsDeleted': stats['placementsDeleted'],
            'yearsAffected': len(stats['yearsAffected'])
        }
    }
    
    logger.info(f"✅ Student deletion complete: {result}")
    return result
