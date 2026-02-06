"""
System Stats Helper Functions
Manages the systemStats/dashboard document for optimized dashboard queries
"""
from firebase_init import get_db
from datetime import datetime
from google.cloud import firestore

def increment_stat(field: str, value: int = 1):
    """
    Increment a system stat field in systemStats/dashboard document
    
    Args:
        field: Name of the stat field to increment
        value: Amount to increment (can be negative for decrement)
    
    Note: Prevents stats from going below zero when decrementing
    """
    db = get_db()
    stats_ref = db.collection('systemStats').document('dashboard')
    
    try:
        # If decrementing, check current value to prevent negative stats
        if value < 0:
            stats_doc = stats_ref.get()
            if stats_doc.exists:
                current_value = stats_doc.to_dict().get(field, 0)
                # Calculate new value and ensure it doesn't go below 0
                new_value = max(0, current_value + value)
                
                # If the new value would be the same (already at 0), skip update
                if new_value == current_value and current_value == 0:
                    print(f"⚠️ Skipped systemStats.{field}: already at 0, cannot decrement")
                    return
                
                # Update with the safe value
                stats_ref.update({
                    field: new_value,
                    'lastUpdated': datetime.utcnow()
                })
                print(f"✅ Updated systemStats.{field}: {current_value} → {new_value} (safe decrement)")
            else:
                # Document doesn't exist and we're trying to decrement - create with 0
                print(f"⚠️ systemStats/dashboard doesn't exist, cannot decrement {field}, setting to 0")
                stats_ref.set({
                    field: 0,
                    'lastUpdated': datetime.utcnow()
                }, merge=True)
        else:
            # Incrementing - use Firestore Increment for efficiency
            stats_ref.update({
                field: firestore.Increment(value),
                'lastUpdated': datetime.utcnow()
            })
            print(f"✅ Updated systemStats.{field}: +{value}")
    except Exception as e:
        # Document doesn't exist, create it
        if value < 0:
            # Don't create with negative value
            print(f"⚠️ systemStats/dashboard doesn't exist, cannot decrement {field}, setting to 0")
            initial_value = 0
        else:
            initial_value = value
            
        stats_ref.set({
            field: initial_value,
            'lastUpdated': datetime.utcnow()
        }, merge=True)
        print(f"✅ Created systemStats.{field} = {initial_value}")

def decrement_stat(field: str, value: int = 1):
    """Decrement a system stat field"""
    increment_stat(field, -value)

def get_system_stats():
    """Get current system stats from systemStats/dashboard"""
    db = get_db()
    stats_doc = db.collection('systemStats').document('dashboard').get()
    
    if stats_doc.exists:
        return stats_doc.to_dict()
    else:
        # Return default empty stats
        return {
            'totalYears': 0,
            'totalCompanies': 0,
            'completedCompanies': 0,
            'runningCompanies': 0,
            'totalStudents': 0,
            'totalPlaced': 0,
            'totalNotPlaced': 0,
            'totalOffers': 0,
            'lastUpdated': None
        }

def set_stat(field: str, value: int):
    """Set a stat field to a specific value"""
    db = get_db()
    stats_ref = db.collection('systemStats').document('dashboard')
    
    stats_ref.set({
        field: value,
        'lastUpdated': datetime.utcnow()
    }, merge=True)
    print(f"✅ Set systemStats.{field} = {value}")

def initialize_system_stats():
    """
    Initialize systemStats/dashboard from existing data
    This should be called once after deployment or when resetting stats
    """
    db = get_db()
    
    print("🔄 Initializing system stats from existing data...")
    
    # Count years
    years_count = len(list(db.collection('years').stream()))
    print(f"  Years: {years_count}")
    
    # Get all companies and calculate stats
    companies = list(db.collection('companies').stream())
    total_companies = len(companies)
    completed_companies = sum(1 for c in companies if c.to_dict().get('status') == 'completed')
    running_companies = sum(1 for c in companies if c.to_dict().get('status') == 'running')
    print(f"  Companies: {total_companies} (Completed: {completed_companies}, Running: {running_companies})")
    
    # Get all students and calculate stats
    students = list(db.collection('students').stream())
    total_students = len(students)
    
    placed_count = 0
    not_placed_count = 0
    total_offers = 0
    
    for student in students:
        student_data = student.to_dict()
        status = student_data.get('currentStatus', 'not_placed')
        offers = student_data.get('totalOffers', 0)
        
        if status == 'placed':
            placed_count += 1
        else:
            not_placed_count += 1
        
        total_offers += offers
    
    print(f"  Students: {total_students} (Placed: {placed_count}, Not Placed: {not_placed_count})")
    print(f"  Total Offers: {total_offers}")
    
    # Create/Update systemStats/dashboard document
    stats_data = {
        'totalYears': years_count,
        'totalCompanies': total_companies,
        'completedCompanies': completed_companies,
        'runningCompanies': running_companies,
        'totalStudents': total_students,
        'totalPlaced': placed_count,
        'totalNotPlaced': not_placed_count,
        'totalOffers': total_offers,
        'lastUpdated': datetime.utcnow(),
        'initializedAt': datetime.utcnow()
    }
    
    db.collection('systemStats').document('dashboard').set(stats_data)
    
    print("✅ System stats initialized successfully!")
    
    return {
        'success': True,
        'message': 'System stats initialized',
        'stats': stats_data
    }
