import os
import pandas as pd
from typing import Optional, List, Tuple, Dict

PROJECT_DIR = os.getenv('PROJECT_DIR', '.')

input_timestamp_path = os.path.join(PROJECT_DIR, "input/input_timestamp.csv")
df_input_timestamp = pd.read_csv(input_timestamp_path)

df_input_timestamp = df_input_timestamp.sort_values('start_timestamp').reset_index(drop=True)

def _get_fault_period_info(df_fault_timestamps: pd.DataFrame, row_index: int) -> Tuple[List[str], str, str, str]:
    """
    Get fault period information for the specified row

    Args:
        df_fault_timestamps: DataFrame containing fault start/end timestamps
        row_index: Row index to query

    Returns:
        List of matching Pod files, date, start_time, end_time
    """
    row = df_fault_timestamps.iloc[row_index]
    date = row['date']
    start_time = row['start_timestamp']
    end_time = row['end_timestamp']

    # Build Pod data directory path
    pod_dir = os.path.join(PROJECT_DIR, 'data', 'processed', f'{date}', 'metric-parquet', 'apm', 'pod')
    matching_files = os.listdir(pod_dir)

    return matching_files, date, start_time, end_time


def _extract_service_name_from_pod(pod_name: str) -> str:
    """
    Extract service name from pod name

    Args:
        pod_name: Pod name, e.g., "redis-cart-0"

    Returns:
        Service name, e.g., "redis"
    """
    # Extract the first part split by '-' as service name
    if '-' in pod_name:
        return pod_name.split('-')[0]
    return pod_name


def _get_normal_time_periods(df_fault_timestamps: pd.DataFrame, current_index: int) -> List[Tuple[str, str]]:
    """
    Get normal time periods (normal periods before and after current fault)

    Args:
        df_fault_timestamps: Fault timestamp DataFrame
        current_index: Current fault index

    Returns:
        List of normal time periods [(start_time, end_time), ...]
    """
    normal_periods = []
    current_row = df_fault_timestamps.iloc[current_index]
    current_start = current_row['start_timestamp']
    current_end = current_row['end_timestamp']

    # Get normal period before current fault (from previous fault end to current fault start)
    if current_index > 0:
        prev_row = df_fault_timestamps.iloc[current_index - 1]
        prev_end = prev_row['end_timestamp']
        # Normal period: 10 minutes after previous fault end to current fault start
        normal_periods.append((prev_end + 10 * 60 * 1_000_000_000, current_start))
        # normal_periods.append((prev_end , current_start))

    # Get normal period after current fault (from current fault end to next fault start)
    if current_index < len(df_fault_timestamps) - 1:
        next_row = df_fault_timestamps.iloc[current_index + 1]
        next_start = next_row['start_timestamp']
        # Normal period: current fault end to next fault start
        normal_periods.append((current_end + 10 * 60 * 1_000_000_000, next_start))
        # normal_periods.append((current_end , next_start))

    return normal_periods


def _get_metrics_description_from_dataframe(df_pod: pd.DataFrame, columns: List[str] = None) -> Dict[str, pd.Series]:
    """
    Get statistical description information for specified columns of DataFrame

    Args:
        df_pod: DataFrame of Pod metric data
        columns: List of column names for descriptive statistics, if None uses numeric columns

    Returns:
        Dictionary containing descriptive statistics for each column
    """
    if columns is None:
        # Default to numeric columns, added rrt_max metric here
        numeric_columns = ['client_error_ratio', 'error_ratio', 'request', 'response', 'rrt', 'rrt_max', 'server_error_ratio',
                           'timeout']
        # Filter to actually existing columns
        columns = [col for col in numeric_columns if col in df_pod.columns]

    descriptions = {}
    for column in columns:
        if column in df_pod.columns:
            # Descriptive statistics (including 0.25, 0.5, 0.75, 0.95, 0.99)
            desc = df_pod[column].describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])

            # Calculate non-zero ratio
            col_data = df_pod[column].dropna()
            non_zero_ratio = (col_data != 0).sum() / len(col_data) if len(col_data) > 0 else 0
            desc['non_zero_ratio'] = round(non_zero_ratio, 3)  # Keep 3 decimal places

            descriptions[column] = desc

    return descriptions


def _get_filtered_metrics_description_with_outlier_removal(df_pod: pd.DataFrame, start_time: str, end_time: str,
                                                          target_columns: List[str] = None,
                                                          remove_outliers: bool = False) -> Dict[str, pd.Series]:
    """
    Get metric descriptive statistics for specified time range, with optional outlier removal

    Args:
        df_pod: DataFrame of Pod metric data
        start_time: Start timestamp
        end_time: End timestamp
        target_columns: List of column names to analyze
        remove_outliers: Whether to remove outliers (smallest 2 and largest 2 values)

    Returns:
        Dictionary of metric descriptive statistics
    """
    if 'timestamp_ns' in df_pod.columns:
        # Convert timestamp to integer for comparison
        start_ts = int(start_time)
        end_ts = int(end_time)
        df_filtered = df_pod[(df_pod['timestamp_ns'] >= start_ts) & (df_pod['timestamp_ns'] <= end_ts)]
    else:
        df_filtered = df_pod

    if len(df_filtered) == 0:
        return {}

    # If need to remove outliers and have enough data
    if remove_outliers and len(df_filtered) > 4:  # Need at least 5 data points to remove 4
        return _get_metrics_description_from_dataframe_without_outliers(df_filtered, target_columns)
    else:
        return _get_metrics_description_from_dataframe(df_filtered, target_columns)


def _get_metrics_description_from_dataframe_without_outliers(df_pod: pd.DataFrame, columns: List[str] = None) -> Dict[
    str, pd.Series]:
    """
    Get descriptive statistics for specified DataFrame columns, removing smallest 2 and largest 2 values

    Args:
        df_pod: DataFrame of Pod metric data
        columns: List of column names for descriptive statistics, if None uses numeric columns

    Returns:
        Dictionary containing descriptive statistics for each column
    """
    if columns is None:
        # Default to numeric columns
        numeric_columns = ['client_error_ratio', 'error_ratio', 'request', 'response', 'rrt', 'rrt_max', 'server_error_ratio',
                           'timeout']
        # Filter to actually existing columns
        columns = [col for col in numeric_columns if col in df_pod.columns]

    descriptions = {}
    for column in columns:
        if column in df_pod.columns:
            # Get column data and sort
            col_data = df_pod[column].dropna().sort_values()

            if len(col_data) <= 4:
                # Too few data points, use original data description
                desc = col_data.describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])
            else:
                # Remove smallest 2 and largest 2
                trimmed_data = col_data.iloc[2:-2]
                desc = trimmed_data.describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])

            # Calculate non-zero ratio (based on data after removing outliers)
            non_zero_ratio = (trimmed_data != 0).sum() / len(trimmed_data) if len(col_data) > 4 else (col_data != 0).sum() / len(col_data)
            desc['non_zero_ratio'] = round(non_zero_ratio, 3)

            descriptions[column] = desc

    return descriptions


