"""Server-side chat logging is completely disabled.
No chat messages, questions, answers, or visitor logs are saved to server disk.
Chat data is maintained strictly client-side in the visitor's browser session.
"""

def ip_hash(ip):
    return ""


def write(record):
    """No-op: Server-side chat persistence is disabled."""
    pass


def cleanup():
    """No-op: No log files to clean."""
    pass


def stats(days=7):
    """Returns clean baseline stats without writing or storing user chats on server."""
    return {
        "questions": 0,
        "total_chats": 0,
        "visitors": 1,
        "active_users": 1,
        "not_found": 0,
        "errors": 0,
        "avg_seconds": 0.0,
        "helpful": 0,
        "not_helpful": 0,
        "recent_unanswered_questions": []
    }
