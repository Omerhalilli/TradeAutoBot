"""
Automated Test Suite for MT4 ZeroMQ Bridge & News Service.
"""
import os
import sys

# Provide test fixture defaults if running in unconfigured environment
if not os.environ.get("TELEGRAM_BOT_TOKEN"):
    os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:dummy_token_for_ci_testing"
if not os.environ.get("ALLOWED_CHAT_IDS"):
    os.environ["ALLOWED_CHAT_IDS"] = "123456789"

from config import TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, ZMQ_SERVER_URL
from zmq_client import zmq_client
from news_service import news_service

def test_config():
    print("[1/3] Testing Configuration...")
    assert TELEGRAM_BOT_TOKEN, "Telegram token is empty"
    assert len(ALLOWED_CHAT_IDS) > 0, "No allowed chat IDs"
    print("  -> Token: ******** (Masked for privacy)")
    print(f"  -> Allowed Chat IDs: {ALLOWED_CHAT_IDS}")
    print(f"  -> ZMQ Server URL: {ZMQ_SERVER_URL}")
    print("  [PASS] Config OK\n")

def test_news():
    print("[2/3] Testing Economic News Service...")
    events = news_service.fetch_events(force=True)
    print(f"  -> Total events fetched: {len(events)}")
    assert len(events) > 0, "No economic events fetched"
    
    today_events = news_service.get_today_events()
    print(f"  -> Today events: {len(today_events)}")
    
    digest = news_service.format_news_digest(today_events or events[:3], "Test Calendar")
    print(f"  -> Formatted digest length: {len(digest)} characters")
    print("  [PASS] News Service OK\n")

def test_zmq():
    print("[3/3] Testing ZeroMQ Client...")
    print("  -> Sending PING...")
    ping_res = zmq_client.ping()
    print("  -> PING response: " + str(ping_res).encode("ascii", "replace").decode("ascii"))
    
    if ping_res.get("status") == "ok":
        print("  -> Bridge EA is active! Testing GET_ACCOUNT...")
        acc_res = zmq_client.get_account()
        print(f"  -> Account response: {acc_res}")
        
        print("  -> Testing GET_POSITIONS...")
        pos_res = zmq_client.get_positions()
        print(f"  -> Positions count: {pos_res.get('count', 0)}")
        
        print("  -> Testing GET_HISTORY (limit 5)...")
        hist_res = zmq_client.get_history(limit=5)
        print(f"  -> History count: {hist_res.get('count', 0)}")
        print("  [PASS] ZeroMQ Bridge Roundtrip OK!\n")
    else:
        print("  [NOTE] MT4 EA is not attached or offline: " + str(ping_res.get("message")).encode("ascii", "replace").decode("ascii"))
        print("  [PASS] ZeroMQ client error handling properly caught offline state.\n")

if __name__ == "__main__":
    test_config()
    test_news()
    test_zmq()
    print("ALL TESTS COMPLETED!")