def _analyze_fault_vs_normal_metrics_by_service(df_fault_timestamps: pd.DataFrame, index: int,
                                               target_columns: List[str] = None) -> Optional[Dict]:
    """
    Analyze metric comparison between fault and normal periods at Service level
    Structure: service → pod → metrics (normal_periods_combined, fault_period)

    Args:
        df_fault_timestamps: Fault timestamp DataFrame
        index: Fault index to analyze
        target_columns: List of metric column names to analyze

    Returns:
        Dictionary organized by Service containing fault and normal period metric comparisons
    """
    pod_files, date, fault_start, fault_end = _get_fault_period_info(df_fault_timestamps, index)

    if not pod_files:
        return None

    normal_periods = _get_normal_time_periods(df_fault_timestamps, index)

    # Organize analysis results by Service → Pod → Metrics structure
    service_analysis = {}

    for pod_file in pod_files:
        pod_path = os.path.join(PROJECT_DIR, 'data', 'processed', f'{date}', 'metric-parquet', 'apm', 'pod', pod_file)
        pod_name = pod_file.split('_')[1] if '_' in pod_file else pod_file.split('.')[0]
        service_name = _extract_service_name_from_pod(pod_name)

        try:
            df_pod = pd.read_parquet(pod_path)

            if len(df_pod) == 0:
                continue

            # If service doesn't exist, initialize
            if service_name not in service_analysis:
                service_analysis[service_name] = {}

            # If pod doesn't exist, initialize
            if pod_name not in service_analysis[service_name]:
                service_analysis[service_name][pod_name] = {
                    'normal_periods_combined': {},  # Combined normal data statistics
                    'fault_period': {}  # Fault data statistics
                }

            # Collect all normal period data
            all_normal_data = []

            for i, (normal_start, normal_end) in enumerate(normal_periods):
                # Filter current normal period data
                start_ts = int(normal_start)
                end_ts = int(normal_end)
                normal_data = df_pod[(df_pod['timestamp_ns'] >= start_ts) & (df_pod['timestamp_ns'] <= end_ts)]

                if len(normal_data) > 0:
                    all_normal_data.append(normal_data)

            # Merge all normal period data
            if all_normal_data:
                combined_normal_data = pd.concat(all_normal_data, ignore_index=True)

                # Perform statistics on merged normal data (remove outliers)
                if len(combined_normal_data) > 4:  # Need at least 5 data points to remove 4
                    normal_desc = _get_metrics_description_from_dataframe_without_outliers(combined_normal_data,
                                                                                          target_columns)
                else:
                    normal_desc = _get_metrics_description_from_dataframe(combined_normal_data, target_columns)

                service_analysis[service_name][pod_name]['normal_periods_combined'] = normal_desc

            # 2. Get fault period statistics (don't remove outliers)
            fault_desc = _get_filtered_metrics_description_with_outlier_removal(
                df_pod, fault_start, fault_end, target_columns, remove_outliers=False
            )

            service_analysis[service_name][pod_name]['fault_period'] = fault_desc

        except Exception as e:
            pass

    return service_analysis if service_analysis else None


def _get_node_metrics_files_mapping(date: str) -> Dict[str, str]:
    """
    Get node metric file name mapping, returns mapping from metric name to file name

    Args:
        date: Date in format "2025-06-06"

    Returns:
        Dictionary mapping metric name to file name
    """
    return {
        'node_cpu_usage_rate': f'infra_node_node_cpu_usage_rate_{date}.parquet',
        'node_disk_read_bytes_total': f'infra_node_node_disk_read_bytes_total_{date}.parquet',
        'node_disk_read_time_seconds_total': f'infra_node_node_disk_read_time_seconds_total_{date}.parquet',
        'node_disk_write_time_seconds_total': f'infra_node_node_disk_write_time_seconds_total_{date}.parquet',
        'node_disk_written_bytes_total': f'infra_node_node_disk_written_bytes_total_{date}.parquet',
        'node_filesystem_free_bytes': f'infra_node_node_filesystem_free_bytes_{date}.parquet',
        'node_filesystem_size_bytes': f'infra_node_node_filesystem_size_bytes_{date}.parquet',
        'node_filesystem_usage_rate': f'infra_node_node_filesystem_usage_rate_{date}.parquet',
        'node_memory_MemAvailable_bytes': f'infra_node_node_memory_MemAvailable_bytes_{date}.parquet',
        'node_memory_MemTotal_bytes': f'infra_node_node_memory_MemTotal_bytes_{date}.parquet',
        'node_memory_usage_rate': f'infra_node_node_memory_usage_rate_{date}.parquet',
        'node_network_receive_bytes_total': f'infra_node_node_network_receive_bytes_total_{date}.parquet',
        'node_network_receive_packets_total': f'infra_node_node_network_receive_packets_total_{date}.parquet',
        'node_network_transmit_bytes_total': f'infra_node_node_network_transmit_bytes_total_{date}.parquet',
        'node_network_transmit_packets_total': f'infra_node_node_network_transmit_packets_total_{date}.parquet',
        'node_sockstat_TCP_inuse': f'infra_node_node_sockstat_TCP_inuse_{date}.parquet'
    }


def _get_target_nodes() -> List[str]:
    """
    Get target analysis node list (only analyze 8 nodes from aiops-k8s-01 to aiops-k8s-08)

    Returns:
        List of target node names
    """
    return [f'aiops-k8s-{i:02d}' for i in range(1, 9)]  # aiops-k8s-01 to aiops-k8s-08


def _load_node_metric_data(date: str, metric_name: str) -> Optional[pd.DataFrame]:
    """
    Load node data for specified date and metric

    Args:
        date: Date in format "2025-06-06"
        metric_name: Metric name, e.g., "node_cpu_usage_rate"

    Returns:
        Node metric data DataFrame, returns None if file doesn't exist
    """
    node_dir = os.path.join(PROJECT_DIR, 'data', 'processed', f'{date}', 'metric-parquet', 'infra', 'infra_node')

    file_mapping = _get_node_metrics_files_mapping(date)

    if metric_name not in file_mapping:
        return None

    file_path = os.path.join(node_dir, file_mapping[metric_name])

    try:
        if not os.path.exists(file_path):
            return None

        df = pd.read_parquet(file_path)

        # Only keep target node data
        target_nodes = _get_target_nodes()
        df_filtered = df[df['kubernetes_node'].isin(target_nodes)]

        if len(df_filtered) == 0:
            return None

        return df_filtered

    except Exception:
        return None


def _get_node_metrics_description_with_time_filter(df_node: pd.DataFrame, start_time: str, end_time: str,
                                                  metric_column: str, remove_outliers: bool = False) -> Optional[
    pd.Series]:
    """
    Get descriptive statistics for node metrics in specified time range

    Args:
        df_node: Node metric data DataFrame
        start_time: Start timestamp
        end_time: End timestamp
        metric_column: Metric column name (actual value column)
        remove_outliers: Whether to remove outliers

    Returns:
        Metric descriptive statistics, returns None if no data
    """
    if 'timestamp_ns' not in df_node.columns:
        return None

    # Time filtering
    start_ts = int(start_time)
    end_ts = int(end_time)
    df_filtered = df_node[(df_node['timestamp_ns'] >= start_ts) & (df_node['timestamp_ns'] <= end_ts)]

    if len(df_filtered) == 0:
        return None

    # Get metric data
    if metric_column not in df_filtered.columns:
        return None

    metric_data = df_filtered[metric_column].dropna()

    if len(metric_data) == 0:
        return None

    # Whether to remove outliers
    if remove_outliers and len(metric_data) > 4:
        metric_data_sorted = metric_data.sort_values()
        metric_data = metric_data_sorted.iloc[2:-2]  # Remove smallest 2 and largest 2
     # Descriptive statistics + percentiles
    desc = metric_data.describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])

    # **New: non-zero ratio**
    non_zero_ratio = (metric_data != 0).sum() / len(metric_data)
    desc['non_zero_ratio'] = round(non_zero_ratio, 3)

    return desc


