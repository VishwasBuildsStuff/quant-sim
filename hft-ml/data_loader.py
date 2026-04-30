"""
Data Loader for HFT Training Pipeline
Supports: TimescaleDB, Parquet files, Kafka streams
"""

import os
import numpy as np
import pandas as pd
from typing import Iterator, Tuple, List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import pytz


@dataclass
class DataConfig:
    """Data loading configuration"""
    symbol: str
    asset_class: str  # 'equity' or 'future'
    n_levels: int = 10
    start_date: str = "2025-01-01"
    end_date: str = "2025-01-31"
    exchange: str = "NSE"  # NSE, CME, etc.
    data_dir: str = "./data"


class LOBDataLoader:
    """
    Loads LOB snapshots from various sources
    Optimized for sequential access during training
    """

    def __init__(self, config: DataConfig):
        self.config = config
        self.cache = {}
        self.current_idx = 0

    def load_from_parquet(self, filepath: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Load LOB data from parquet file

        Expected columns:
        - timestamp_ns
        - bid_price_1..10, bid_volume_1..10
        - ask_price_1..10, ask_volume_1..10
        - last_trade_price, last_trade_volume, trade_side
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Parquet file not found: {filepath}")

        df = pd.read_parquet(filepath)
        df = df.sort_values('timestamp_ns').reset_index(drop=True)

        n = len(df)
        n_levels = self.config.n_levels

        # Extract LOB arrays
        bid_prices = np.zeros((n, n_levels), dtype=np.float64)
        bid_volumes = np.zeros((n, n_levels), dtype=np.float64)
        ask_prices = np.zeros((n, n_levels), dtype=np.float64)
        ask_volumes = np.zeros((n, n_levels), dtype=np.float64)

        for i in range(n_levels):
            bid_prices[:, i] = df[f'bid_price_{i+1}'].values
            bid_volumes[:, i] = df[f'bid_volume_{i+1}'].values
            ask_prices[:, i] = df[f'ask_price_{i+1}'].values
            ask_volumes[:, i] = df[f'ask_volume_{i+1}'].values

        timestamps = df['timestamp_ns'].values.astype(np.int64)
        last_trade_price = df['last_trade_price'].values.astype(np.float64)
        last_trade_volume = df['last_trade_volume'].values.astype(np.float64)
        trade_side = df['trade_side'].values.astype(np.int8)

        return {
            'bid_prices': bid_prices,
            'bid_volumes': bid_volumes,
            'ask_prices': ask_prices,
            'ask_volumes': ask_volumes,
            'timestamps': timestamps,
            'last_trade_price': last_trade_price,
            'last_trade_volume': last_trade_volume,
            'trade_side': trade_side
        }

    def load_from_timescaledb(self, connection_string: str) -> Dict[str, np.ndarray]:
        """Load from TimescaleDB (PostgreSQL extension)"""
        try:
            import psycopg2
            from psycopg2.extras import execute_values

            conn = psycopg2.connect(connection_string)
            cursor = conn.cursor()

            query = f"""
                SELECT
                    extract(epoch from timestamp) * 1e9 as timestamp_ns,
                    bid_prices, bid_volumes,
                    ask_prices, ask_volumes,
                    last_trade_price, last_trade_volume, trade_side
                FROM lob_snapshots
                WHERE symbol = %s
                    AND timestamp >= %s
                    AND timestamp <= %s
                ORDER BY timestamp
            """

            cursor.execute(query, (
                self.config.symbol,
                self.config.start_date,
                self.config.end_date
            ))

            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            # Convert to numpy arrays
            # ... (parsing logic)

            return {}  # Return structured dict like load_from_parquet

        except ImportError:
            raise ImportError("Install psycopg2: pip install psycopg2-binary")

    def create_training_batches(self,
                                data: Dict[str, np.ndarray],
                                sequence_length: int = 100,
                                batch_size: int = 256) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        """
        Create training batches for sequence models

        Yields:
            X: (batch_size, sequence_length, n_features)
            timestamps: (batch_size,)
        """
        n_samples = len(data['timestamps'])
        n_levels = self.config.n_levels

        # Pre-compute features for efficiency
        mid_prices = (data['bid_prices'][:, 0] + data['ask_prices'][:, 0]) / 2.0
        spreads = data['ask_prices'][:, 0] - data['bid_prices'][:, 0]

        indices = np.arange(sequence_length, n_samples)
        np.random.shuffle(indices)

        for start in range(0, len(indices), batch_size):
            batch_indices = indices[start:start + batch_size]

            if len(batch_indices) < batch_size:
                continue

            # Create sequences
            X_sequences = []
            timestamps = []

            for idx in batch_indices:
                seq_start = idx - sequence_length

                # Build feature vector per timestep
                seq = np.zeros((sequence_length, n_levels * 4 + 5))

                for t in range(sequence_length):
                    i = seq_start + t
                    features = np.concatenate([
                        data['bid_prices'][i],       # 10 levels
                        data['bid_volumes'][i],      # 10 levels
                        data['ask_prices'][i],       # 10 levels
                        data['ask_volumes'][i],      # 10 levels
                        [data['last_trade_price'][i],
                         data['last_trade_volume'][i],
                         data['trade_side'][i],
                         mid_prices[i],
                         spreads[i]]                 # 5 scalars
                    ])
                    seq[t] = features

                X_sequences.append(seq)
                timestamps.append(data['timestamps'][idx])

            yield np.array(X_sequences, dtype=np.float32), np.array(timestamps, dtype=np.int64)

    def load_multiple_symbols(self,
                              symbols: List[str],
                              date_range: Tuple[str, str]) -> Dict[str, Dict[str, np.ndarray]]:
        """Load data for multiple symbols (for multi-asset models)"""
        all_data = {}

        for symbol in symbols:
            filepath = os.path.join(
                self.config.data_dir,
                symbol,
                f"{date_range[0]}_{date_range[1]}.parquet"
            )

            if os.path.exists(filepath):
                all_data[symbol] = self.load_from_parquet(filepath)
                print(f"Loaded {symbol}: {len(all_data[symbol]['timestamps'])} snapshots")
            else:
                print(f"File not found: {filepath}")

        return all_data


class DataIntegrityChecker:
    """
    Validates data quality and checks for common issues
    """

    def __init__(self):
        self.issues = []

    def validate_lob_data(self, data: Dict[str, np.ndarray]) -> List[str]:
        """Comprehensive data validation"""
        self.issues = []

        # Check for NaN/Inf
        for key in ['bid_prices', 'ask_prices', 'bid_volumes', 'ask_volumes']:
            arr = data[key]
            if np.any(np.isnan(arr)):
                self.issues.append(f"NaN values found in {key}")
            if np.any(np.isinf(arr)):
                self.issues.append(f"Inf values found in {key}")

        # Check bid < ask (no crossed books)
        crossed = data['bid_prices'][:, 0] >= data['ask_prices'][:, 0]
        if np.any(crossed):
            self.issues.append(f"Crossed book detected: {np.sum(crossed)} timestamps")

        # Check timestamp ordering
        timestamps = data['timestamps']
        if np.any(np.diff(timestamps) <= 0):
            self.issues.append("Timestamps not strictly increasing")

        # Check for exchange downtime (gaps > 1 second)
        gaps = np.diff(timestamps)
        large_gaps = gaps > 1e9  # 1 second in nanoseconds
        if np.any(large_gaps):
            n_gaps = np.sum(large_gaps)
            self.issues.append(f"Exchange downtime: {n_gaps} gaps > 1s")

        # Check volumes non-negative
        if np.any(data['bid_volumes'] < 0) or np.any(data['ask_volumes'] < 0):
            self.issues.append("Negative volumes detected")

        # Check prices positive
        if np.any(data['bid_prices'] <= 0) or np.any(data['ask_prices'] <= 0):
            self.issues.append("Non-positive prices detected")

        # Check for look-ahead bias (features should only use past data)
        # This is validated during feature engineering

        if self.issues:
            print(f"Data integrity issues found: {len(self.issues)}")
            for issue in self.issues:
                print(f"  - {issue}")
        else:
            print("Data integrity checks passed")

        return self.issues

    def align_timestamps(self,
                         data1: Dict[str, np.ndarray],
                         data2: Dict[str, np.ndarray],
                         tolerance_ns: int = 1_000_000) -> Tuple[Dict, Dict]:
        """
        Align two data streams by timestamp (for multi-asset)

        Args:
            tolerance_ns: Maximum allowed timestamp difference (default 1ms)
        """
        ts1 = data1['timestamps']
        ts2 = data2['timestamps']

        # Find common timestamps
        common_mask1 = np.isin(ts1, ts2, assume_unique=True)
        common_mask2 = np.isin(ts2, ts1, assume_unique=True)

        # Apply mask
        aligned1 = {k: v[common_mask1] for k, v in data1.items()}
        aligned2 = {k: v[common_mask2] for k, v in data2.items()}

        print(f"Aligned: {len(ts1)} -> {len(aligned1['timestamps'])} common timestamps")

        return aligned1, aligned2
