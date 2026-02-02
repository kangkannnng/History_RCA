"""
Test suite for search_raw_* tools with UUID parameter support

This test file verifies that the enhanced search tools can accept UUID parameter
and automatically fetch time range from df_input_timestamp.
"""

import os
import sys
import pytest
from datetime import datetime

# Add project root to path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ['PROJECT_DIR'] = PROJECT_DIR

from history_rca.sub_agents.trace_agent.tools import search_raw_traces
from history_rca.sub_agents.log_agent.tools import search_raw_logs
from history_rca.sub_agents.metric_agent.tools import search_raw_metrics


class TestSearchToolsWithUUID:
    """Test search tools with UUID parameter"""

    # Use a known UUID from the test dataset
    TEST_UUID = "38ee3d45-82"

    def test_search_raw_traces_with_uuid(self):
        """Test search_raw_traces using UUID parameter"""
        print("\n=== Testing search_raw_traces with UUID ===")

        result = search_raw_traces(
            operation_name=".*",  # Match any operation
            uuid=self.TEST_UUID,
            max_results=5
        )

        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        print(f"UUID: {result.get('uuid', 'N/A')}")
        print(f"Time Range: {result.get('time_range', {})}")
        print(f"Total Matched: {result.get('total_matched', 0)}")
        print(f"Returned: {result.get('returned', 0)}")

        # Assertions
        assert result['status'] == 'success', f"Expected success, got {result['status']}: {result.get('message')}"
        assert result.get('uuid') == self.TEST_UUID, "UUID should be included in result"
        assert 'time_range' in result, "Time range should be included in result"
        assert result['time_range']['start'] is not None, "Start time should not be None"
        assert result['time_range']['end'] is not None, "End time should not be None"

        print("✅ search_raw_traces with UUID test passed!")
        return result

    def test_search_raw_logs_with_uuid(self):
        """Test search_raw_logs using UUID parameter"""
        print("\n=== Testing search_raw_logs with UUID ===")

        result = search_raw_logs(
            service_name="frontend",
            keyword="error|Error",
            uuid=self.TEST_UUID,
            max_results=5
        )

        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        print(f"UUID: {result.get('uuid', 'N/A')}")
        print(f"Time Range: {result.get('time_range', {})}")
        print(f"Total Matched: {result.get('total_matched', 0)}")
        print(f"Returned: {result.get('returned', 0)}")

        # Assertions
        assert result['status'] == 'success', f"Expected success, got {result['status']}: {result.get('message')}"
        assert result.get('uuid') == self.TEST_UUID, "UUID should be included in result"
        assert 'time_range' in result, "Time range should be included in result"
        assert result['time_range']['start'] is not None, "Start time should not be None"
        assert result['time_range']['end'] is not None, "End time should not be None"

        print("✅ search_raw_logs with UUID test passed!")
        return result

    def test_search_raw_metrics_with_uuid(self):
        """Test search_raw_metrics using UUID parameter"""
        print("\n=== Testing search_raw_metrics with UUID ===")

        result = search_raw_metrics(
            metric_name="pod_processes",
            service_name="cartservice",
            uuid=self.TEST_UUID,
            max_results=10
        )

        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        print(f"UUID: {result.get('uuid', 'N/A')}")
        print(f"Metric Type: {result.get('metric_type', 'N/A')}")
        print(f"Time Range: {result.get('time_range', {})}")
        print(f"Total Matched: {result.get('total_matched', 0)}")
        print(f"Returned: {result.get('returned', 0)}")

        # Assertions
        assert result['status'] == 'success', f"Expected success, got {result['status']}: {result.get('message')}"
        assert result.get('uuid') == self.TEST_UUID, "UUID should be included in result"
        assert 'time_range' in result, "Time range should be included in result"
        assert result['time_range']['start'] is not None, "Start time should not be None"
        assert result['time_range']['end'] is not None, "End time should not be None"

        # Check if we got metrics data
        if result.get('returned', 0) > 0:
            print(f"\nSample metrics (first 3):")
            for i, metric in enumerate(result.get('metrics', [])[:3]):
                print(f"  {i+1}. Timestamp: {metric['timestamp']}, Value: {metric['metric_value']}")

        print("✅ search_raw_metrics with UUID test passed!")
        return result

    def test_backward_compatibility_time_range(self):
        """Test that old time_range parameter still works (backward compatibility)"""
        print("\n=== Testing Backward Compatibility with time_range ===")

        # Use the actual time range from the test UUID
        # First get the time range from UUID
        from history_rca.sub_agents.trace_agent.tools import df_input_timestamp

        uuid_match = df_input_timestamp[df_input_timestamp['uuid'].str.contains(self.TEST_UUID, case=False, na=False)]
        if not uuid_match.empty:
            row = uuid_match.iloc[0]
            start_ts = int(row['start_timestamp'])
            end_ts = int(row['end_timestamp'])

            print(f"Using time range from UUID {self.TEST_UUID}")
            print(f"Start: {start_ts}, End: {end_ts}")
        else:
            # Fallback to manual construction if UUID not found
            start_time = datetime(2025, 6, 6, 2, 10, 5)
            end_time = datetime(2025, 6, 6, 2, 34, 5)
            start_ts = int(start_time.timestamp() * 1_000_000_000)
            end_ts = int(end_time.timestamp() * 1_000_000_000)

        result = search_raw_traces(
            operation_name=".*",
            time_range=[start_ts, end_ts],
            max_results=5
        )

        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")

        assert result['status'] == 'success', f"Expected success, got {result['status']}: {result.get('message')}"
        print("✅ Backward compatibility test passed!")
        return result

    def test_error_handling_no_uuid_no_time_range(self):
        """Test error handling when neither uuid nor time_range is provided"""
        print("\n=== Testing Error Handling (No UUID, No time_range) ===")

        result = search_raw_traces(
            operation_name=".*",
            max_results=5
        )

        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")

        assert result['status'] == 'error', "Should return error when neither uuid nor time_range provided"
        assert 'uuid' in result['message'].lower() or 'time_range' in result['message'].lower(), \
            "Error message should mention uuid or time_range"

        print("✅ Error handling test passed!")
        return result

    def test_error_handling_invalid_uuid(self):
        """Test error handling with invalid UUID"""
        print("\n=== Testing Error Handling (Invalid UUID) ===")

        result = search_raw_traces(
            operation_name=".*",
            uuid="invalid-uuid-12345",
            max_results=5
        )

        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")

        # Should return error because UUID not found
        assert result['status'] == 'error', "Should return error for invalid UUID"

        print("✅ Invalid UUID handling test passed!")
        return result


