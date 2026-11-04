import sqlite3
import os
import json
import math
from contextlib import closing

DATABASE = 'users.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    return conn

def search_user(username):
    """Search for a user by username in the database securely using parameterized queries."""
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            query = "SELECT id, username, email, is_active FROM users WHERE username = ?"
            cursor.execute(query, (username,))
            result = cursor.fetchall()
            return result

def load_user_session(session_file_path):
    """Load user session state from a file securely using JSON."""
    if os.path.exists(session_file_path):
        try:
            with open(session_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except (json.JSONDecodeError, IOError):
            return None
    return None

def process_items(items):
    """Process a list of items and return squared values."""
    processed = []
    if items is not None:
        for item in items:
            if item is not None:
                squared = item * item
                processed.append(squared)
    return processed

def calculate_discount(price, discount_percent):
    """Calculate the final price after applying a discount percentage.
    
    Requires a finite non-negative price and a finite discount percentage from 0 to 100.
    Invalid values fail clearly with ValueError.
    """
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price < 0:
        raise ValueError("Price must be a finite non-negative number.")
    
    if not isinstance(discount_percent, (int, float)) or not math.isfinite(discount_percent) or not (0 <= discount_percent <= 100):
        raise ValueError("Discount percentage must be a finite number between 0 and 100.")
        
    final_price = price - price * discount_percent / 100
    return final_price