def _analyze_node_metrics_by_node(df_fault_timestamps: pd.DataFrame, index: int,
                                 target_metrics: List[str] = None) -> Optional[Dict]:
    """
    Analyze node metric comparison between specified fault period and normal periods
    Structure: node → metric → {normal_periods_combined, fault_period}

    Args:
        df_fault_timestamps: Fault timestamp DataFrame
        index: Fault index to analyze
        target_metrics: List of metrics to analyze, if None uses all 10 metrics

    Returns:
        Dictionary organized by node containing fault and normal period metric comparisons
    """
    if target_metrics is None:
        target_metrics = ['node_cpu_usage_rate',
                          'node_disk_read_bytes_total',
                          'node_disk_read_time_seconds_total',
                          'node_disk_write_time_seconds_total',
                          'node_disk_written_bytes_total',
                          'node_filesystem_free_bytes',
                          'node_filesystem_usage_rate',
                          'node_filesystem_usage_rate',
                          'node_memory_MemAvailable_bytes',
                          'node_memory_MemTotal_bytes',
                          'node_memory_usage_rate',
                          'node_network_receive_bytes_total',
                          'node_network_receive_packets_total',
                          'node_network_transmit_bytes_total',
                          'node_network_transmit_packets_total',
                          'node_sockstat_TCP_inuse', ]

    # Get fault time information
    _, date, fault_start, fault_end = _get_fault_period_info(df_fault_timestamps, index)
    normal_periods = _get_normal_time_periods(df_fault_timestamps, index)
    target_nodes = _get_target_nodes()

    # Organize analysis results by node → metric → time period structure
    nodes_analysis = {}

    for node_name in target_nodes:
        # Initialize node structure
        nodes_analysis[node_name] = {}

        # Analyze all metrics for current node
        for metric_name in target_metrics:
            # Load data for this metric
            df_metric = _load_node_metric_data(date, metric_name)

            if df_metric is None:
                continue

            # Filter current node data
            df_node = df_metric[df_metric['kubernetes_node'] == node_name]

            if len(df_node) == 0:
                continue

            # Initialize metric structure
            nodes_analysis[node_name][metric_name] = {
                'normal_periods_combined': None,
                'fault_period': None
            }

            # 1. Merge all normal period data for statistics
            all_normal_data = []

            for i, (normal_start, normal_end) in enumerate(normal_periods):
                start_ts = int(normal_start)
                end_ts = int(normal_end)
                normal_data = df_node[(df_node['timestamp_ns'] >= start_ts) & (df_node['timestamp_ns'] <= end_ts)]

                if len(normal_data) > 0:
                    all_normal_data.append(normal_data)

            # Merge normal period data and calculate statistics
            if all_normal_data:
                combined_normal_data = pd.concat(all_normal_data, ignore_index=True)

                # Get statistics (remove outliers)
                normal_desc = _get_node_metrics_description_with_time_filter(
                    combined_normal_data,
                    str(combined_normal_data['timestamp_ns'].min()),
                    str(combined_normal_data['timestamp_ns'].max()),
                    metric_name,
                    remove_outliers=(len(combined_normal_data) > 4)
                )

                nodes_analysis[node_name][metric_name]['normal_periods_combined'] = normal_desc

            # 2. Fault period statistics
            fault_desc = _get_node_metrics_description_with_time_filter(
                df_node, fault_start, fault_end, metric_name, remove_outliers=False
            )

            nodes_analysis[node_name][metric_name]['fault_period'] = fault_desc

    return nodes_analysis if nodes_analysis else None


# ==================== 1. Pod Metric File Mapping ====================

def _get_pod_metrics_files_mapping(date: str) -> Dict[str, str]:
    """
    Get Pod metric file name mapping, returns mapping from metric name to file name

    Args:
        date: Date in format "2025-06-06"

    Returns:
        Dictionary mapping metric name to file name
    """
    return {
        'pod_cpu_usage': f'infra_pod_pod_cpu_usage_{date}.parquet',
        'pod_fs_reads_bytes': f'infra_pod_pod_fs_reads_bytes_{date}.parquet',
        'pod_fs_writes_bytes': f'infra_pod_pod_fs_writes_bytes_{date}.parquet',
        'pod_memory_working_set_bytes': f'infra_pod_pod_memory_working_set_bytes_{date}.parquet',
        'pod_network_receive_bytes': f'infra_pod_pod_network_receive_bytes_{date}.parquet',
        'pod_network_receive_packets': f'infra_pod_pod_network_receive_packets_{date}.parquet',
        'pod_network_transmit_bytes': f'infra_pod_pod_network_transmit_bytes_{date}.parquet',
        'pod_network_transmit_packets': f'infra_pod_pod_network_transmit_packets_{date}.parquet',
        'pod_processes': f'infra_pod_pod_processes_{date}.parquet'
    }


# ==================== 2. Target Pod List ====================

def _get_target_pods() -> List[str]:
    """
    Get target analysis Pod list
    """
    services = [
        "adservice-0", "adservice-1", "adservice-2",
        "cartservice-0", "cartservice-1", "cartservice-2",
        "checkoutservice-0", "checkoutservice-1", "checkoutservice-2",
        "currencyservice-0", "currencyservice-1", "currencyservice-2",
        "emailservice-0", "emailservice-1", "emailservice-2",
        "frontend-0", "frontend-1", "frontend-2",
        "paymentservice-0", "paymentservice-1", "paymentservice-2",
        "productcatalogservice-0", "productcatalogservice-1", "productcatalogservice-2",
        "recommendationservice-0", "recommendationservice-1", "recommendationservice-2",
        "redis-cart-0",
        "shippingservice-0", "shippingservice-1", "shippingservice-2"
    ]
    return services


# ==================== 3. Load Pod Metric Data ====================

def _load_pod_metric_data(date: str, metric_name: str) -> Optional[pd.DataFrame]:
    """
    Load Pod data for specified date and metric

    Args:
        date: Date in format "2025-06-06"
        metric_name: Metric name, e.g., "pod_cpu_usage"

    Returns:
        Pod metric data DataFrame, returns None if file doesn't exist
    """
    pod_dir = os.path.join(PROJECT_DIR, 'data', 'processed', f'{date}', 'metric-parquet', 'infra', 'infra_pod')

    file_mapping = _get_pod_metrics_files_mapping(date)

    if metric_name not in file_mapping:
        return None

    file_path = os.path.join(pod_dir, file_mapping[metric_name])

    try:
        if not os.path.exists(file_path):
            return None

        df = pd.read_parquet(file_path)

        # Only keep target pod data
        target_pods = _get_target_pods()
        df_filtered = df[df['pod'].isin(target_pods)]

        if len(df_filtered) == 0:
            return None

        return df_filtered

    except Exception:
        return None


# ==================== 4. Time Filtering Statistics ====================

def _get_pod_metrics_description_with_time_filter(df_pod: pd.DataFrame, start_time: str, end_time: str,
                                                 metric_column: str, remove_outliers: bool = False) -> Optional[
    pd.Series]:
    """
    Get descriptive statistics for Pod metrics in specified time range
    """
    if 'timestamp_ns' not in df_pod.columns:
        return None

    # Time filtering
    start_ts = int(start_time)
    end_ts = int(end_time)
    df_filtered = df_pod[(df_pod['timestamp_ns'] >= start_ts) & (df_pod['timestamp_ns'] <= end_ts)]

    if len(df_filtered) == 0:
        return None

    # Get metric data
    if metric_column not in df_filtered.columns:
        return None

    metric_data = df_filtered[metric_column].dropna()

    if len(metric_data) == 0:
        return None

    # Whether to remove outliers
    if remove_outliers and len(metric_data) > 4:
        metric_data_sorted = metric_data.sort_values()
        metric_data = metric_data_sorted.iloc[2:-2]  # Remove smallest 2 and largest 2
    # Generate descriptive statistics
    desc = metric_data.describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])

    # Add non-zero ratio
    desc['non_zero_ratio'] = round((metric_data != 0).sum() / len(metric_data), 3)

    return desc


