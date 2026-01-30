import os
import pickle
import pandas as pd
from typing import Optional

PROJECT_DIR = os.getenv('PROJECT_DIR', '.')

input_timestamp_path = os.path.join(PROJECT_DIR, "input/input_timestamp.csv")
df_input_timestamp = pd.read_csv(input_timestamp_path)

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

    search_pattern = os.path.join(PROJECT_DIR, 'data', 'processed', '*', 'log-parquet', f'*{start_time_hour}*')
    matching_files = glob.glob(search_pattern, recursive=True)
    
    return matching_files, start_time, end_time


def _filter_logs_by_timerange(matching_files: list[str], start_time: int, end_time: int, df_log: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    """
    Filter log data by time range

    Args:
        matching_files: List of matching file paths
        start_time: Start timestamp
        end_time: End timestamp
        df_log: DataFrame containing log data, if None will attempt to read matching files

    Returns:
        DataFrame: Filtered log data containing only rows within time range; returns None if no matching files
    """
    import pandas as pd

    if not matching_files:
        return None

    if df_log is None:
        df_log = pd.DataFrame()
        for file in matching_files:
            temp_df = pd.read_parquet(file)
            df_log = pd.concat([df_log, temp_df])

    if 'timestamp_ns' not in df_log.columns:
        return None

    filtered_df = df_log[(df_log['timestamp_ns'] >= start_time) & (df_log['timestamp_ns'] <= end_time)]
    return filtered_df


def _filter_logs_by_error(df: Optional[pd.DataFrame], column: str = 'message') -> Optional[pd.DataFrame]:
    """
    Filter log data containing error keywords

    Args:
        df: Input DataFrame
        column: Column name to check, defaults to 'message'

    Returns:
        DataFrame: Log data containing errors; returns None if input is None or column doesn't exist
    """
    if df is None:
        return None

    if column not in df.columns:
        return None

    # Extended keyword list
    keywords = [
        'error', 'exception', 'fail', 'warn', 'critical', 'stress', 'timeout', 'refused',
        'gc', 'garbage', 'heap', 'latency',
        'slow', 'backoff', 'retry', 'deadlock', 'unreachable', 'election',
        'corrupt', 'checksum', 'malformed', 'truncated', 'crc'
    ]
    pattern = '|'.join(keywords)

    # 1. Initial filtering: keep logs containing keywords
    error_logs = df[df[column].str.contains(pattern, case=False, na=False)]

    # 2. Hard filter: physically remove known noise
    # Redis saving is normal behavior, not a fault; TiKV INFO logs are also often misread
    exclude_keywords = [
        'Background saving', 
        'DB saved on disk', 
        'RDB: ',
        'Background RDB',
        'diskless'
    ]
    
    if not error_logs.empty:
        exclude_pattern = '|'.join(exclude_keywords)
        error_logs = error_logs[~error_logs[column].str.contains(exclude_pattern, case=False, na=False)]
    
    return error_logs


def _filter_out_injected_errors(df: Optional[pd.DataFrame], column: str = 'message') -> Optional[pd.DataFrame]:
    """
    Filter out injected errors (if they have specific markers)
    Currently not filtering 'java' keyword to avoid false positives on normal Java service logs

    Args:
        df: Input DataFrame
        column: Column name to check, defaults to 'message'

    Returns:
        DataFrame: Filtered log data; returns None if input is None or column doesn't exist
    """
    if df is None or column not in df.columns:
        return None

    # Temporarily removed filtering for 'java' because adservice is a Java service and may contain java-related exception stacks
    # filtered_df = df[~df[column].str.contains('java', na=False)]
    return df

    
def _filter_logs_by_columns(filtered_df: Optional[pd.DataFrame], columns: Optional[list[str]] = None) -> Optional[pd.DataFrame]:
    """
    Further filter specified columns from already filtered log data

    Args:
        filtered_df: DataFrame already filtered by time range
        columns: List of column names to keep, if None returns all columns

    Returns:
        DataFrame: Data containing only specified columns; returns None if input is None
    """
    if filtered_df is None:
        return None

    if columns is None:
        return filtered_df

    # Only keep existing columns
    valid_cols = [col for col in columns if col in filtered_df.columns]
    if not valid_cols:
        return None

    return filtered_df.loc[:, valid_cols]


def _sample_logs_by_pod(df: Optional[pd.DataFrame], group_col: str = 'k8_pod', max_samples: int = 3, random_state: int = 42) -> Optional[pd.DataFrame]:
    """
    Group by specified column and randomly sample logs from each group

    Args:
        df: Input DataFrame
        group_col: Column name for grouping, defaults to 'k8_pod'
        max_samples: Maximum number of samples per group, defaults to 3
        random_state: Random seed, defaults to 42

    Returns:
        DataFrame: Sampled data
    """
    if df is None:
        return None

    sampled_df = df.groupby(group_col, group_keys=False).apply(
        lambda x: x.sample(min(len(x), max_samples), random_state=random_state)
    )
    return sampled_df


def _extract_log_templates(df: Optional[pd.DataFrame], message_col: str = 'message') -> Optional[pd.DataFrame]:
    """
    Extract templates from log messages and add template column

    Args:
        df: DataFrame containing log messages
        message_col: Column name containing log messages, defaults to 'message'

    Returns:
        DataFrame: DataFrame with added template column; returns original DataFrame if unable to process
    """
    if df is None or len(df) == 0 or message_col not in df.columns:
        return df

    try:
        drain_model_path = os.path.join(PROJECT_DIR, 'models', 'drain', 'error_log-drain.pkl')
        if not os.path.exists(drain_model_path):
            return df

        with open(drain_model_path, 'rb') as f:
            miner = pickle.load(f, encoding='bytes')

        templates = []
        for log in df[message_col]:
            cluster = miner.match(log)
            templates.append(cluster.get_template() if cluster else None)

        df['template'] = templates
        return df

    except Exception:
        return df


def _deduplicate_pod_template_combinations(df: Optional[pd.DataFrame], pod_col: str = 'k8_pod', template_col: str = 'template') -> Optional[pd.DataFrame]:
    """
    Deduplicate DataFrame by pod and template combinations, keeping only first occurrence of each combination and adding count column

    Args:
        df: DataFrame containing pod and template columns
        pod_col: Name of pod column, defaults to 'k8_pod'
        template_col: Name of template column, defaults to 'template'

    Returns:
        DataFrame: Deduplicated DataFrame with added occurrence_count column
    """
    if df is None or len(df) == 0:
        return df

    if pod_col not in df.columns or template_col not in df.columns:
        return df

    try:
        df_copy = df.copy()
        
        # Fill None templates with a prefix of the message to avoid grouping distinct errors together
        # Use first 50 chars of message as fallback template
        mask_none = df_copy[template_col].isna() | (df_copy[template_col] == 'None')
        if 'message' in df_copy.columns:
             df_copy.loc[mask_none, template_col] = df_copy.loc[mask_none, 'message'].astype(str).str.slice(0, 50)
        else:
             df_copy[template_col] = df_copy[template_col].fillna('None')

        # Calculate occurrence count for each combination
        pod_template_counts = df_copy.groupby([pod_col, template_col]).size().reset_index().rename(columns={0: 'occurrence_count'})
        pod_template_counts['occurrence_count'] = pod_template_counts['occurrence_count'].apply(
            lambda x: f"occurrence_count:{x}"
        )

        # Deduplicate and merge counts
        df_deduplicated = df_copy.drop_duplicates(subset=[pod_col, template_col], keep='first')
        df_deduplicated = pd.merge(df_deduplicated, pod_template_counts, on=[pod_col, template_col], how='left')

        return df_deduplicated

    except Exception:
        return df

def _extract_service_name(pod_name: str) -> str:
    """
    Extract service_name from pod_name (e.g., frontend-1 -> frontend)

    Args:
        pod_name: Pod name string, e.g., 'frontend-1'
    Returns:
        str: Extracted service_name (e.g., 'frontend'), returns original pod_name if extraction fails
    """
    if not isinstance(pod_name, str):
        return None
    # Take the part before the first '-'
    import re
    match = re.match(r'([a-zA-Z0-9]+)', pod_name)
    if match:
        return match.group(1)
    return pod_name

def _load_filtered_log(df_input_timestamp: pd.DataFrame, index: int) -> Optional[tuple[str, dict]]:
    """
    Load and filter log data, return CSV format string and unique pod/service/node lists

    Args:
        df_input_timestamp: DataFrame containing fault start/end timestamps
        index: Row index to query

    Returns:
        tuple: (filtered_logs_csv, log_unique_dict)
               - filtered_logs_csv: Filtered log string in CSV format, empty string means analysis succeeded but no error logs
               - log_unique_dict: {'pod_name': [...], 'service_name': [...], 'node_name': [...]} three unique value lists
               Returns None if file doesn't exist or error occurs during processing
    """
    matching_files, start_time, end_time = _get_period_info(df_input_timestamp, index)

    try:
        if not matching_files:
            return None  # File doesn't exist, real error

        df_log = pd.read_parquet(matching_files[0])
        df_filtered_logs = _filter_logs_by_timerange(matching_files, start_time, end_time, df_log=df_log)
        if df_filtered_logs is None or len(df_filtered_logs) == 0:
            return ("", {})  # Analysis succeeded but no logs

        df_filtered_logs = _filter_logs_by_error(df_filtered_logs, column='message')
        if df_filtered_logs is None or len(df_filtered_logs) == 0:
            return ("", {})  # Analysis succeeded but no error logs

        df_filtered_logs = _filter_logs_by_columns(filtered_df=df_filtered_logs, columns=['time_beijing', 'k8_pod', 'message', 'k8_node_name'])
        if df_filtered_logs is None or len(df_filtered_logs) == 0:
            return ("", {})  # Analysis succeeded but no results after filtering

        df_filtered_logs = _extract_log_templates(df_filtered_logs, message_col='message')
        if df_filtered_logs is None or len(df_filtered_logs) == 0:
            return ("", {})  # Analysis succeeded but no templates

        df_filtered_logs = _deduplicate_pod_template_combinations(df_filtered_logs, pod_col='k8_pod', template_col='template')
        if df_filtered_logs is None or len(df_filtered_logs) == 0:
            return ("", {})  # Analysis succeeded but no results after deduplication

        # Add service_name column
        df_filtered_logs['service_name'] = df_filtered_logs['k8_pod'].apply(_extract_service_name)
        df_filtered_logs = df_filtered_logs.rename(columns={'k8_pod': 'pod_name', 'k8_node_name': 'node_name'})

        # Select final columns and sort
        df_filtered_logs = df_filtered_logs[['node_name', 'service_name', 'pod_name', 'message', 'occurrence_count']]
        df_filtered_logs = df_filtered_logs.sort_values(by='occurrence_count', ascending=False)

        # Filter out injected java errors
        df_filtered_logs = _filter_out_injected_errors(df_filtered_logs, column='message')

        if df_filtered_logs is None or len(df_filtered_logs) == 0:
            return ("", {})  # Analysis succeeded but no results after filtering injected errors

        log_unique_dict = {
            'pod_name': df_filtered_logs['pod_name'].unique().tolist(),
            'service_name': df_filtered_logs['service_name'].unique().tolist(),
            'node_name': df_filtered_logs['node_name'].unique().tolist()
        }
        filtered_logs_csv = df_filtered_logs.to_csv(index=False)

        return filtered_logs_csv, log_unique_dict

    except Exception:
        return None  # Return None on error


def log_analysis_tool(query: str) -> dict:
    """
    Analyze log data based on anomaly description or UUID, return error logs and related information for that time period.

    Args:
        query: Natural language anomaly query, can be:
               - UUID (e.g., "345fbe93-80")
               - Time range description (e.g., "2025-06-05T16:10:02Z to 2025-06-05T16:31:02Z")
               - Anomaly description text

    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - filtered_logs: Filtered log CSV string (if successful)
        - unique_entities: Contains unique pod_name, service_name, node_name lists
        - message: Status message
        - matched_anomaly: Matched anomaly description
    """
    global df_input_timestamp

    try:
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

        # Method 3: Match by time string
        if matched_index is None:
            import re
            time_range_pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+to\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)'
            time_match_obj = re.search(time_range_pattern, query)

            if time_match_obj:
                start_normalized = time_match_obj.group(1).replace('T', ' ').replace('Z', '')
                end_normalized = time_match_obj.group(2).replace('T', ' ').replace('Z', '')

                time_match = df_input_timestamp[
                    (df_input_timestamp['start_time_utc'].astype(str).str.contains(start_normalized, na=False)) &
                    (df_input_timestamp['end_time_utc'].astype(str).str.contains(end_normalized, na=False))
                ]

                if not time_match.empty:
                    matched_index = time_match.index[0]
                    matched_row = time_match.iloc[0]

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

        if matched_index is None:
            result = {
                "status": "error",
                "message": f"No anomaly record found matching query '{query}'.",
                "filtered_logs": None,
                "unique_entities": None,
                "matched_anomaly": None
            }
            return result

        load_result = _load_filtered_log(df_input_timestamp, matched_index)

        if load_result is None:
             # Error during loading
            result = {
                "status": "error",
                "message": f"Failed to load log data (returned None). UUID: {matched_row['uuid']}",
                "filtered_logs": None,
                "unique_entities": None,
                "matched_anomaly": matched_row['Anomaly Description']
            }
            return result

        filtered_logs_csv, log_unique_dict = load_result

        if filtered_logs_csv == "":
            # Analysis succeeded but no error logs
            result = {
                "status": "success",
                "message": f"Analysis completed, no error logs detected. UUID: {matched_row['uuid']}",
                "filtered_logs": None,
                "unique_entities": log_unique_dict,
                "matched_anomaly": matched_row['Anomaly Description'],
                "time_range": f"{matched_row['start_time_utc']} to {matched_row['end_time_utc']}"
            }
            return result

        log_count = len(filtered_logs_csv.split('\n')) - 2 if filtered_logs_csv else 0

        # Success with error logs
        result = {
            "status": "success",
            "message": f"Successfully loaded log data. UUID: {matched_row['uuid']}, total {log_count} error logs",
            "filtered_logs": filtered_logs_csv,
            "unique_entities": log_unique_dict,
            "matched_anomaly": matched_row['Anomaly Description'],
            "time_range": f"{matched_row['start_time_utc']} to {matched_row['end_time_utc']}"
        }

        return result

    except Exception as e:
        result = {
            "status": "error",
            "message": f"Error during log analysis: {str(e)}",
            "filtered_logs": None,
            "unique_entities": None,
            "matched_anomaly": None
        }
        return result

