#!/usr/bin/env python3
"""
Test script for search_raw_logs function
"""
import os
import sys
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from history_rca.sub_agents.log_agent.tools import search_raw_logs

def test_search_logs():
    """Test the search_raw_logs function"""

    # Test case 1: Search for "error" in adservice logs
    print("=" * 80)
    print("Test 1: Search for 'error' in adservice logs")
    print("=" * 80)

    # Time range: 2025-06-06 10:00:00 to 10:30:00 (UTC)
    start_time = datetime(2025, 6, 6, 10, 0, 0)
    end_time = datetime(2025, 6, 6, 10, 30, 0)

    start_ts = int(start_time.timestamp() * 1_000_000_000)
    end_ts = int(end_time.timestamp() * 1_000_000_000)

    result = search_raw_logs(
        service_name="adservice",
        keyword="error",
        time_range=(start_ts, end_ts),
        max_results=10
    )

    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    print(f"Total matched: {result['total_matched']}")
    print(f"Returned: {result['returned']}")
    print("\nSample logs:")
    for i, log in enumerate(result['logs'][:3], 1):
        print(f"\n--- Log {i} ---")
        print(f"Timestamp: {log['timestamp']}")
        print(f"Pod: {log['pod']}")
        print(f"Node: {log['node']}")
        print(f"Message: {log['message'][:200]}...")

    # Test case 2: Search with regex pattern
    print("\n" + "=" * 80)
    print("Test 2: Search for regex pattern 'exception|error|fail' in cartservice")
    print("=" * 80)

    result2 = search_raw_logs(
        service_name="cartservice",
        keyword="exception|error|fail",
        time_range=(start_ts, end_ts),
        max_results=15
    )

    print(f"Status: {result2['status']}")
    print(f"Message: {result2['message']}")
    print(f"Total matched: {result2['total_matched']}")
    print(f"Returned: {result2['returned']}")

    # Test case 3: Search in specific pod
    print("\n" + "=" * 80)
    print("Test 3: Search for 'request' in frontend-0 pod")
    print("=" * 80)

    result3 = search_raw_logs(
        service_name="frontend-0",
        keyword="request",
        time_range=(start_ts, end_ts),
        max_results=5
    )

    print(f"Status: {result3['status']}")
    print(f"Message: {result3['message']}")
    print(f"Total matched: {result3['total_matched']}")
    print(f"Returned: {result3['returned']}")

    # Test case 4: Invalid regex
    print("\n" + "=" * 80)
    print("Test 4: Test with invalid regex pattern")
    print("=" * 80)

    result4 = search_raw_logs(
        service_name="adservice",
        keyword="[invalid(regex",
        time_range=(start_ts, end_ts),
        max_results=10
    )

    print(f"Status: {result4['status']}")
    print(f"Message: {result4['message']}")

if __name__ == "__main__":
    test_search_logs()