# ==================== 5. Analyze Fault vs Normal by Pod ====================

def _analyze_pod_metrics_by_pod(df_fault_timestamps: pd.DataFrame, index: int,
                               target_metrics: List[str] = None) -> Optional[Dict]:
    """
    Analyze Pod metric comparison between specified fault period and normal periods
    Structure: pod → metric → {normal_periods_combined, fault_period}
    """
    if target_metrics is None:
        target_metrics = [
            'pod_cpu_usage', 'pod_fs_reads_bytes', 'pod_fs_writes_bytes',
            'pod_memory_working_set_bytes', 'pod_network_receive_bytes',
            'pod_network_receive_packets', 'pod_network_transmit_bytes',
            'pod_network_transmit_packets', 'pod_processes'
        ]

    # Get fault time information
    _, date, fault_start, fault_end = _get_fault_period_info(df_fault_timestamps, index)
    normal_periods = _get_normal_time_periods(df_fault_timestamps, index)
    target_pods = _get_target_pods()

    # Organize analysis results by Pod → metric → time period structure
    pods_analysis = {}

    for pod_name in target_pods:
        pods_analysis[pod_name] = {}

        for metric_name in target_metrics:
            # Load data for this metric
            df_metric = _load_pod_metric_data(date, metric_name)

            if df_metric is None:
                continue

            # Filter current Pod data
            df_pod = df_metric[df_metric['pod'] == pod_name]
            # Delete rows where device column is /dev/vdb
            if 'device' in df_pod.columns:
                df_pod = df_pod[df_pod['device'] != '/dev/dmb']

            if len(df_pod) == 0:
                continue

            # Initialize metric structure
            pods_analysis[pod_name][metric_name] = {
                'normal_periods_combined': None,
                'fault_period': None
            }

            # 1. Merge all normal period data
            all_normal_data = []

            for i, (normal_start, normal_end) in enumerate(normal_periods):
                start_ts = int(normal_start)
                end_ts = int(normal_end)
                normal_data = df_pod[(df_pod['timestamp_ns'] >= start_ts) & (df_pod['timestamp_ns'] <= end_ts)]

                if len(normal_data) > 0:
                    all_normal_data.append(normal_data)

            # Merge normal period data and calculate statistics
            normal_desc = None
            if all_normal_data:
                combined_normal_data = pd.concat(all_normal_data, ignore_index=True)

                normal_desc = _get_pod_metrics_description_with_time_filter(
                    combined_normal_data,
                    str(combined_normal_data['timestamp_ns'].min()),
                    str(combined_normal_data['timestamp_ns'].max()),
                    metric_name,
                    remove_outliers=(len(combined_normal_data) > 4)
                )

            # 2. Fault period statistics
            fault_desc = _get_pod_metrics_description_with_time_filter(
                df_pod, fault_start, fault_end, metric_name, remove_outliers=False
            )
            pods_analysis[pod_name][metric_name]['fault_period'] = fault_desc
            pods_analysis[pod_name][metric_name]['normal_periods_combined'] = normal_desc

    return pods_analysis if pods_analysis else None




