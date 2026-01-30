import pandas as pd
import os
import glob
import random
import numpy as np
import pickle
import re
import warnings
from typing import Optional, List, Tuple, Dict, Set
from collections import defaultdict
from sklearn.ensemble import IsolationForest

# Suppress sklearn version warnings and pandas warnings
warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')
warnings.filterwarnings('ignore', category=FutureWarning)
# Suppress SettingWithCopyWarning
pd.options.mode.chained_assignment = None

PROJECT_DIR = os.getenv('PROJECT_DIR', '.')

input_timestamp_path = os.path.join(PROJECT_DIR, "input/input_timestamp.csv")
df_input_timestamp = pd.read_csv(input_timestamp_path)

# ========== Hyperparameter Configuration ==========
# Training related parameters
SAMPLE_SIZE = 50  # Sample size
RANDOM_SEED = 42  # Random seed
MINUTES_AFTER = 40  # Minutes after anomaly end to consider as normal data
N_ESTIMATORS = 100  # Number of estimators for IsolationForest
CONTAMINATION = 0.01  # Contamination rate for IsolationForest

# Sliding window parameters
WIN_SIZE_SECONDS = 30  # Sliding window size (seconds)
WIN_SIZE_NS = WIN_SIZE_SECONDS * 1000000000  # Sliding window size (nanoseconds)

# Statistical analysis parameters
TOP_N_COMBINATIONS = 10  # Take top N anomaly combinations for detailed analysis
BEIJING_TIMEZONE_OFFSET = 8  # Beijing timezone offset (UTC+8)


def _get_period_info(df_input_timestamp: pd.DataFrame, row_index: int) -> tuple[list[str], int, int]:
    """
    Get matching information for the specified row

    Args:
        df_input_timestamp: DataFrame containing fault start/end timestamps, result from pd.read_csv('input_timestamp.csv')
        row_index: Row index to query

    Returns:
        List of matching files, start_time, end_time
    """    
    import glob

    row = df_input_timestamp.iloc[row_index]
    start_time_hour = row['start_time_hour']
    start_time = row['start_timestamp']
    end_time = row['end_timestamp']
    

    search_pattern = os.path.join(PROJECT_DIR, 'data', 'processed', '*', 'trace-parquet', f'*{start_time_hour}*')
    matching_files = glob.glob(search_pattern, recursive=True)

    return matching_files, start_time, end_time


