#!/usr/bin/env python3
"""
Test script for search_raw_traces function
"""
import os
import sys
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from history_rca.sub_agents.trace_agent.tools import search_raw_traces

def test_search_traces():
    """Test the search_raw_traces function"""

    # Time range: 2025-06-09 09:00:00 to 09:30:00 (UTC)
    start_time = datetime(2025, 6, 9, 9, 0, 0)
    end_time = datetime(2025, 6, 9, 9, 30, 0)

    start_ts = int(start_time.timestamp() * 1_000_000_000)
    end_ts = int(end_time.timestamp() * 1_000_000_000)

    # Test case 1: Search by operation_name
    print("=" * 80)
    print("Test 1: Search by operation_name pattern 'GET.*product'")
    print("=" * 80)

    result = search_raw_traces(
        operation_name="GET.*product",
        time_range=(start_ts, end_ts),
        max_results=5
    )

    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    print(f"Total matched: {result['total_matched']}")
    print(f"Returned: {result['returned']}")
    print("\nSample traces:")
    for i, trace in enumerate(result['traces'][:3], 1):
        print(f"\n--- Trace {i} ---")
        print(f"Timestamp: {trace['timestamp']}")
        print(f"Trace ID: {trace['trace_id']}")
        print(f"Span ID: {trace['span_id']}")
        print(f"Operation: {trace['operation_name']}")
        print(f"Duration: {trace['duration']} ns")
        print(f"Service: {trace['service_name']}")
        print(f"Pod: {trace['pod_name']}")

    # Test case 2: Search by attribute_key
    print("\n" + "=" * 80)
    print("Test 2: Search by attribute_key 'http.status_code'")
    print("=" * 80)

    result2 = search_raw_traces(
        attribute_key="http.status_code",
        time_range=(start_ts, end_ts),
        max_results=10
    )

    print(f"Status: {result2['status']}")
    print(f"Message: {result2['message']}")
    print(f"Total matched: {result2['total_matched']}")
    print(f"Returned: {result2['returned']}")

    # Test case 3: Search by operation_name with attribute_key
    print("\n" + "=" * 80)
    print("Test 3: Search by operation_name 'POST' AND attribute_key 'error'")
    print("=" * 80)

    result3 = search_raw_traces(
        operation_name="POST",
        attribute_key="error",
        time_range=(start_ts, end_ts),
        max_results=5
    )

    print(f"Status: {result3['status']}")
    print(f"Message: {result3['message']}")
    print(f"Total matched: {result3['total_matched']}")
    print(f"Returned: {result3['returned']}")

    # Test case 4: No search criteria (should fail)
    print("\n" + "=" * 80)
    print("Test 4: Test with no search criteria (should fail)")
    print("=" * 80)

    result4 = search_raw_traces(
        time_range=(start_ts, end_ts),
        max_results=10
    )

    print(f"Status: {result4['status']}")
    print(f"Message: {result4['message']}")

    # Test case 5: Search by specific trace_id (if we have one from previous results)
    if result['traces']:
        print("\n" + "=" * 80)
        print("Test 5: Search by specific trace_id")
        print("=" * 80)

        trace_id = result['traces'][0]['trace_id']
        result5 = search_raw_traces(
            trace_id=trace_id,
            time_range=(start_ts, end_ts),
            max_results=20
        )

        print(f"Status: {result5['status']}")
        print(f"Message: {result5['message']}")
        print(f"Total matched: {result5['total_matched']}")
        print(f"Returned: {result5['returned']}")
        print(f"\nAll spans in trace {trace_id}:")
        for i, trace in enumerate(result5['traces'], 1):
            print(f"  {i}. {trace['operation_name']} (duration: {trace['duration']} ns)")

if __name__ == "__main__":
    test_search_traces()