def _convert_metrics_to_csv(metric_data: Dict, change_threshold: float = 0.05) -> tuple[str, dict]:
    """
    Convert metric data to CSV format, only including metrics with significant changes

    Args:
        metric_data: Raw metric data
        change_threshold: Change threshold (default 5%)

    Returns:
        tuple: (csv_string, unique_dict)
            - csv_string: CSV format anomaly metric list
            - unique_dict: Unique value dictionary {'service_name': [...], 'node_name': [...], 'pod_name': [...]}
    """
    anomaly_rows = []
    unique_services = set()
    unique_nodes = set()
    unique_pods = set()

    # Statistics
    stats = {
        'service': {'total_checked': 0, 'passed_filter': 0},
        'tidb': {'total_checked': 0, 'passed_filter': 0},
        'node': {'total_checked': 0, 'passed_filter': 0},
        'pod': {'total_checked': 0, 'passed_filter': 0}
    }

    def calculate_symmetric_ratio(normal_val, fault_val):
        """Calculate symmetric ratio"""
        return abs(fault_val - normal_val) / ((fault_val + normal_val) / 2 + 1e-9)

    def extract_stats(stats_dict):
        """Extract key values from statistics dictionary"""
        if stats_dict is None:
            return None, None, None, None
        if isinstance(stats_dict, dict) and not stats_dict:
            return None, None, None, None
        return (
            stats_dict.get('50%', 0),
            stats_dict.get('99%', 0),
            stats_dict.get('25%', 0),
            stats_dict.get('75%', 0)
        )

    # Define absolute thresholds for noise filtering
    ABSOLUTE_THRESHOLDS = {
        # CPU (cores or ratio)
        'pod_cpu_usage': 0.05,
        'node_cpu_usage_rate': 0.05,
        'cpu_usage': 0.05, # TiDB
        
        # Memory (Bytes) - 10MB
        'pod_memory_working_set_bytes': 10 * 1024 * 1024,
        'node_memory_usage_rate': 0.05,
        'node_memory_MemAvailable_bytes': 100 * 1024 * 1024, # 100MB for Node
        
        # Network (Bytes/Packets)
        'pod_network_receive_bytes': 1024, # 1KB
        'pod_network_transmit_bytes': 1024,
        'pod_network_receive_packets': 10,
        'pod_network_transmit_packets': 10,
        'node_network_receive_bytes_total': 1024 * 1024, # 1MB
        'node_network_transmit_bytes_total': 1024 * 1024,
        
        # Disk (Bytes)
        'pod_fs_reads_bytes': 1024 * 1024, # 1MB
        'pod_fs_writes_bytes': 1024 * 1024,
        'node_disk_written_bytes_total': 10 * 1024 * 1024, # 10MB
        'node_disk_read_bytes_total': 10 * 1024 * 1024,
        
        # Latency (ms)
        'rrt': 10,
        'rrt_max': 10,
        'duration_99th': 10,
        'raft_apply_wait': 5,
        'raft_propose_wait': 5,
        
        # Error Ratio
        'error_ratio': 0.01,
        'server_error_ratio': 0.01,
        'client_error_ratio': 0.01,
        
        # Others
        'pod_processes': 2,
        'io_util': 0.05,
    }

    def is_negligible(metric_name, val1, val2):
        threshold = ABSOLUTE_THRESHOLDS.get(metric_name)
        if threshold is None:
            # Try partial match for generic names
            if 'cpu' in metric_name: threshold = 0.05
            elif 'memory' in metric_name and 'rate' in metric_name: threshold = 0.05
            elif 'bytes' in metric_name: threshold = 1024 * 1024 # Default 1MB
            elif 'packets' in metric_name: threshold = 10
            elif 'ratio' in metric_name: threshold = 0.01
            else: return False # No threshold defined, assume significant
            
        # If BOTH values are below threshold, it's negligible
        # Use max to be safe (if one spikes above threshold, it's not negligible)
        return max(val1, val2) < threshold

    # Process Service metrics
    for service_name, service_pods in metric_data.get('service_metrics', {}).items():
        unique_services.add(str(service_name))

        for pod_name, pod_metrics in service_pods.items():
            unique_pods.add(str(pod_name))

            normal_combined = pod_metrics.get('normal_periods_combined', {})
            fault_period = pod_metrics.get('fault_period', {})

            # Get all metric names (from normal or fault)
            all_metric_names = set(normal_combined.keys()) | set(fault_period.keys())

            for metric_name in all_metric_names:
                
                normal_stats = normal_combined.get(metric_name)
                fault_stats = fault_period.get(metric_name)
                
                if normal_stats is None or fault_stats is None:
                    continue
                if (isinstance(normal_stats, dict) and not normal_stats) or (isinstance(fault_stats, dict) and not fault_stats):
                    continue
                
                n_p50, n_p99, n_p25, n_p75 = extract_stats(normal_stats)
                f_p50, f_p99, f_p25, f_p75 = extract_stats(fault_stats)
                
                if n_p50 is None or f_p50 is None:
                    continue
                
                # Check for negligible values
                if is_negligible(metric_name, n_p99, f_p99):
                    continue
                
                p50_ratio = calculate_symmetric_ratio(n_p50, f_p50)
                p99_ratio = calculate_symmetric_ratio(n_p99, f_p99)

                stats['service']['total_checked'] += 1

                # Only keep metrics with significant changes
                if p50_ratio >= change_threshold or p99_ratio >= change_threshold:
                    stats['service']['passed_filter'] += 1
                    anomaly_rows.append({
                        'metric_type': 'service',
                        'service_name': str(service_name),
                        'pod_name': str(pod_name),
                        'node_name': 'N/A',
                        'metric_name': str(metric_name),
                        'normal_median': round(n_p50, 2),
                        'fault_median': round(f_p50, 2),
                        'normal_p99': round(n_p99, 2),
                        'fault_p99': round(f_p99, 2),
                        'median_change_ratio': round(p50_ratio, 4),
                        'p99_change_ratio': round(p99_ratio, 4)
                    })

    # Process TiDB component metrics
    for component_name, component_metrics in metric_data.get('tidb_metrics', {}).items():
        unique_services.add(str(component_name))
        
        for metric_name, metric_stats in component_metrics.items():
            normal_stats = metric_stats.get('normal_periods_combined')
            fault_stats = metric_stats.get('fault_period')
            
            if normal_stats is None or fault_stats is None:
                continue
            if (isinstance(normal_stats, dict) and not normal_stats) or (isinstance(fault_stats, dict) and not fault_stats):
                continue
            
            n_p50, n_p99, n_p25, n_p75 = extract_stats(normal_stats)
            f_p50, f_p99, f_p25, f_p75 = extract_stats(fault_stats)
            
            if n_p50 is None or f_p50 is None:
                continue
            
            # Check for negligible values
            if is_negligible(metric_name, n_p99, f_p99):
                continue
            
            p50_ratio = calculate_symmetric_ratio(n_p50, f_p50)
            p99_ratio = calculate_symmetric_ratio(n_p99, f_p99)
            
            stats['tidb']['total_checked'] += 1
            
            if p50_ratio >= change_threshold or p99_ratio >= change_threshold:
                stats['tidb']['passed_filter'] += 1
                anomaly_rows.append({
                    'metric_type': 'tidb',
                    'service_name': str(component_name),
                    'pod_name': 'N/A',
                    'node_name': 'N/A',
                    'metric_name': str(metric_name),
                    'normal_median': round(n_p50, 2),
                    'fault_median': round(f_p50, 2),
                    'normal_p99': round(n_p99, 2),
                    'fault_p99': round(f_p99, 2),
                    'median_change_ratio': round(p50_ratio, 4),
                    'p99_change_ratio': round(p99_ratio, 4)
                })

    # Process Node metrics
    node_pod_mapping = metric_data.get('node_pod_mapping', {})
    for node_name, node_metrics in metric_data.get('node_metrics', {}).items():
        unique_nodes.add(str(node_name))

        # Add all Pods on this node
        pods_on_node = node_pod_mapping.get(node_name, [])
        for pod in pods_on_node:
            unique_pods.add(str(pod))
        
        for metric_name, metric_stats in node_metrics.items():
            normal_stats = metric_stats.get('normal_periods_combined')
            fault_stats = metric_stats.get('fault_period')
            
            if normal_stats is None or fault_stats is None:
                continue
            if (isinstance(normal_stats, dict) and not normal_stats) or (isinstance(fault_stats, dict) and not fault_stats):
                continue
            
            n_p50, n_p99, n_p25, n_p75 = extract_stats(normal_stats)
            f_p50, f_p99, f_p25, f_p75 = extract_stats(fault_stats)
            
            if n_p50 is None or f_p50 is None:
                continue
            
            # Check for negligible values
            if is_negligible(metric_name, n_p99, f_p99):
                continue
            
            p50_ratio = calculate_symmetric_ratio(n_p50, f_p50)
            p99_ratio = calculate_symmetric_ratio(n_p99, f_p99)
            
            # === New logic: Absolute value saturation check ===
            is_saturated = False
            # Check if Node memory/CPU is overloaded (threshold 0.8 = 80%)
            if metric_name in ['node_memory_usage_rate', 'node_cpu_usage_rate']:
                if f_p50 > 0.8:  # Median during fault period exceeds 80%
                    is_saturated = True

            # Check if Node disk usage is overloaded (threshold 0.8 = 80%)
            if metric_name == 'node_filesystem_usage_rate':
                if f_p50 > 0.8:
                    is_saturated = True

            stats['node']['total_checked'] += 1
            
            if p50_ratio >= change_threshold or p99_ratio >= change_threshold or is_saturated:
                stats['node']['passed_filter'] += 1
                anomaly_rows.append({
                    'metric_type': 'node',
                    'service_name': 'N/A',
                    'pod_name': 'N/A',
                    'node_name': str(node_name),
                    'metric_name': str(metric_name),
                    'normal_median': round(n_p50, 2),
                    'fault_median': round(f_p50, 2),
                    'normal_p99': round(n_p99, 2),
                    'fault_p99': round(f_p99, 2),
                    'median_change_ratio': round(p50_ratio, 4),
                    'p99_change_ratio': round(p99_ratio, 4)
                })

    # Process Pod metrics
    for pod_name, pod_metrics in metric_data.get('pod_metrics', {}).items():
        unique_pods.add(str(pod_name))

        for metric_name, metric_stats in pod_metrics.items():
            normal_stats = metric_stats.get('normal_periods_combined')
            fault_stats = metric_stats.get('fault_period')
            
            # Skip if normal stats are missing (we can't compare)
            if normal_stats is None or (isinstance(normal_stats, dict) and not normal_stats):
                continue

            n_p50, n_p99, n_p25, n_p75 = extract_stats(normal_stats)
            if n_p50 is None:
                continue

            # Handle fault stats
            if fault_stats is None or (isinstance(fault_stats, dict) and not fault_stats):
                # Missing data in fault period -> Treat as 0 (Pod likely down/killed)
                f_p50 = 0.0
                f_p99 = 0.0
            else:
                f_p50, f_p99, f_p25, f_p75 = extract_stats(fault_stats)
                if f_p50 is None:
                    f_p50 = 0.0
                    f_p99 = 0.0
            
            # Check for negligible values
            if is_negligible(metric_name, n_p99, f_p99):
                continue
            
            p50_ratio = calculate_symmetric_ratio(n_p50, f_p50)
            p99_ratio = calculate_symmetric_ratio(n_p99, f_p99)
            
            stats['pod']['total_checked'] += 1

            if p50_ratio >= change_threshold or p99_ratio >= change_threshold:
                stats['pod']['passed_filter'] += 1
                anomaly_rows.append({
                    'metric_type': 'pod',
                    'service_name': 'N/A',
                    'pod_name': str(pod_name),
                    'node_name': 'N/A',
                    'metric_name': str(metric_name),
                    'normal_median': round(n_p50, 2),
                    'fault_median': round(f_p50, 2),
                    'normal_p99': round(n_p99, 2),
                    'fault_p99': round(f_p99, 2),
                    'median_change_ratio': round(p50_ratio, 4),
                    'p99_change_ratio': round(p99_ratio, 4)
                })

    # If no anomalies, return empty
    if not anomaly_rows:
        return "", {'service_name': [], 'node_name': [], 'pod_name': []}

    # Convert to DataFrame and sort
    df_anomalies = pd.DataFrame(anomaly_rows)

    # Calculate sorting score: combine change ratio and absolute value
    # For resource metrics (memory, disk, network, latency), larger absolute values are more important
    # Score = max_change_ratio * sqrt(fault_p99)
    # This ensures:
    # 1. Metrics with large change ratio but small absolute value (e.g., Redis 5MB->35MB) get lower scores
    # 2. Metrics with moderate change ratio but large absolute value (e.g., Shipping 200MB->500MB) get higher scores
    
    def calculate_score(row):
        ratio = max(row['median_change_ratio'], row['p99_change_ratio'])
        # Use max of normal and fault value to handle "Drop to Zero" cases correctly
        # If value drops from 1000 to 0, we want to score it based on 1000, not 0.
        value = max(row['normal_p99'], row['fault_p99'])

        # For CPU/Processes and other small-value metrics, use Ratio directly
        if row['metric_name'] in ['pod_cpu_usage', 'pod_processes', 'node_cpu_usage_rate', 'node_memory_usage_rate', 'node_filesystem_usage_rate',
                                  'io_util', 'region_pending', 'rocksdb_write_stall', 'cpu_usage', 'failed_query_ops', 'store_down_count', 'store_unhealth_count',
                                  'raft_apply_wait', 'raft_propose_wait', 'duration_99th',
                                  'rrt', 'rrt_max', 'client_error', 'client_error_ratio', 'server_error', 'server_error_ratio', 'error', 'error_ratio',
                                  'dns', 'http.resp.status']:
            return ratio * 100  # Give higher weight as these are usually critical bottlenecks

        # For Bytes/Duration and other large-value metrics, combine with absolute value
        # Use sqrt as a compromise, neither completely ignoring Ratio nor being completely dominated by Value

        # For Bytes-type metrics, convert to MB (divide by 1e6) then take square root to avoid excessive weight from large values
        if 'bytes' in row['metric_name'].lower():
             return ratio * ((value / 1e6) ** 0.5)

        return ratio * (value ** 0.5)

    df_anomalies['score'] = df_anomalies.apply(calculate_score, axis=1)
    df_anomalies = df_anomalies.sort_values('score', ascending=False)
    df_anomalies = df_anomalies.head(30)  # Keep only Top 30 to avoid information overload
    df_anomalies = df_anomalies.drop('score', axis=1)

    # Convert to CSV
    csv_string = df_anomalies.to_csv(index=False)

    # Build unique value dictionary
    unique_dict = {
        'service_name': sorted(list(unique_services)),
        'node_name': sorted(list(unique_nodes)),
        'pod_name': sorted(list(unique_pods)),
        'metric_name': sorted(list(df_anomalies['metric_name'].unique()))
    }

    return csv_string, unique_dict