class TestTimeSeriesAnalysis:
    """Test time series analysis for pod_processes metric"""

    TEST_UUID = "38ee3d45-82"

    def test_pod_processes_time_series(self):
        """Test pod_processes metric to check for drops to 0"""
        print("\n=== Testing pod_processes Time Series Analysis ===")

        result = search_raw_metrics(
            metric_name="pod_processes",
            service_name="cartservice",
            uuid=self.TEST_UUID,
            max_results=100  # Get more data points for time series analysis
        )

        print(f"Status: {result['status']}")
        print(f"Total Matched: {result.get('total_matched', 0)}")
        print(f"Returned: {result.get('returned', 0)}")

        if result['status'] == 'success' and result.get('returned', 0) > 0:
            metrics = result.get('metrics', [])

            # Analyze time series
            values = [m['metric_value'] for m in metrics if m['metric_value'] is not None]

            if values:
                min_val = min(values)
                max_val = max(values)

                print(f"\nTime Series Analysis:")
                print(f"  Min value: {min_val}")
                print(f"  Max value: {max_val}")
                print(f"  Total data points: {len(values)}")

                # Check for drops to 0
                zero_count = sum(1 for v in values if v == 0.0)
                if zero_count > 0:
                    print(f"  ⚠️  Found {zero_count} data points with value 0.0 (pod crashed!)")

                    # Find timestamps where pod_processes dropped to 0
                    zero_timestamps = [m['timestamp'] for m in metrics if m['metric_value'] == 0.0]
                    print(f"  Crash timestamps: {zero_timestamps[:5]}")  # Show first 5
                else:
                    print(f"  ✅ No drops to 0 detected (pod stable)")

                # Check for oscillations
                if len(values) > 2:
                    changes = [values[i+1] - values[i] for i in range(len(values)-1)]
                    sign_changes = sum(1 for i in range(len(changes)-1) if changes[i] * changes[i+1] < 0)

                    if sign_changes > len(changes) / 2:
                        print(f"  ⚠️  Detected oscillation pattern (pod repeatedly restarting)")

        print("✅ Time series analysis test completed!")
        return result


def run_all_tests():
    """Run all tests"""
    print("=" * 80)
    print("Running Search Tools with UUID Parameter Tests")
    print("=" * 80)

    test_suite = TestSearchToolsWithUUID()
    time_series_suite = TestTimeSeriesAnalysis()

    try:
        # Test UUID parameter support
        test_suite.test_search_raw_traces_with_uuid()
        test_suite.test_search_raw_logs_with_uuid()
        test_suite.test_search_raw_metrics_with_uuid()

        # Test backward compatibility
        test_suite.test_backward_compatibility_time_range()

        # Test error handling
        test_suite.test_error_handling_no_uuid_no_time_range()
        test_suite.test_error_handling_invalid_uuid()

        # Test time series analysis
        time_series_suite.test_pod_processes_time_series()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)

    except AssertionError as e:
        print("\n" + "=" * 80)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 80)
        raise
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ UNEXPECTED ERROR: {e}")
        print("=" * 80)
        raise


if __name__ == "__main__":
    run_all_tests()
