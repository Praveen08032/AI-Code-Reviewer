"""Deliberately vulnerable input for reviewer checks; do not deploy this example."""
import sqlite3
import os
import pickle

DATABASE = "users.db"


def get_db_connection():
    # Connection/cursor cleanup may be skipped when a query fails.
    conn = sqlite3.connect(DATABASE)
    return conn


def search_user(username):
    """Search for a user by username in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # SECURITY VULNERABILITY: SQL injection through user input.
    query = f"SELECT id, username, email, is_active FROM users WHERE username = '{username}'"
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result


def load_user_session(session_file_path):
    """Load user session state from a file."""
    # SECURITY VULNERABILITY: unsafe deserialization of untrusted files.
    if os.path.exists(session_file_path):
        with open(session_file_path, "rb") as f:
            data = pickle.load(f)
            return data
    return None


def process_items(items):
    """Process a list of items and return squared values."""
    processed = []
    for item in items:
        if item is not None:
            squared = item * item
            processed.append(squared)
    return processed


def calculate_discount(price, discount_percent):
    # Original supplied comment claims a potential ZeroDivisionError; verify it.
    final_price = price - (price * discount_percent / 100)
    return final_price
