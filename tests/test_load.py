import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, Mock
from io import BytesIO
import pyarrow.parquet as pq
from src.load.load_gold import (
    read_silver_parquet,
    truncate_staging,
    load_to_staging,
    execute_merge,
    run_load,
)

# ========== FIXTURES ==========


@pytest.fixture
def mock_minio_client():
    """Mock MinIO client for testing."""
    return MagicMock()


@pytest.fixture
def mock_engine():
    """Mock SQLAlchemy engine for testing."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    return mock_engine


@pytest.fixture
def sample_silver_df():
    """Sample DataFrame matching Silver layer structure."""
    return pd.DataFrame(
        {
            "NomVille": ["Paris", "London"],
            "CodePays": ["FR", "UK"],
            "Latitude": [48.85, 51.50],
            "Longitude": [2.35, -0.12],
            "IDTemps": [2023010112, 2023010112],
            "Temperature": [20.0, 18.0],
            "Humidite": [65, 70],
            "Pression": [1012, 1010],
            "VitesseVent": [3.2, 4.1],
            "AqiGlobal": [42, 38],
            "PM25": [12.0, 10.0],
            "PM10": [18.0, 15.0],
            "NO2": [25.0, 20.0],
            "O3": [30.0, 28.0],
            "MeteoStatus": ["OK", "OK"],
            "AirStatus": ["OK", "OK"],
        }
    )


@pytest.fixture
def mock_run_date():
    """Mock run_date for consistent testing."""
    from datetime import datetime

    return datetime(2023, 1, 1, 12, 0)


# ========== TESTS FOR read_silver_parquet ==========


def test_read_silver_parquet_success(mock_minio_client, sample_silver_df):
    """Test reading Parquet file from MinIO."""
    # Create a real Parquet buffer from the sample DataFrame
    buffer = BytesIO()
    table = pq.Table.from_pandas(sample_silver_df)
    pq.write_table(table, buffer)
    buffer.seek(0)

    mock_response = MagicMock()
    mock_response.read.return_value = buffer.getvalue()
    mock_minio_client.get_object.return_value = mock_response

    result = read_silver_parquet(
        mock_minio_client, "silver", "2023/01/01/mesures.parquet"
    )
    pd.testing.assert_frame_equal(result, sample_silver_df)


def test_read_silver_parquet_file_not_found(mock_minio_client):
    """Test when file is not found."""
    mock_minio_client.get_object.side_effect = Exception("File not found")
    with pytest.raises(Exception):
        read_silver_parquet(mock_minio_client, "silver", "nonexistent.parquet")


# ========== TESTS FOR truncate_staging ==========


def test_truncate_staging(mock_engine):
    """Test that staging tables are truncated."""
    truncate_staging(mock_engine)
    mock_engine.connect.assert_called_once()
    # Verify TRUNCATE was called for all 3 tables
    assert (
        mock_engine.connect.return_value.__enter__.return_value.execute.call_count == 3
    )


# ========== TESTS FOR load_to_staging ==========


def test_load_to_staging_creates_dim_tables(
    mock_engine, sample_silver_df, mock_run_date
):
    """Test that data is loaded into all 3 staging tables."""
    load_to_staging(mock_engine, sample_silver_df, mock_run_date)

    # Check calls to to_sql
    calls = (
        mock_engine.connect.return_value.__enter__.return_value.execute.call_args_list
    )
    # Should have calls for DimLieux_Temp, DimTemps_Temp, FactMesures_Temp
    assert len(calls) == 3

    # Verify DimLieux_Temp has unique cities
    lieux_call = [c for c in calls if "DimLieux_Temp" in str(c)][0]
    assert "DimLieux_Temp" in str(lieux_call)

    # Verify DimTemps_Temp has time data
    temps_call = [c for c in calls if "DimTemps_Temp" in str(c)][0]
    assert "DimTemps_Temp" in str(temps_call)

    # Verify FactMesures_Temp has all fact columns
    facts_call = [c for c in calls if "FactMesures_Temp" in str(c)][0]
    assert "FactMesures_Temp" in str(facts_call)


def test_load_to_staging_empty_dataframe(mock_engine, mock_run_date):
    """Test with empty DataFrame."""
    df = pd.DataFrame()
    load_to_staging(mock_engine, df, mock_run_date)
    # Should still create DimTemps_Temp with run_date
    mock_engine.connect.return_value.__enter__.return_value.execute.assert_called()


# ========== TESTS FOR execute_merge ==========


def test_execute_merge(mock_engine):
    """Test that MERGE operations are executed in order."""
    execute_merge(mock_engine, batch_id=1)

    # Verify all 3 SQL operations were executed
    calls = (
        mock_engine.connect.return_value.__enter__.return_value.execute.call_args_list
    )
    assert len(calls) == 3

    # Check order: DimLieux, DimTemps, FactMesures
    assert "DimLieux" in str(calls[0])
    assert "DimTemps" in str(calls[1])
    assert "FactMesures" in str(calls[2])


def test_execute_merge_with_batch_id(mock_engine):
    """Test that batch_id is passed to MERGE query."""
    execute_merge(mock_engine, batch_id=42)
    # The last call should contain the batch_id
    last_call = (
        mock_engine.connect.return_value.__enter__.return_value.execute.call_args_list[
            -1
        ]
    )
    assert last_call.kwargs.get("batch_id") == 42


# ========== TESTS FOR run_load ==========


@patch("src.load.load_gold.get_minio_client")
@patch("src.load.load_gold.get_sql_engine")
@patch("src.load.load_gold.get_partition_path")
@patch("src.load.load_gold.read_silver_parquet")
@patch("src.load.load_gold.truncate_staging")
@patch("src.load.load_gold.load_to_staging")
@patch("src.load.load_gold.execute_merge")
@patch.dict("os.environ", {"MINIO_BUCKET_SILVER": "silver"})
def test_run_load_success(
    mock_execute_merge,
    mock_load,
    mock_truncate,
    mock_read,
    mock_partition,
    mock_engine,
    mock_minio,
    sample_silver_df,
    mock_run_date,
):
    """Test full load workflow with valid data."""
    mock_minio.return_value = MagicMock()
    mock_engine.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"
    mock_read.return_value = sample_silver_df

    result = run_load(mock_run_date, batch_id=1)

    # Should not return False (which indicates failure)
    assert result is None
    mock_truncate.assert_called_once()
    mock_load.assert_called_once()
    mock_execute_merge.assert_called_once_with(mock_engine.return_value, 1)


@patch("src.load.load_gold.get_minio_client")
@patch("src.load.load_gold.get_sql_engine")
@patch("src.load.load_gold.get_partition_path")
@patch("src.load.load_gold.read_silver_parquet")
@patch.dict("os.environ", {"MINIO_BUCKET_SILVER": "silver"})
def test_run_load_empty_silver(
    mock_read, mock_partition, mock_engine, mock_minio, mock_run_date
):
    """Test that run_load returns early when Silver is empty."""
    mock_minio.return_value = MagicMock()
    mock_engine.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"
    mock_read.return_value = pd.DataFrame()  # Empty DataFrame

    result = run_load(mock_run_date, batch_id=1)
    assert result is None  # Returns None, doesn't raise


@patch("src.load.load_gold.get_minio_client")
@patch("src.load.load_gold.get_sql_engine")
@patch("src.load.load_gold.get_partition_path")
@patch("src.load.load_gold.read_silver_parquet")
@patch.dict("os.environ", {"MINIO_BUCKET_SILVER": "silver"})
def test_run_load_missing_columns(
    mock_read, mock_partition, mock_engine, mock_minio, mock_run_date
):
    """Test that run_load raises AssertionError when columns are missing."""
    mock_minio.return_value = MagicMock()
    mock_engine.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"

    # DataFrame missing required columns
    bad_df = pd.DataFrame({"NomVille": ["Paris"], "Temperature": [20]})
    mock_read.return_value = bad_df

    with pytest.raises(AssertionError) as excinfo:
        run_load(mock_run_date, batch_id=1)
    assert "Colonnes manquantes" in str(excinfo.value)


@patch("src.load.load_gold.get_minio_client")
@patch("src.load.load_gold.get_sql_engine")
@patch("src.load.load_gold.get_partition_path")
@patch("src.load.load_gold.read_silver_parquet")
@patch.dict("os.environ", {"MINIO_BUCKET_SILVER": "silver"})
def test_run_load_read_failure(
    mock_read, mock_partition, mock_engine, mock_minio, mock_run_date
):
    """Test that run_load raises when reading Silver fails."""
    mock_minio.return_value = MagicMock()
    mock_engine.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"
    mock_read.side_effect = Exception("Read error")

    with pytest.raises(Exception) as excinfo:
        run_load(mock_run_date, batch_id=1)
    assert "Impossible de lire Silver" in str(excinfo.value)