def _get_node_pod_mapping(date: str) -> Dict[str, List[str]]:
    """
    Get list of Pods deployed on each node

    Args:
        date: Date in format "2025-06-06"

    Returns:
        Dictionary mapping node name to Pod list {node_name: [pod1, pod2, ...]}
    """
    infra_pod_dir = os.path.join(PROJECT_DIR, 'data', 'processed', f'{date}', 'metric-parquet', 'infra', 'infra_pod')

    # Try to read CPU usage file first
    target_file = f'infra_pod_pod_cpu_usage_{date}.parquet'
    target_file_path = os.path.join(infra_pod_dir, target_file)

    df_pod_info = None

    try:
        if os.path.exists(target_file_path):
            df_pod_info = pd.read_parquet(target_file_path)
        else:
            # If target file doesn't exist, randomly select a file
            if os.path.exists(infra_pod_dir):
                available_files = [f for f in os.listdir(infra_pod_dir) if f.endswith('.parquet')]
                if available_files:
                    selected_file = available_files[0]  # Select first file
                    selected_file_path = os.path.join(infra_pod_dir, selected_file)
                    df_pod_info = pd.read_parquet(selected_file_path)
                else:
                    return {}
            else:
                return {}

        if df_pod_info is None or len(df_pod_info) == 0:
            return {}

        # Get target node list
        target_nodes = _get_target_nodes()
        node_pod_mapping = {}

        for node_name in target_nodes:
            # Filter data for this node
            node_data = df_pod_info[df_pod_info['instance'] == node_name]
            if len(node_data) > 0:
                # Get unique Pod list on this node
                pods_on_node = node_data['pod'].unique().tolist()
                node_pod_mapping[node_name] = pods_on_node
            else:
                node_pod_mapping[node_name] = []

        return node_pod_mapping

    except Exception:
        return {}


# ==================== TiDB Service Related Functions ====================

def _get_tidb_services_files_mapping(date: str) -> Dict[str, Dict[str, str]]:
    """
    Get TiDB service file name mapping, returns mapping from service name to metric files

    Args:
        date: Date in format "2025-06-06"

    Returns:
        Dictionary mapping service name to metric files {service_name: {metric_name: file_name}}
    """
    return {
        'tidb-tidb': {
            'failed_query_ops': f'infra_tidb_failed_query_ops_{date}.parquet',
            'duration_99th': f'infra_tidb_duration_99th_{date}.parquet',
            'connection_count': f'infra_tidb_connection_count_{date}.parquet',
            'server_is_up': f'infra_tidb_server_is_up_{date}.parquet',
            'cpu_usage': f'infra_tidb_cpu_usage_{date}.parquet',
            'memory_usage': f'infra_tidb_memory_usage_{date}.parquet'
        },
        'tidb-pd': {
            'store_up_count': f'infra_pd_store_up_count_{date}.parquet',
            'store_down_count': f'infra_pd_store_down_count_{date}.parquet',
            'cpu_usage': f'infra_pd_cpu_usage_{date}.parquet',
            'memory_usage': f'infra_pd_memory_usage_{date}.parquet',
            'storage_used_ratio': f'infra_pd_storage_used_ratio_{date}.parquet',
            'store_unhealth_count': f'infra_pd_store_unhealth_count_{date}.parquet',
            'store_size': f'infra_pd_store_size_{date}.parquet',
            'leader_count': f'infra_pd_leader_count_{date}.parquet',
            'region_health': f'infra_pd_region_health_{date}.parquet',
            'abnormal_region_count': f'infra_pd_abnormal_region_count_{date}.parquet'
        },
        'tidb-tikv': {
            'cpu_usage': f'infra_tikv_cpu_usage_{date}.parquet',
            'memory_usage': f'infra_tikv_memory_usage_{date}.parquet',
            'server_is_up': f'infra_tikv_server_is_up_{date}.parquet',
            'available_size': f'infra_tikv_available_size_{date}.parquet',
            'raft_propose_wait': f'infra_tikv_raft_propose_wait_{date}.parquet',
            'raft_apply_wait': f'infra_tikv_raft_apply_wait_{date}.parquet',
            'rocksdb_write_stall': f'infra_tikv_rocksdb_write_stall_{date}.parquet',
            'io_util': f'infra_tikv_io_util_{date}.parquet',
            'region_pending': f'infra_tikv_region_pending_{date}.parquet',
            'snapshot_apply_count': f'infra_tikv_snapshot_apply_count_{date}.parquet',
            'block_cache_size': f'infra_tikv_block_cache_size_{date}.parquet'
        }
    }


