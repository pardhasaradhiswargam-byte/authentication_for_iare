"""
Firestore Read Counter Middleware
Tracks and logs the number of Firestore reads per request
"""
from functools import wraps
from flask import request, g
import time

class FirestoreReadCounter:
    """Context manager to count Firestore reads"""
    
    def __init__(self):
        self.read_count = 0
        self.start_time = None
        self.endpoint = None
    
    def __enter__(self):
        self.read_count = 0
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if self.endpoint:
            print(f"📊 [{self.endpoint}] Firestore Reads: {self.read_count} | Duration: {duration:.2f}s")
        return False
    
    def increment(self, count=1):
        """Increment read counter"""
        self.read_count += count
        return self.read_count


# Global counter instance
_counter = None

def get_read_counter():
    """Get the current request's read counter"""
    return getattr(g, '_read_counter', None)

def init_read_counter(endpoint_name):
    """Initialize read counter for current request"""
    counter = FirestoreReadCounter()
    counter.endpoint = endpoint_name
    g._read_counter = counter
    return counter

def count_reads(count=1):
    """Count Firestore reads for current request"""
    counter = get_read_counter()
    if counter:
        counter.increment(count)


def track_reads(f):
    """Decorator to track reads for an endpoint"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Initialize counter
        endpoint = f"{request.method} {request.path}"
        counter = init_read_counter(endpoint)
        
        with counter:
            result = f(*args, **kwargs)
        
        return result
    
    return decorated_function


# Monkey-patch common Firestore operations to auto-count
def patch_firestore_client(db):
    """Patch Firestore client to automatically count reads"""
    original_get = db.collection.__class__.get
    original_stream = db.collection.__class__.stream
    
    def patched_get(self, *args, **kwargs):
        result = original_get(self, *args, **kwargs)
        count_reads(1)
        return result
    
    def patched_stream(self, *args, **kwargs):
        result = original_stream(self, *args, **kwargs)
        # Convert to list to count
        items = list(result)
        count_reads(len(items))
        # Return iterator
        return iter(items)
    
    db.collection.__class__.get = patched_get
    db.collection.__class__.stream = patched_stream