def _filter_traces_by_timerange(matching_files: list[str], start_time: int, end_time: int, df_trace: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    """
    Filter trace data by time range

    Args:
        matching_files: List of matching file paths
        start_time: Start timestamp
        end_time: End timestamp
        df_trace: DataFrame containing trace data, if None will attempt to read matching files

    Returns:
        DataFrame: Filtered trace data containing only rows within time range; returns None if no matching files
    """
    import pandas as pd

    # Check if matching files were found
    if not matching_files:
        return None

    # Filter data using timestamp
    filtered_df = df_trace[(df_trace['timestamp_ns'] >= start_time) & (df_trace['timestamp_ns'] <= end_time)]

    return filtered_df


def _load_or_train_anomaly_detection_model() -> Optional[Dict[str, Dict[str, IsolationForest]]]:
    """
    Load or train anomaly detection model

    Returns:
        Dict[str, Dict[str, IsolationForest]]: Anomaly detection model dictionary, returns None if failed
    """
    detector_file = os.path.join(PROJECT_DIR, 'models', 'isolation_forest', 'trace_detectors.pkl')

    # If model file already exists, load it directly
    if os.path.exists(detector_file):
        try:
            with open(detector_file, 'rb') as f:
                trace_detectors = pickle.load(f)
            return trace_detectors
        except Exception:
            return None

    # If model file doesn't exist, perform training
    try:
        # Process sampled trace data
        print("Starting to process sampled trace data...")
        merged_file = os.path.join(PROJECT_DIR, 'data', 'merged', 'merged_traces.parquet')

        # Call main processing function to extract specified number of trace files, merge and save as merged_traces.parquet and return to variable merged_traces, extract normal trace data for training iforest from merged_traces, save to train_iforest_normal_traces.pkl and return to variable normal_traces
        merged_traces, normal_traces = _process_trace_samples(
            sample_size=SAMPLE_SIZE, random_seed=RANDOM_SEED, output_path=merged_file, minutes_after=MINUTES_AFTER
        )
        print(f"Processing complete, merged data contains {len(merged_traces)} rows")
        print(f"Normal trace data for training iforest contains {len(normal_traces)} groups")

        # Train anomaly detection model
        trace_detectors, normal_stats = _train_anomaly_detection_model(normal_traces, output_path=detector_file)
        print(f"Anomaly detection model training complete, contains {len(trace_detectors)} detectors")

        return trace_detectors

    except Exception as e:
        print(f"Failed to train anomaly detection model: {e}")
        return None


def _extract_pod_name(process):
    """
    Extract 'name' or 'podName' value from 'tags' list in process dictionary

    Args:
        process: Dictionary containing tags list

    Returns:
        str: Extracted name or podName value, returns None if not found
    """
    if not isinstance(process, dict):
        return None
    
    tags = process.get('tags', [])
    for tag in tags:
        if tag.get('key') == 'name' or tag.get('key') == 'podName':
            return tag.get('value')
    
    return None


def _extract_service_name(process):
    """
    Extract 'serviceName' field from process dictionary

    Args:
        process: Dictionary containing serviceName

    Returns:
        str: Extracted serviceName value, returns None if not found
    """
    if not isinstance(process, dict):
        return None
    return process.get('serviceName', None)


def _extract_node_name(process):
    """
    Extract 'node_name' or 'nodeName' value from 'tags' list in process dictionary

    Args:
        process: Dictionary containing tags list

    Returns:
        str: Extracted node_name or nodeName value, returns None if not found
    """
    if not isinstance(process, dict):
        return None

    tags = process.get('tags', [])
    for tag in tags:
        if tag.get('key') == 'node_name' or tag.get('key') == 'nodeName':
            return tag.get('value')
    return None


def _extract_parent_spanid(ref):
    """
    Extract parent spanID from references

    Args:
        ref: Reference array containing parent spanID

    Returns:
        str: Parent spanID, returns None if not found
    """
    if isinstance(ref, np.ndarray) and ref.size == 1 and isinstance(ref[0], dict) and 'spanID' in ref[0]:
        return ref[0]['spanID']
    return None


def _extract_status_keys_and_values(tags_str: str) -> Tuple[Set[str], Dict[str, str]]:
    """
    Extract status-related keys and corresponding values from tags string

    Returns:
        keys: Set of status-related keys
        values: Mapping from key to value
    """
    try:
        # Extract all keys containing status and their corresponding values
        key_pattern = r"'key':\s*'([^']*status[^']*)'.*?'value':\s*'([^']*)'"
        matches = re.findall(key_pattern, tags_str, re.IGNORECASE)
        
        keys = set()
        values = {}

        for key, value in matches:
            keys.add(key)
            values[key] = value

        return keys, values
    except Exception:
        return set(), {}


def _analyze_status_combinations_in_fault_period(df_filtered_traces: pd.DataFrame) -> str:
    """
    Analyze status.code and status.message combinations during fault period, including detailed context information

    Args:
        df_filtered_traces: Trace data during fault period (already preprocessed, contains pod information)

    Returns:
        CSV format string of status combination statistics, including detailed information like node_name, service_name, parent_pod, child_pod, operation_name
    """
    # Filter rows containing status
    status_logs = df_filtered_traces[df_filtered_traces['tags'].astype(str).str.contains("status", case=False, na=False)]

    if len(status_logs) == 0:
        return ""

    # Collect detailed status combination information
    status_details = []

    # Process each row
    for _, row in status_logs.iterrows():
        keys, values = _extract_status_keys_and_values(str(row['tags']))

        # Check if contains status.code and status.message
        if 'status.code' in keys and 'status.message' in keys:
            status_code = values.get('status.code', 'N/A')
            status_message = values.get('status.message', 'N/A')

            # Filter out normal cases with status.code of 0
            if status_code == '0':
                continue

            # Extract context information
            node_name = row.get('node_name', 'N/A')
            service_name = row.get('service_name', 'N/A')
            parent_pod = row.get('parent_pod', 'N/A')
            child_pod = row.get('child_pod', 'N/A')
            operation_name = row.get('operationName', 'N/A')

            # Service name replacement: redis -> redis-cart
            if service_name == 'redis':
                service_name = 'redis-cart'

            # Handle None values
            node_name = str(node_name) if node_name is not None else "N/A"
            service_name = str(service_name) if service_name is not None else "N/A"
            parent_pod = str(parent_pod) if parent_pod is not None else "N/A"
            child_pod = str(child_pod) if child_pod is not None else "N/A"
            operation_name = str(operation_name) if operation_name is not None else "N/A"

            status_details.append({
                'status_code': status_code,
                'status_message': status_message,
                'node_name': node_name,
                'service_name': service_name,
                'parent_pod': parent_pod,
                'child_pod': child_pod,
                'operation_name': operation_name
            })

    if not status_details:
        return ""

    # Convert to DataFrame
    status_df = pd.DataFrame(status_details)

    # Count occurrences of same combinations
    combination_columns = ['node_name', 'service_name', 'parent_pod', 'child_pod',
                          'operation_name', 'status_code', 'status_message']

    # Group and count
    grouped = status_df.groupby(combination_columns).size().reset_index(name='occurrence_count')

    # Sort by occurrence count in descending order, take top 20 (sort before adding text)
    grouped = grouped.sort_values('occurrence_count', ascending=False).head(20)

    # Add text description to count column
    grouped['occurrence_count_display'] = grouped['occurrence_count'].apply(lambda x: f"occurrence_count:{x}")

    # Delete original numeric column, rename display column
    grouped = grouped.drop('occurrence_count', axis=1)
    grouped = grouped.rename(columns={'occurrence_count_display': 'occurrence_count'})

    # Adjust column order to specified order
    desired_column_order = ['node_name', 'service_name', 'parent_pod', 'child_pod',
                           'operation_name', 'status_code', 'status_message', 'occurrence_count']

    # Ensure only existing columns are included, arranged in specified order
    existing_columns = [col for col in desired_column_order if col in grouped.columns]
    grouped = grouped[existing_columns]

    return grouped.to_csv(index=False)


def _sample_timestamp_data(sample_size: int = 50, random_seed: int = 42) -> pd.DataFrame:
    """
    Randomly sample specified number of samples from input_timestamp.csv

    Args:
        sample_size: Number of samples to extract, default is 50
        random_seed: Random seed, default is 42

    Returns:
        DataFrame: Sampled data
    """
    # Construct path to input_timestamp.csv using absolute path
    input_path = os.path.join(PROJECT_DIR, 'input', 'input_timestamp.csv')
    df_input_timestamp = pd.read_csv(input_path)

    # Set random seed and sample
    random.seed(random_seed)
    if sample_size >= len(df_input_timestamp):
        return df_input_timestamp

    sampled_df = df_input_timestamp.sample(n=sample_size, random_state=random_seed)

    return sampled_df


def _match_trace_files(sampled_df: pd.DataFrame) -> List[str]:
    """
    Match corresponding trace files based on sampled data

    Args:
        sampled_df: Sampled DataFrame

    Returns:
        List[str]: List of matched file paths
    """
    matched_trace_files = []

    for _, row in sampled_df.iterrows():
        start_time_hour = row['@start_time_hour']

        search_pattern = os.path.join(PROJECT_DIR, 'data', 'phaseone', 'processed', '*', 'trace-parquet', f'*{start_time_hour}*')
        matching_file = glob.glob(search_pattern, recursive=True)

        if matching_file:
            matched_trace_files.append(matching_file[0])

    return matched_trace_files


def _merge_trace_files(matched_trace_files: List[str]) -> pd.DataFrame:
    """
    Merge matched trace files

    Args:
        matched_trace_files: List of matched file paths

    Returns:
        DataFrame: Merged data
    """
    all_traces = []

    for file_path in matched_trace_files:
        try:
            df_trace = pd.read_parquet(file_path)

            # Add source file information
            df_trace['source_file'] = os.path.basename(file_path)
            all_traces.append(df_trace)
        except Exception:
            pass

    if not all_traces:
        return pd.DataFrame()

    # Merge all data
    merged_df = pd.concat(all_traces, ignore_index=True)

    return merged_df


def _extract_normal_traces(sampled_df: pd.DataFrame, merged_df: pd.DataFrame, minutes_after: int = 40) -> Dict[str, List[pd.DataFrame]]:
    """
    Extract normal period trace data from merged trace data and build dictionary

    Args:
        sampled_df: Sampled DataFrame containing end_time information
        merged_df: Merged trace data
        minutes_after: Minutes after anomaly end to consider as normal data, default 40 minutes

    Returns:
        Dict[str, List[pd.DataFrame]]: Normal trace data dictionary, key is parent_name-service_name-operationName, value is corresponding duration list
    """

    # Create default dictionary with list values
    normal_traces = defaultdict(list)

    # Conversion factor from nanoseconds to minutes
    ns_to_min = 60 * 1000000000

    # Iterate through each sample
    for _, row in sampled_df.iterrows():
        end_time = row['end_time']
        normal_start_time = end_time  # Normal data start time is anomaly end time
        normal_end_time = normal_start_time + minutes_after * ns_to_min  # Normal data end time

        # Filter normal period data
        normal_df = merged_df[(merged_df['timestamp_ns'] >= normal_start_time) & (merged_df['timestamp_ns'] <= normal_end_time)]

        if normal_df.empty:
            continue

        # Group by parent_pod, child_pod, operationName
        trace_gp = normal_df.groupby(['parent_pod', 'child_pod', 'operationName'])

        # Iterate through each group to build dictionary
        for (src, dst, op), call_df in trace_gp:
            # Handle None values
            src_str = str(src) if src is not None else "None"
            dst_str = str(dst) if dst is not None else "None"
            op_str = str(op) if op is not None else "None"

            name = f"{src_str}_{dst_str}_{op_str}"
            normal_traces[name].append(call_df)

    return normal_traces


def _slide_window(df: pd.DataFrame, win_size: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate mean duration using sliding window

    Args:
        df: DataFrame containing timestamp and duration
        win_size: Window size (nanoseconds)

    Returns:
        Tuple[np.ndarray, np.ndarray]: Window start times and corresponding duration means
    """
    window_start_times, durations = [], []

    time_min, time_max = df['timestamp_ns'].min(), df['timestamp_ns'].max()

    # Sliding window
    i = time_min
    while i < time_max:
        temp_df = df[(df['timestamp_ns'] >= i) & (df['timestamp_ns'] <= i + win_size)]

        if temp_df.empty:
            i += win_size
            continue

        window_start_times.append(i)
        durations.append(temp_df['duration'].mean())
        i += win_size

    return np.array(window_start_times), np.array(durations)


def _train_anomaly_detection_model(normal_traces: Dict[str, List[pd.DataFrame]], output_path: Optional[str] = None) -> Tuple[Dict[str, Dict[str, IsolationForest]], Dict[str, Dict[str, float]]]:
    """
    Train anomaly detection model, only using duration field

    Args:
        normal_traces: Normal trace data dictionary, key is service_name, value is corresponding DataFrame list
        output_path: Output file path, if not None then save model

    Returns:
        Tuple[Dict[str, Dict[str, IsolationForest]], Dict[str, Dict[str, float]]]:
            - Trained anomaly detection model dictionary
            - Normal data statistics dictionary
    """

    # Create anomaly detector dictionary and statistics dictionary
    trace_detectors = {}
    normal_stats = {}

    # Iterate through each service call group
    for name, call_dfs in normal_traces.items():

        # Create anomaly detector for each group
        trace_detectors[name] = {
            'dur_detector': IsolationForest(random_state=RANDOM_SEED, n_estimators=N_ESTIMATORS, contamination=CONTAMINATION)
        }

        # Collect training data
        train_ds = []
        for call_df in call_dfs:
            # Extract duration features using sliding window
            _, durs = _slide_window(call_df, WIN_SIZE_NS)
            train_ds.extend(durs)

        # Skip if not enough training data
        if len(train_ds) == 0:
            continue

        # Calculate statistics for normal data
        train_ds_array = np.array(train_ds)
        normal_stats[name] = {
            'mean': float(np.mean(train_ds_array)),
            'std': float(np.std(train_ds_array)),
            'median': float(np.median(train_ds_array)),
            'min': float(np.min(train_ds_array)),
            'max': float(np.max(train_ds_array)),
            'count': len(train_ds_array)
        }

        # Train duration anomaly detector
        # Set [name]['dur_detector'] to preserve other possible detectors, such as adding ['another_detector'] later
        dur_clf = trace_detectors[name]['dur_detector']
        dur_clf.fit(train_ds_array.reshape(-1, 1))
        trace_detectors[name]['dur_detector'] = dur_clf

    # Save model and statistics
    if output_path:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save model
        with open(output_path, 'wb') as f:
            pickle.dump(trace_detectors, f)

        # Save statistics
        stats_path = output_path.replace('.pkl', '_normal_stats.pkl')
        with open(stats_path, 'wb') as f:
            pickle.dump(normal_stats, f)

    return trace_detectors, normal_stats


def _detect_anomalies(df: pd.DataFrame, trace_detectors: Dict[str, Dict[str, IsolationForest]]) -> List[List[str]]:
    """
    Detect anomalies using trained model

    Args:
        df: Trace data to be detected
        trace_detectors: Trained anomaly detection model dictionary

    Returns:
        List[List[str]]: List of detected anomaly events
    """
    # print("\nStarting anomaly detection...")  # Simplified output

    # Create event list
    events = []

    # Ensure data is sorted by timestamp
    df = df.sort_values(by='timestamp_ns', ascending=True)

    # Group by parent_pod, child_pod, operationName
    gp = df.groupby(['parent_pod', 'child_pod', 'operationName'])

    # Iterate through each group
    for (parent_pod, child_pod, operation_name), call_df in gp:
        # Handle None values
        parent_pod_str = str(parent_pod) if parent_pod is not None else "None"
        child_pod_str = str(child_pod) if child_pod is not None else "None"
        operation_name_str = str(operation_name) if operation_name is not None else "None"

        name = f"{parent_pod_str}_{child_pod_str}_{operation_name_str}"

        # Check if corresponding detector exists
        if name not in trace_detectors:
            continue

        # Extract features using sliding window
        test_window_start_times, test_durations = _slide_window(call_df, WIN_SIZE_NS)

        # Skip if not enough test data
        if len(test_durations) == 0:
            continue

        # Detect duration anomalies
        dur_detector = trace_detectors[name]['dur_detector']
        labels = dur_detector.predict(test_durations.reshape(-1, 1)).tolist()

        # Find all anomaly points
        anomaly_indices = [i for i, label in enumerate(labels) if label == -1]

        if anomaly_indices:
            service_name = call_df['service_name'].iloc[0] if not call_df.empty and 'service_name' in call_df.columns else None
            node_name = call_df['node_name'].iloc[0] if not call_df.empty and 'node_name' in call_df.columns else None
            for idx in anomaly_indices:
                timestamp = test_window_start_times[idx]
                duration = test_durations[idx]
                events.append([timestamp, parent_pod_str, child_pod_str, operation_name_str, 'Duration', duration, service_name, node_name])

    return events


def _process_trace_samples(sample_size: int = 50, random_seed: int = 42, output_path: Optional[str] = None, minutes_after: int = 40) -> Tuple[pd.DataFrame, Dict[str, List[pd.DataFrame]]]:
    """
    Main function for processing trace samples, including sampling, matching and merging

    Args:
        sample_size: Number of samples to extract, default is 50
        random_seed: Random seed, default is 42
        output_path: Output file path, if not None then save merged data
        minutes_after: Minutes after anomaly end to consider as normal data, default 40 minutes

    Returns:
        Tuple[pd.DataFrame, Dict[str, List[pd.DataFrame]]]:
            - Merged data
            - Normal trace data dictionary
    """
    # Step 1: Random sampling
    sampled_df = _sample_timestamp_data(sample_size, random_seed)

    # Step 2: Match files
    matched_files = _match_trace_files(sampled_df)

    # Step 3: Merge files
    merged_df = _merge_trace_files(matched_files)

    # Step 4: Extract pod_name, service_name, node_name
    merged_df['pod_name'] = merged_df['process'].apply(_extract_pod_name)
    merged_df['service_name'] = merged_df['process'].apply(_extract_service_name)
    merged_df['node_name'] = merged_df['process'].apply(_extract_node_name)

    # Step 5: Extract parent spanID
    merged_df['parent_spanID'] = merged_df['references'].apply(_extract_parent_spanid)

    # Step 6: Create spanID to pod_name mapping
    span_to_pod = dict(zip(merged_df['spanID'].tolist(), merged_df['pod_name'].tolist()))

    # Step 7: Extract pod_name corresponding to parent spanID
    merged_df['parent_pod'] = merged_df['parent_spanID'].map(lambda x: span_to_pod.get(x))

    # Step 8: Create spanID to service_name mapping
    span_to_service = dict(zip(merged_df['spanID'].tolist(), merged_df['service_name'].tolist()))

    # Step 9: Extract service_name corresponding to parent spanID
    merged_df['parent_service'] = merged_df['parent_spanID'].map(lambda x: span_to_service.get(x))

    # Step 10: Rename columns to match new naming convention
    merged_df = merged_df.rename(columns={'pod_name': 'child_pod'})

    # Step 11: Sort by timestamp
    merged_df = merged_df.sort_values(by='timestamp_ns')

    # Step 12: Rearrange column order, put related columns together
    columns = merged_df.columns.tolist()

    # Get indices of columns that need to be grouped together
    spanid_idx = columns.index('spanID')
    parent_spanid_idx = columns.index('parent_spanID')
    child_pod_idx = columns.index('child_pod')
    parent_pod_idx = columns.index('parent_pod')
    service_name_idx = columns.index('service_name')
    parent_service_idx = columns.index('parent_service')
    node_name_idx = columns.index('node_name')

    # Remove these columns from list
    for idx in sorted([spanid_idx, parent_spanid_idx, child_pod_idx, parent_pod_idx,
                       service_name_idx, parent_service_idx, node_name_idx], reverse=True):
        columns.pop(idx)

    # Reinsert these columns in specified order
    new_columns = ['parent_spanID', 'spanID', 'parent_pod', 'child_pod',
                   'parent_service', 'service_name', 'node_name'] + columns
    merged_df = merged_df[new_columns]

    # Step 13: Extract normal period trace data
    normal_traces = _extract_normal_traces(sampled_df, merged_df, minutes_after)

    # Step 14: Save data
    if output_path:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        merged_df.to_parquet(output_path)

        # Save normal trace data
        normal_traces_path = os.path.join(os.path.dirname(output_path), 'train_iforest_normal_traces.pkl')
        with open(normal_traces_path, 'wb') as f:
            pickle.dump(normal_traces, f)

    return merged_df, normal_traces


def _load_filtered_trace(df_input_timestamp: pd.DataFrame, index: int) -> Optional[tuple[str, dict, str]]:
    """
    Load and filter trace anomaly data, return CSV format string of top 20 anomaly combinations, three unique value dictionary and status combination statistics

    Args:
        df_input_timestamp: DataFrame containing fault start/end timestamps
        index: Row index to query

    Returns:
        tuple: (filtered_traces_csv, trace_unique_dict, status_combinations_csv)
                - filtered_traces_csv: CSV format string of top 20 anomaly combination statistics, empty string means analysis succeeded but no anomalies
                - trace_unique_dict: {'pod_name': [...], 'service_name': [...], 'node_name': [...]} three unique value dictionary
                - status_combinations_csv: CSV format string of status combination statistics during fault period (top 20)
                Returns None if file doesn't exist or error occurs during processing
    """
    # Load or train anomaly detection model (if model file exists, load directly, otherwise train automatically)
    trace_detectors = _load_or_train_anomaly_detection_model()
    if trace_detectors is None:
        return None  # Model loading failed, return None to indicate error

    # Load normal data statistics
    normal_stats_file = os.path.join(PROJECT_DIR, 'models', 'isolation_forest', 'trace_detectors_normal_stats.pkl')
    normal_stats = {}
    try:
        if os.path.exists(normal_stats_file):
            with open(normal_stats_file, 'rb') as f:
                normal_stats = pickle.load(f)
    except Exception:
        pass  # Statistics loading failure doesn't affect main flow

    # Get trace files and time range during fault period
    matching_files, start_time, end_time = _get_period_info(df_input_timestamp, index)

    try:
        if not matching_files:
            return None  # File doesn't exist, return None to indicate error

        # Read trace data
        df_trace = pd.read_parquet(matching_files[0])

        # Filter data within time range
        df_filtered_traces = _filter_traces_by_timerange(matching_files, start_time, end_time, df_trace)

        if df_filtered_traces is None or len(df_filtered_traces) == 0:
            return ("", {}, "")  # Analysis succeeded but no trace data within time range

        # Preprocess trace data
        # Extract pod_name, service_name, node_name
        df_filtered_traces['pod_name'] = df_filtered_traces['process'].apply(_extract_pod_name)
        df_filtered_traces['service_name'] = df_filtered_traces['process'].apply(_extract_service_name)
        df_filtered_traces['node_name'] = df_filtered_traces['process'].apply(_extract_node_name)

        # Extract parent spanID
        df_filtered_traces['parent_spanID'] = df_filtered_traces['references'].apply(_extract_parent_spanid)

        # Create spanID to pod_name mapping
        span_to_pod = dict(zip(df_filtered_traces['spanID'].tolist(), df_filtered_traces['pod_name'].tolist()))

        # Extract pod_name corresponding to parent spanID
        df_filtered_traces['parent_pod'] = df_filtered_traces['parent_spanID'].map(lambda x: span_to_pod.get(x))

        # Rename pod_name to child_pod
        df_filtered_traces = df_filtered_traces.rename(columns={'pod_name': 'child_pod'})

        # Sort by timestamp
        df_filtered_traces = df_filtered_traces.sort_values(by='timestamp_ns')

        # Analyze status combinations during fault period (after preprocessing is complete)
        status_combinations_csv = _analyze_status_combinations_in_fault_period(df_filtered_traces)

        # Detect anomalies
        anomaly_events = _detect_anomalies(df_filtered_traces, trace_detectors)

        # Convert anomaly events to DataFrame format
        if not anomaly_events:
            return ("", {}, status_combinations_csv)  # Analysis succeeded but no anomalies detected

        anomaly_data = []
        for event in anomaly_events:
            timestamp, parent_pod, child_pod, operation_name, anomaly_type, duration, service_name, node_name = event
            # Convert to Beijing time (UTC+8)
            beijing_time = pd.to_datetime(timestamp, unit='ns') + pd.Timedelta(hours=BEIJING_TIMEZONE_OFFSET)
            anomaly_data.append({
                'timestamp': timestamp,
                'timestamp_readable': beijing_time,
                'parent_pod': parent_pod,
                'child_pod': child_pod,
                'operation_name': operation_name,
                'anomaly_type': anomaly_type,
                'duration': duration,
                'service_name': service_name,
                'node_name': node_name
            })

        df_anomalies = pd.DataFrame(anomaly_data)

        # ========== Part 3: Count top 10 anomaly combinations ==========
        # Sort by time
        df_anomalies = df_anomalies.sort_values('timestamp_readable')

        # Create combination column
        df_anomalies['combination'] = (df_anomalies['parent_pod'].astype(str) + '_' +
                                        df_anomalies['child_pod'].astype(str) + '_' +
                                        df_anomalies['operation_name'].astype(str))

        # Duration information is already directly extracted and included in anomaly data during anomaly detection, no need for additional matching

        # Group by combination for statistics
        combination_stats = []

        for combination_name, group in df_anomalies.groupby('combination'):
            parent_pod = group['parent_pod'].iloc[0]
            child_pod = group['child_pod'].iloc[0]
            operation_name = group['operation_name'].iloc[0]
            service_name = group['service_name'].iloc[0] if 'service_name' in group.columns else None
            node_name = group['node_name'].iloc[0] if 'node_name' in group.columns else None

            # Calculate average duration (if available)
            if 'duration' not in group.columns or len(group['duration'].dropna()) == 0:
                continue  # Skip combinations without valid duration data
            anomaly_avg_duration = group['duration'].mean()

            # Get average time for normal data
            normal_avg_time = 0
            combination_key = f"{parent_pod}_{child_pod}_{operation_name}"
            if combination_key in normal_stats:
                normal_avg_time = normal_stats[combination_key].get('mean', 0)

            stats = {
                'node_name': node_name,
                'service_name': service_name,
                'parent_pod': parent_pod,
                'child_pod': child_pod,
                'operation_name': operation_name,
                'normal_avg_duration': normal_avg_time,
                'anomaly_avg_duration': anomaly_avg_duration,
                'anomaly_count': len(group)
            }
            combination_stats.append(stats)

        # Convert to DataFrame and sort by occurrence count, take top 20
        if not combination_stats:
            return ("", {}, status_combinations_csv)  # Analysis succeeded but no valid combination statistics

        stats_df = pd.DataFrame(combination_stats)


        # Sort by occurrence count, take top 20 (sort before adding text)
        top_20_stats = stats_df.sort_values('anomaly_count', ascending=False).head(20)

        # Add text description to anomaly_count column
        top_20_stats['anomaly_count'] = top_20_stats['anomaly_count'].apply(lambda x: f"occurrence_count:{x}")

        # Rearrange column order
        desired_column_order = ['node_name', 'service_name', 'parent_pod', 'child_pod',
                               'operation_name', 'normal_avg_duration', 'anomaly_avg_duration', 'anomaly_count']
        # Ensure only existing columns are included, arranged in specified order
        existing_columns = [col for col in desired_column_order if col in top_20_stats.columns]
        top_20_stats = top_20_stats[existing_columns]

        # Extract three unique values from df_filtered_traces: pod_name, service_name, node_name
        trace_unique_dict = {
            'pod_name': [],
            'service_name': [],
            'node_name': []
        }

        # Extract pod_name from child_pod and parent_pod
        pod_names = []
        if 'child_pod' in top_20_stats.columns:
            pod_names.extend(top_20_stats['child_pod'].dropna().unique().tolist())
        if 'parent_pod' in top_20_stats.columns:
            pod_names.extend(top_20_stats['parent_pod'].dropna().unique().tolist())
        trace_unique_dict['pod_name'] = sorted(list(set([str(name) for name in pod_names if pd.notna(name)])))

        # Extract unique values from service_name column
        if 'service_name' in top_20_stats.columns:
            service_names = top_20_stats['service_name'].dropna().unique().tolist()
            trace_unique_dict['service_name'] = sorted(list(set([str(name) for name in service_names if pd.notna(name)])))

        # Extract unique values from node_name column
        if 'node_name' in top_20_stats.columns:
            node_names = top_20_stats['node_name'].dropna().unique().tolist()
            trace_unique_dict['node_name'] = sorted(list(set([str(name) for name in node_names if pd.notna(name)])))

        # Return CSV format string, three unique value dictionary and status combination statistics
        filtered_traces_csv = top_20_stats.to_csv(index=False)
        return filtered_traces_csv, trace_unique_dict, status_combinations_csv

    except Exception:
        return None  # Return None on error

def trace_analysis_tool(query: str) -> dict:
    """
    Analyze trace data based on anomaly description or UUID, return anomalous trace combinations and status statistics for that time period.

    Args:
        query: Natural language anomaly query, can be:
               - UUID (e.g., "345fbe93-80")
               - Time range description (e.g., "2025-06-05T16:10:02Z to 2025-06-05T16:31:02Z")
               - Anomaly description text (e.g., "The system experienced an anomaly from 2025-06-05T16:10:02Z to 2025-06-05T16:31:02Z. Please infer the possible cause")

    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - filtered_traces: CSV string of top 20 anomalous trace combinations (if successful)
        - unique_entities: Contains unique pod_name, service_name, node_name lists
        - status_combinations: CSV string of status combination statistics during fault period
        - message: Status message
        - matched_anomaly: Matched anomaly description
    """
    global df_input_timestamp

    try:
        # Try to find matching row in input_timestamp.csv
        matched_index = None
        matched_row = None

        # Method 1: Exact match by UUID
        uuid_match = df_input_timestamp[df_input_timestamp['uuid'].str.contains(query, case=False, na=False)]
        if not uuid_match.empty:
            matched_index = uuid_match.index[0]
            matched_row = uuid_match.iloc[0]

        # Method 2: Fuzzy match by Anomaly Description
        if matched_index is None:
            desc_match = df_input_timestamp[
                df_input_timestamp['Anomaly Description'].str.contains(query, case=False, na=False)
            ]
            if not desc_match.empty:
                matched_index = desc_match.index[0]
                matched_row = desc_match.iloc[0]

        # Method 3: Match by time string (supports time range)
        if matched_index is None:
            # Try to parse time range (format: "YYYY-MM-DDTHH:MM:SSZ to YYYY-MM-DDTHH:MM:SSZ")
            import re
            time_range_pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+to\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)'
            time_match_obj = re.search(time_range_pattern, query)

            if time_match_obj:
                start_time_str = time_match_obj.group(1)  # e.g., "2025-06-05T17:10:04Z"
                end_time_str = time_match_obj.group(2)    # e.g., "2025-06-05T17:33:04Z"

                # Normalize time string for matching (remove T and Z, replace with space)
                # "2025-06-05T17:10:04Z" -> "2025-06-05 17:10:04"
                start_normalized = start_time_str.replace('T', ' ').replace('Z', '')
                end_normalized = end_time_str.replace('T', ' ').replace('Z', '')

                # Find matching row in start_time_utc and end_time_utc columns
                time_match = df_input_timestamp[
                    (df_input_timestamp['start_time_utc'].astype(str).str.contains(start_normalized, na=False)) &
                    (df_input_timestamp['end_time_utc'].astype(str).str.contains(end_normalized, na=False))
                ]

                if not time_match.empty:
                    matched_index = time_match.index[0]
                    matched_row = time_match.iloc[0]

            # If time range matching fails, try fuzzy matching in all time columns
            if matched_index is None:
                time_cols = ['start_time_utc', 'end_time_utc', 'start_time_beijing', 'end_time_beijing']
                for col in time_cols:
                    time_match = df_input_timestamp[
                        df_input_timestamp[col].astype(str).str.contains(query.replace('T', ' ').replace('Z', ''), case=False, na=False)
                    ]
                    if not time_match.empty:
                        matched_index = time_match.index[0]
                        matched_row = time_match.iloc[0]
                        break

        # If no matching row found
        if matched_index is None:
            result = {
                "status": "error",
                "message": f"No anomaly record found matching query '{query}'. Please try using UUID, time range, or keywords from anomaly description.",
                "filtered_traces": None,
                "unique_entities": None,
                "status_combinations": None,
                "matched_anomaly": None
            }
            return result

        # Call _load_filtered_trace to get trace data
        load_result = _load_filtered_trace(df_input_timestamp, matched_index)

        if load_result is None:
             # Error during loading
            result = {
                "status": "error",
                "message": f"Failed to load trace data (returned None). UUID: {matched_row['uuid']}",
                "filtered_traces": None,
                "unique_entities": None,
                "status_combinations": None,
                "matched_anomaly": matched_row['Anomaly Description']
            }
            return result

        filtered_traces_csv, trace_unique_dict, status_combinations_csv = load_result

        if filtered_traces_csv == "":
            # Analysis succeeded but no anomalies detected
            result = {
                "status": "success",
                "message": f"Analysis completed, no trace anomalies detected. UUID: {matched_row['uuid']}",
                "filtered_traces": None,
                "unique_entities": trace_unique_dict,
                "status_combinations": status_combinations_csv if status_combinations_csv else None,
                "matched_anomaly": matched_row['Anomaly Description'],
                "time_range": f"{matched_row['start_time_utc']} to {matched_row['end_time_utc']}"
            }
            return result

        # Success with anomalies
        trace_count = len(filtered_traces_csv.split('\n')) - 2 if filtered_traces_csv else 0
        status_count = len(status_combinations_csv.split('\n')) - 2 if status_combinations_csv else 0

        result = {
            "status": "success",
            "message": f"Successfully loaded trace data. UUID: {matched_row['uuid']}, total {trace_count} anomaly combinations, {status_count} status combinations",
            "filtered_traces": filtered_traces_csv,
            "unique_entities": trace_unique_dict,
            "status_combinations": status_combinations_csv,
            "matched_anomaly": matched_row['Anomaly Description'],
            "time_range": f"{matched_row['start_time_utc']} to {matched_row['end_time_utc']}"
        }

        return result

    except Exception as e:
        result = {
            "status": "error",
            "message": f"Error during trace analysis: {str(e)}",
            "filtered_traces": None,
            "unique_entities": None,
            "status_combinations": None,
            "matched_anomaly": None
        }
        return result


def search_raw_traces(
    trace_id: Optional[str] = None,
    operation_name: Optional[str] = None,
    attribute_key: Optional[str] = None,
    time_range: Optional[list] = None,
    max_results: int = 20
) -> dict:
    """
    Search raw traces for specific trace_id, operation_name, or attribute_key within a time range

    This function searches the ORIGINAL trace data (not filtered/processed traces) in the trace-parquet files.

    Args:
        trace_id: Trace ID to search for (exact match)
        operation_name: Operation name to search for (supports regex)
        attribute_key: Attribute key to search in tags (e.g., "http.status_code", "error")
        time_range: Time range tuple (start_timestamp_ns, end_timestamp_ns) in nanoseconds (optional)
        max_results: Maximum number of spans to return (default 20)

    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - message: Status message
        - traces: List of matched trace spans from original data
        - total_matched: Total number of matched spans
        - returned: Number of spans actually returned

    Example:
        >>> from datetime import datetime
        >>> start_time = datetime(2025, 6, 6, 10, 0, 0)
        >>> end_time = datetime(2025, 6, 6, 10, 30, 0)
        >>> start_ts = int(start_time.timestamp() * 1_000_000_000)
        >>> end_ts = int(end_time.timestamp() * 1_000_000_000)
        >>>
        >>> # Search by trace_id
        >>> result = search_raw_traces(trace_id="abc123", time_range=[start_ts, end_ts])
        >>>
        >>> # Search by operation_name
        >>> result = search_raw_traces(operation_name="GET /product", time_range=[start_ts, end_ts])
        >>>
        >>> # Search by attribute_key in tags
        >>> result = search_raw_traces(attribute_key="http.status_code", time_range=[start_ts, end_ts])
    """
    import re
    from datetime import datetime

    try:
        # Validate input: at least one search criterion must be provided
        if not trace_id and not operation_name and not attribute_key:
            return {
                "status": "error",
                "message": "At least one search criterion (trace_id, operation_name, or attribute_key) must be provided",
                "traces": [],
                "total_matched": 0,
                "returned": 0
            }

        # Determine time range
        if time_range:
            start_ts, end_ts = time_range
            start_dt = datetime.fromtimestamp(start_ts / 1_000_000_000)
            end_dt = datetime.fromtimestamp(end_ts / 1_000_000_000)
            date_str = start_dt.strftime('%Y-%m-%d')
            start_hour = start_dt.hour
            end_hour = end_dt.hour

            # If time range spans multiple days, only search in the start date for now
            if start_dt.date() != end_dt.date():
                end_hour = 23
        else:
            return {
                "status": "error",
                "message": "time_range parameter is required",
                "traces": [],
                "total_matched": 0,
                "returned": 0
            }

        trace_dir = os.path.join(PROJECT_DIR, 'data', 'processed', date_str, 'trace-parquet')

        if not os.path.exists(trace_dir):
            return {
                "status": "error",
                "message": f"Trace directory not found for date {date_str}",
                "traces": [],
                "total_matched": 0,
                "returned": 0
            }

        # Compile regex pattern for operation_name if provided
        operation_pattern = None
        if operation_name:
            try:
                operation_pattern = re.compile(operation_name, re.IGNORECASE)
            except re.error as e:
                return {
                    "status": "error",
                    "message": f"Invalid regex pattern for operation_name: {str(e)}",
                    "traces": [],
                    "total_matched": 0,
                    "returned": 0
                }

        matched_traces = []
        total_matched = 0

        # Read trace files hour by hour from ORIGINAL data
        for hour in range(start_hour, end_hour + 1):
            # Try different file naming patterns
            trace_files = [
                f'trace_jaeger-span_{date_str}_{hour:02d}-00-00.parquet',
                f'trace_jaeger_{date_str}_{hour:02d}-00-00.parquet'
            ]

            trace_path = None
            for trace_file in trace_files:
                potential_path = os.path.join(trace_dir, trace_file)
                if os.path.exists(potential_path):
                    trace_path = potential_path
                    break

            if not trace_path:
                continue

            try:
                # Read original trace data
                df_traces = pd.read_parquet(trace_path)

                # Filter by time range
                if time_range:
                    df_traces = df_traces[(df_traces['timestamp_ns'] >= start_ts) & (df_traces['timestamp_ns'] <= end_ts)]

                if len(df_traces) == 0:
                    continue

                # Filter by trace_id (exact match)
                if trace_id:
                    df_traces = df_traces[df_traces['traceID'] == trace_id]

                if len(df_traces) == 0:
                    continue

                # Filter by operation_name (regex match)
                if operation_name and operation_pattern:
                    mask = df_traces['operationName'].astype(str).apply(lambda x: bool(operation_pattern.search(x)))
                    df_traces = df_traces[mask]

                if len(df_traces) == 0:
                    continue

                # Filter by attribute_key in tags
                if attribute_key:
                    mask = df_traces['tags'].astype(str).str.contains(attribute_key, case=False, na=False)
                    df_traces = df_traces[mask]

                if len(df_traces) == 0:
                    continue

                total_matched += len(df_traces)

                # Convert to list of dicts
                for _, row in df_traces.iterrows():
                    if len(matched_traces) >= max_results:
                        break

                    # Extract service name and pod name from process
                    service_name = None
                    pod_name = None
                    if isinstance(row['process'], dict):
                        service_name = row['process'].get('serviceName')
                        tags = row['process'].get('tags', [])
                        for tag in tags:
                            if tag.get('key') in ['name', 'podName']:
                                pod_name = tag.get('value')
                                break

                    matched_traces.append({
                        "timestamp": str(row['time_utc']),
                        "timestamp_ns": int(row['timestamp_ns']),
                        "trace_id": str(row['traceID']),
                        "span_id": str(row['spanID']),
                        "operation_name": str(row['operationName']),
                        "duration": int(row['duration']),
                        "service_name": str(service_name) if service_name else "N/A",
                        "pod_name": str(pod_name) if pod_name else "N/A",
                        "tags": str(row['tags']),
                        "references": str(row['references'])
                    })

                if len(matched_traces) >= max_results:
                    break

            except Exception:
                # Skip this file if there's an error
                continue

        # Sort by timestamp
        matched_traces.sort(key=lambda x: x['timestamp_ns'])

        search_criteria = []
        if trace_id:
            search_criteria.append(f"trace_id={trace_id}")
        if operation_name:
            search_criteria.append(f"operation_name={operation_name}")
        if attribute_key:
            search_criteria.append(f"attribute_key={attribute_key}")

        return {
            "status": "success",
            "message": f"Found {total_matched} matching spans in original data, returning {len(matched_traces)}",
            "traces": matched_traces,
            "total_matched": total_matched,
            "returned": len(matched_traces),
            "search_criteria": ", ".join(search_criteria),
            "time_range": {
                "start": str(start_dt) if time_range else None,
                "end": str(end_dt) if time_range else None
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error searching traces: {str(e)}",
            "traces": [],
            "total_matched": 0,
            "returned": 0
        }