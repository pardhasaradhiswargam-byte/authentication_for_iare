"""
Middleware helper to count Firestore reads
Add this to any route that performs Firestore operations
"""
from flask import g

def count_firestore_read(count=1):
    """
    Count Firestore reads for the current request
    Usage: count_firestore_read(1) for single read
           count_firestore_read(len(docs)) for multiple reads
    """
    current = getattr(g, 'firestore_reads', 0)
    g.firestore_reads = current + count
    return g.firestore_reads
