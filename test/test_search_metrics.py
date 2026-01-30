#!/usr/bin/env python3
"""
Test script for search_raw_metrics function
"""
import os
import sys
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from history_rca.sub_agents.metric_agent.tools import search_raw_metrics

def test_search_metrics():
    """Test the search_raw_metrics function"""

    # Time range: 2025-06-06 10:00:00 to 10:30:00 (UTC)
    start_time = datetime(2025, 6, 6, 10, 0, 0)
    end_time = datetime(2025, 6, 6, 10, 30, 0)

    start_ts = int(start_time.timestamp() * 1_000_000_000)
    end_ts = int(end_time.timestamp() * 1_000_000_000)

    # Test case 1: Search for APM metric (error_ratio) for a specific service
    print("=" * 80)
    print("Test 1: Search for APM metric 'error_ratio' for adservice")
    print("=" * 80)

    result = search_raw_metrics(
        metric_name="error_ratio",
        service_name="adservice",
        time_range=(start_ts, end_ts),
        max_results=10
    )

    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    print(f"Metric Type: {result.get('metric_type', 'N/A')}")
    print(f"Total matched: {result['total_matched']}")
    print(f"Returned: {result['returned']}")
    print("\nSample metrics:")
    for i, metric in enumerate(result['metrics'][:5], 1):
        print(f"\n--- Metric {i} ---")
        print(f"Timestamp: {metric['timestamp']}")
        print(f"Pod: {metric['pod_name']}")
        print(f"Metric: {metric['metric_name']}")
        print(f"Value: {metric['metric_value']}")

    # Test case 2: Search for Infra metric (pod_cpu_usage) for a specific service
    print("\n" + "=" * 80)
    print("Test 2: Search for Infra metric 'pod_cpu_usage' for frontend")
    print("=" * 80)

    result2 = search_raw_metrics(
        metric_name="pod_cpu_usage",
        service_name="frontend",
        time_range=(start_ts, end_ts),
        max_results=10
    )

    print(f"Status: {result2['status']}")
    print(f"Message: {result2['message']}")
    print(f"Metric Type: {result2.get('metric_type', 'N/A')}")
    print(f"Total matched: {result2['total_matched']}")
    print(f"Returned: {result2['returned']}")
    print("\nSample metrics:")
    for i, metric in enumerate(result2['metrics'][:5], 1):
        print(f"  {i}. {metric['timestamp']} - Pod: {metric['pod_name']}, Value: {metric['metric_value']}")

    # Test case 3: Search for APM metric (rrt) without service filter
    print("\n" + "=" * 80)
    print("Test 3: Search for APM metric 'rrt' for all services")
    print("=" * 80)

    result3 = search_raw_metrics(
        metric_name="rrt",
        time_range=(start_ts, end_ts),
        max_results=15
    )

    print(f"Status: {result3['status']}")
    print(f"Message: {result3['message']}")
    print(f"Metric Type: {result3.get('metric_type', 'N/A')}")
    print(f"Total matched: {result3['total_matched']}")
    print(f"Returned: {result3['returned']}")
    print(f"\nUnique pods found: {len(set([m['pod_name'] for m in result3['metrics']]))}")

    # Test case 4: Search for Infra metric (pod_memory_working_set_bytes)
    print("\n" + "=" * 80)
    print("Test 4: Search for Infra metric 'pod_memory_working_set_bytes' for cartservice")
    print("=" * 80)

    result4 = search_raw_metrics(
        metric_name="pod_memory_working_set_bytes",
        service_name="cartservice",
        time_range=(start_ts, end_ts),
        max_results=10
    )

    print(f"Status: {result4['status']}")
    print(f"Message: {result4['message']}")
    print(f"Metric Type: {result4.get('metric_type', 'N/A')}")
    print(f"Total matched: {result4['total_matched']}")
    print(f"Returned: {result4['returned']}")

    # Test case 5: Test with missing metric_name (should fail)
    print("\n" + "=" * 80)
    print("Test 5: Test with missing metric_name (should fail)")
    print("=" * 80)

    result5 = search_raw_metrics(
        metric_name="",
        time_range=(start_ts, end_ts)
    )

    print(f"Status: {result5['status']}")
    print(f"Message: {result5['message']}")

    # Test case 6: Test with non-existent metric
    print("\n" + "=" * 80)
    print("Test 6: Test with non-existent metric 'fake_metric'")
    print("=" * 80)

    result6 = search_raw_metrics(
        metric_name="fake_metric",
        time_range=(start_ts, end_ts)
    )

    print(f"Status: {result6['status']}")
    print(f"Message: {result6['message']}")

if __name__ == "__main__":
    test_search_metrics()