def _get_tidb_services_directories() -> Dict[str, str]:
    """
    Get TiDB service data directory mapping

    Returns:
        Dictionary mapping service name to directory path
    """
    return {
        'tidb-tidb': 'infra/infra_tidb',
        'tidb-pd': 'other',
        'tidb-tikv': 'other'
    }


def _get_tidb_core_metrics() -> Dict[str, List[str]]:
    """
    Get TiDB service core metrics list (based on your filtering recommendations)

    Returns:
        Dictionary mapping service name to core metrics list
    """
    return {
        'tidb-tidb': [
            'failed_query_ops',  # Failed request count - error rate metric
            'duration_99th',  # 99th percentile request latency - key performance metric
            'connection_count',  # Connection count - load metric
            'server_is_up',  # Service alive node count - availability metric
            'cpu_usage',  # CPU usage rate - resource saturation
            'memory_usage'  # Memory usage - resource usage
        ],
        'tidb-pd': [
            'store_up_count',  # Healthy Store count - cluster health
            'store_down_count',  # Down Store count - failure metric
            'store_unhealth_count',  # Unhealth Store count - anomaly metric
            'storage_used_ratio',  # Used capacity ratio - capacity metric
            'cpu_usage',  # CPU usage rate - resource usage
            'memory_usage',  # Memory usage - resource usage
            'store_size', # Storage size
            'leader_count', # Leader count
            'region_health', # Region health
            'abnormal_region_count' # Abnormal Region count
        ],
        'tidb-tikv': [
            'cpu_usage',  # CPU usage rate - resource usage
            'memory_usage',  # Memory usage - resource usage
            'server_is_up',  # Service alive node count - availability
            'available_size',  # Available storage capacity - capacity warning
            'raft_propose_wait',  # RaftPropose wait latency P99 - performance metric
            'raft_apply_wait',  # RaftApply wait latency P99 - performance metric
            'rocksdb_write_stall',  # RocksDB write stall count - critical anomaly metric
            'io_util',  # IO utilization - disk IO bottleneck
            'region_pending',  # Pending Region count - Raft consistency anomaly
            'snapshot_apply_count', # Snapshot apply count
            'block_cache_size' # Block Cache size
        ]
    }


def _load_tidb_service_data(date: str, service_name: str, metric_name: str) -> Optional[pd.DataFrame]:
    """
    Load metric data for specified TiDB service

    Args:
        date: Date in format "2025-06-06"
        service_name: Service name, e.g., "tidb-tidb"
        metric_name: Metric name, e.g., "cpu_usage"

    Returns:
        TiDB service metric data DataFrame, returns None if file doesn't exist
    """

    # Get directory mapping
    directories = _get_tidb_services_directories()
    if service_name not in directories:
        return None

    # Build data directory path
    data_dir = os.path.join(PROJECT_DIR, 'data', 'processed', f'{date}', 'metric-parquet', directories[service_name])

    # Get file mapping
    file_mapping = _get_tidb_services_files_mapping(date)
    if service_name not in file_mapping or metric_name not in file_mapping[service_name]:
        return None

    file_path = os.path.join(data_dir, file_mapping[service_name][metric_name])

    try:
        if not os.path.exists(file_path):
            return None

        df = pd.read_parquet(file_path)

        if len(df) == 0:
            return None

        return df

    except Exception:
        return None


def _get_tidb_metrics_description_with_time_filter(df_tidb: pd.DataFrame, start_time: str, end_time: str,
                                                  metric_column: str, remove_outliers: bool = False) -> Optional[
    pd.Series]:
    """
    Get descriptive statistics for TiDB metrics in specified time range

    Args:
        df_tidb: TiDB metric data DataFrame
        start_time: Start timestamp
        end_time: End timestamp
        metric_column: Metric column name (actual value column)
        remove_outliers: Whether to remove outliers

    Returns:
        Metric descriptive statistics, returns None if no data
    """
    if 'timestamp_ns' not in df_tidb.columns:
        return None

    # Time filtering
    start_ts = int(start_time)
    end_ts = int(end_time)
    df_filtered = df_tidb[(df_tidb['timestamp_ns'] >= start_ts) & (df_tidb['timestamp_ns'] <= end_ts)]

    if len(df_filtered) == 0:
        return None

    # Get metric data
    if metric_column not in df_filtered.columns:
        return None

    metric_data = df_filtered[metric_column].dropna()

    if len(metric_data) == 0:
        return None

    # Whether to remove outliers
    if remove_outliers and len(metric_data) > 4:
        metric_data_sorted = metric_data.sort_values()
        metric_data = metric_data_sorted.iloc[2:-2]  # Remove smallest 2 and largest 2
    desc = metric_data.describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])

    # Add non-zero ratio
    desc['non_zero_ratio'] = round((metric_data != 0).sum() / len(metric_data), 3)

    return desc


def _analyze_tidb_services_metrics(df_fault_timestamps: pd.DataFrame, index: int) -> Optional[Dict]:
    """
    Analyze TiDB service metric comparison between fault period and normal periods
    Structure: service → metric → {normal_periods_combined, fault_period}

    Args:
        df_fault_timestamps: Fault timestamp DataFrame
        index: Fault index to analyze

    Returns:
        Dictionary organized by TiDB service containing fault and normal period metric comparisons
    """
    # Get fault time information
    _, date, fault_start, fault_end = _get_fault_period_info(df_fault_timestamps, index)
    normal_periods = _get_normal_time_periods(df_fault_timestamps, index)

    # Get TiDB services and core metrics
    core_metrics = _get_tidb_core_metrics()

    # Organize analysis results by service → metric → time period structure
    tidb_analysis = {}

    for service_name, metrics_list in core_metrics.items():
        # Initialize service structure
        tidb_analysis[service_name] = {}

        for metric_name in metrics_list:
            # Load data for this metric
            df_metric = _load_tidb_service_data(date, service_name, metric_name)

            if df_metric is None:
                continue

            # Initialize metric structure
            tidb_analysis[service_name][metric_name] = {
                'normal_periods_combined': None,
                'fault_period': None
            }

            # 1. Merge all normal period data for statistics
            all_normal_data = []

            for i, (normal_start, normal_end) in enumerate(normal_periods):
                start_ts = int(normal_start)
                end_ts = int(normal_end)
                normal_data = df_metric[(df_metric['timestamp_ns'] >= start_ts) & (df_metric['timestamp_ns'] <= end_ts)]

                if len(normal_data) > 0:
                    all_normal_data.append(normal_data)

            # Merge normal period data and calculate statistics
            if all_normal_data:
                combined_normal_data = pd.concat(all_normal_data, ignore_index=True)

                # Get statistics (remove outliers)
                normal_desc = _get_tidb_metrics_description_with_time_filter(
                    combined_normal_data,
                    str(combined_normal_data['timestamp_ns'].min()),
                    str(combined_normal_data['timestamp_ns'].max()),
                    metric_name,
                    remove_outliers=(len(combined_normal_data) > 4)
                )

                tidb_analysis[service_name][metric_name]['normal_periods_combined'] = normal_desc

            # 2. Fault period statistics
            fault_desc = _get_tidb_metrics_description_with_time_filter(
                df_metric, fault_start, fault_end, metric_name, remove_outliers=False
            )

            tidb_analysis[service_name][metric_name]['fault_period'] = fault_desc

    return tidb_analysis if tidb_analysis else None


# ==================== Core Data Retrieval Function ====================

def _load_filtered_metric(df_fault_timestamps: pd.DataFrame, index: int) -> tuple[str, dict, dict]:
    """
    Load and filter anomaly metric data, only return metrics with significant changes

    Args:
        df_fault_timestamps: Fault timestamp DataFrame
        index: Fault index to analyze

    Returns:
        tuple: (anomaly_metrics_csv, unique_dict, node_pod_mapping)
            - anomaly_metrics_csv: CSV format string of anomaly metrics with significant changes
            - unique_dict: {'service_name': [...], 'node_name': [...], 'pod_name': [...]} unique value dictionary
            - node_pod_mapping: {node_name: [pod1, pod2, ...]} node to Pod mapping
            Returns (None, {}, {}) if no anomalies or error occurs
    """
    # Define key metrics to analyze, added rrt_max metric here
    service_key_metrics = ['client_error_ratio', 'error_ratio', 'request', 'response',
                          'rrt', 'rrt_max', 'server_error_ratio', 'timeout']

    node_metrics_list = ['node_cpu_usage_rate', 'node_disk_read_bytes_total',
                        'node_disk_read_time_seconds_total', 'node_disk_write_time_seconds_total',
                        'node_disk_written_bytes_total', 'node_filesystem_free_bytes',
                        'node_filesystem_usage_rate', 'node_memory_MemAvailable_bytes',
                        'node_memory_MemTotal_bytes', 'node_memory_usage_rate',
                        'node_network_receive_bytes_total', 'node_network_receive_packets_total',
                        'node_network_transmit_bytes_total', 'node_network_transmit_packets_total',
                        'node_sockstat_TCP_inuse']

    pod_metrics_list = ['pod_cpu_usage', 'pod_fs_reads_bytes', 'pod_fs_writes_bytes',
                       'pod_memory_working_set_bytes', 'pod_network_receive_bytes',
                       'pod_network_receive_packets', 'pod_network_transmit_bytes',
                       'pod_network_transmit_packets', 'pod_processes',
                       'container_network_receive_errors_total', 'container_network_transmit_packets_dropped_total']

    result = {
        'fault_info': {},
        'service_metrics': {},
        'tidb_metrics': {},
        'node_metrics': {},
        'pod_metrics': {},
        'node_pod_mapping': {}
    }

    try:
        # Get fault basic information
        row = df_fault_timestamps.iloc[index]
        fault_date = row['date']
        fault_start = row['start_timestamp']
        fault_end = row['end_timestamp']

        # Ensure minimum window of 60 seconds for metric analysis to capture data points
        # Metrics are typically scraped every 15-30s. A 1s fault window will likely have no data.
        min_duration = 60 * 1_000_000_000  # 60 seconds in nanoseconds
        if fault_end - fault_start < min_duration:
            # Extend the window to ensure we capture at least one or two scrape points
            # We extend the end time.
            fault_end = fault_start + min_duration

        result['fault_info'] = {
            'index': int(index),
            'date': str(fault_date),
            'start_timestamp': int(fault_start),
            'end_timestamp': int(fault_end)
        }

        # Collect all data
        service_result = _analyze_fault_vs_normal_metrics_by_service(
            df_fault_timestamps, index, service_key_metrics)
        result['service_metrics'] = service_result if service_result else {}

        tidb_result = _analyze_tidb_services_metrics(df_fault_timestamps, index)
        result['tidb_metrics'] = tidb_result if tidb_result else {}

        node_result = _analyze_node_metrics_by_node(
            df_fault_timestamps, index, node_metrics_list)
        result['node_metrics'] = node_result if node_result else {}

        pod_result = _analyze_pod_metrics_by_pod(
            df_fault_timestamps, index, pod_metrics_list)
        result['pod_metrics'] = pod_result if pod_result else {}

        node_pod_mapping = _get_node_pod_mapping(fault_date)
        result['node_pod_mapping'] = node_pod_mapping if node_pod_mapping else {}

        # Format data to CSV format
        anomaly_metrics_csv, unique_dict = _convert_metrics_to_csv(result)

        return anomaly_metrics_csv, unique_dict, result['node_pod_mapping']

    except Exception:
        return None, {}, {}  # Return None to indicate error, distinguish from empty string (no anomalies)

def metric_analysis_tool(query: str) -> dict:
    """
    Analyze system metric data based on anomaly description or UUID, return metrics with significant changes during that time period.

    Args:
        query: Natural language anomaly query, can be:
               - UUID (e.g., "345fbe93-80")
               - Time range description (e.g., "2025-06-05T16:10:02Z to 2025-06-05T16:31:02Z")
               - Anomaly description text (e.g., "The system experienced an anomaly from 2025-06-05T16:10:02Z to 2025-06-05T16:31:02Z. Please infer the possible cause")

    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - anomaly_metrics: CSV string of anomaly metrics with significant changes (if successful)
        - unique_entities: Contains unique service_name, node_name, pod_name lists
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
                "anomaly_metrics": None,
                "unique_entities": None,
                "node_pod_mapping": None,
                "matched_anomaly": None
            }
            return result

        # Call _load_filtered_metric to get metric data
        anomaly_metrics_csv, metric_unique_dict, node_pod_mapping = _load_filtered_metric(df_input_timestamp, matched_index)

        if anomaly_metrics_csv is None:
            # Error during loading
            result = {
                "status": "error",
                "message": f"Error analyzing metric data. UUID: {matched_row['uuid']}",
                "anomaly_metrics": None,
                "unique_entities": None,
                "node_pod_mapping": None,
                "matched_anomaly": matched_row['Anomaly Description']
            }
            return result

        if anomaly_metrics_csv == "":
            # Analysis succeeded but no anomaly metrics detected
            result = {
                "status": "success",
                "message": f"Analysis completed, no anomaly metrics detected. UUID: {matched_row['uuid']}",
                "anomaly_metrics": None,
                "unique_entities": metric_unique_dict,
                "node_pod_mapping": node_pod_mapping,
                "matched_anomaly": matched_row['Anomaly Description'],
                "time_range": f"{matched_row['start_time_utc']} to {matched_row['end_time_utc']}"
            }
            return result

        # Success with anomaly metrics
        result = {
            "status": "success",
            "message": f"Successfully loaded metric data. UUID: {matched_row['uuid']}",
            "anomaly_metrics": anomaly_metrics_csv,
            "unique_entities": metric_unique_dict,
            "node_pod_mapping": node_pod_mapping,
            "matched_anomaly": matched_row['Anomaly Description'],
            "time_range": f"{matched_row['start_time_utc']} to {matched_row['end_time_utc']}"
        }

        return result

    except Exception as e:
        result = {
            "status": "error",
            "message": f"Error during metric analysis: {str(e)}",
            "anomaly_metrics": None,
            "unique_entities": None,
            "node_pod_mapping": None,
            "matched_anomaly": None
        }
        return result


