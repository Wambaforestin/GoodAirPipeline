import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.transform.transform_silver import (
    flatten_openweathermap,
    flatten_aqicn,
    apply_cleaning_rules,
    save_to_silver,
    run_transform,
    ALL_EXPECTED_COLUMNS,
)

# ========== FIXTURES ==========


@pytest.fixture
def mock_minio_client():
    """Mock MinIO client for testing."""
    return MagicMock()


@pytest.fixture
def sample_owm_data():
    """Sample OpenWeatherMap API response."""
    return {
        "coord": {"lon": 2.35, "lat": 48.85},
        "sys": {"country": "FR"},
        "main": {
            "temp": 22.5,
            "humidity": 65,
            "pressure": 1012,
        },
        "wind": {"speed": 3.2},
    }


@pytest.fixture
def sample_aqicn_data():
    """Sample AQICN API response."""
    return {
        "status": "ok",
        "data": {
            "aqi": 42,
            "iaqi": {
                "pm25": {"v": 12.0},
                "pm10": {"v": 18.0},
                "no2": {"v": 25.0},
                "o3": {"v": 30.0},
            },
        },
    }


@pytest.fixture
def mock_run_date():
    """Mock run_date for consistent testing."""
    from datetime import datetime

    return datetime(2023, 1, 1, 12, 0)  # 2023-01-01 12:00


# ========== TESTS FOR flatten_openweathermap ==========


def test_flatten_openweathermap_full_data(sample_owm_data, mock_run_date):
    """Test flattening with all fields present."""
    result = flatten_openweathermap(sample_owm_data, "Paris", mock_run_date)
    assert result["NomVille"] == "Paris"
    assert result["CodePays"] == "FR"
    assert result["Latitude"] == 48.85
    assert result["Longitude"] == 2.35
    assert result["Temperature"] == 22.5
    assert result["IDTemps"] == 2023010112


def test_flatten_openweathermap_missing_fields():
    """Test flattening with missing fields returns None for those fields."""
    minimal_data = {"sys": {}, "coord": {}, "main": {}, "wind": {}}
    from datetime import datetime

    run_date = datetime(2023, 1, 1, 12, 0)
    result = flatten_openweathermap(minimal_data, "Paris", run_date)
    assert result["NomVille"] == "Paris"
    assert result["CodePays"] is None
    assert result["Temperature"] is None
    assert result["IDTemps"] == 2023010112


# ========== TESTS FOR flatten_aqicn ==========


def test_flatten_aqicn_full_data(sample_aqicn_data, mock_run_date):
    """Test flattening with all AQICN fields present."""
    result = flatten_aqicn(sample_aqicn_data, "Paris", mock_run_date)
    assert result["NomVille"] == "Paris"
    assert result["AqiGlobal"] == 42
    assert result["PM25"] == 12.0
    assert result["PM10"] == 18.0
    assert result["IDTemps"] == 2023010112


def test_flatten_aqicn_missing_iaqi():
    """Test flattening when iaqi data is missing."""
    data = {"status": "ok", "data": {"aqi": 50, "iaqi": {}}}
    from datetime import datetime

    run_date = datetime(2023, 1, 1, 12, 0)
    result = flatten_aqicn(data, "Paris", run_date)
    assert result["AqiGlobal"] == 50
    assert result["PM25"] is None
    assert result["PM10"] is None


# ========== TESTS FOR ensure_all_columns ==========


def test_ensure_all_columns_adds_missing():
    """Test that missing columns are added with NA."""
    df = pd.DataFrame({"NomVille": ["Paris"], "Temperature": [20]})
    result, _ = apply_cleaning_rules(df)  # ensure_all_columns is called inside
    for col in ALL_EXPECTED_COLUMNS:
        assert col in result.columns


# ========== TESTS FOR apply_cleaning_rules ==========


def test_apply_cleaning_rules_numeric_conversion():
    """Test that non-numeric values become NA."""
    df = pd.DataFrame(
        {"Temperature": ["20", "invalid", 25], "Humidite": [60, 70, "80"]}
    )
    result, _ = apply_cleaning_rules(df)
    assert pd.isna(result.loc[1, "Temperature"])  # "invalid" → NA
    assert result.loc[0, "Temperature"] == 20.0
    assert result.loc[2, "Temperature"] == 25.0


def test_apply_cleaning_rules_codepays_fillna():
    """Test that missing CodePays becomes 'ND'."""
    df = pd.DataFrame({"CodePays": [None, "FR", None]})
    result, _ = apply_cleaning_rules(df)
    assert result["CodePays"].iloc[0] == "ND"
    assert result["CodePays"].iloc[1] == "FR"


def test_apply_cleaning_rules_status_flags():
    """Test that MeteoStatus and AirStatus are set correctly."""
    df = pd.DataFrame(
        {
            "Temperature": [20, None],
            "AqiGlobal": [42, None],
        }
    )
    result, _ = apply_cleaning_rules(df)
    assert result["MeteoStatus"].iloc[0] == "OK"
    assert result["MeteoStatus"].iloc[1] == "FAILED"
    assert result["AirStatus"].iloc[0] == "OK"
    assert result["AirStatus"].iloc[1] == "FAILED"


def test_apply_cleaning_rules_dead_rows():
    """Test that rows with all NA metrics are rejected."""
    df = pd.DataFrame(
        {
            "NomVille": ["Paris", "London"],
            "IDTemps": [2023010112, 2023010112],
            "Temperature": [20, None],
            "AqiGlobal": [None, None],
            "PM25": [None, None],
        }
    )
    valid, rejects = apply_cleaning_rules(df)
    assert len(valid) == 1  # Paris has Temperature
    assert len(rejects) == 1  # London has all NA metrics


def test_apply_cleaning_rules_deduplication():
    """Test that duplicates are removed."""
    df = pd.DataFrame(
        {
            "NomVille": ["Paris", "Paris"],
            "IDTemps": [2023010112, 2023010112],
            "Temperature": [20, 25],
        }
    )
    valid, _ = apply_cleaning_rules(df)
    assert len(valid) == 1  # Duplicate removed
    assert valid["Temperature"].iloc[0] == 25  # Last value kept


# ========== TESTS FOR save_to_silver ==========


def test_save_to_silver_creates_bucket(mock_minio_client):
    """Test that bucket is created if it doesn't exist."""
    mock_minio_client.bucket_exists.return_value = False
    df = pd.DataFrame({"NomVille": ["Paris"]})

    save_to_silver(mock_minio_client, "test-silver", df, "path/", "test.parquet")
    mock_minio_client.make_bucket.assert_called_once_with("test-silver")


def test_save_to_silver_saves_parquet(mock_minio_client):
    """Test that DataFrame is saved as Parquet."""
    mock_minio_client.bucket_exists.return_value = True
    df = pd.DataFrame({"NomVille": ["Paris"], "Temperature": [20]})

    save_to_silver(mock_minio_client, "silver", df, "2023/01/01/", "data.parquet")

    mock_minio_client.put_object.assert_called_once()
    args, kwargs = mock_minio_client.put_object.call_args
    assert kwargs["bucket_name"] == "silver"
    assert "2023/01/01/data.parquet" in kwargs["object_name"]
    assert kwargs["content_type"] == "application/octet-stream"


# ========== TESTS FOR run_transform ==========


@patch("src.transform.transform_silver.load_cities_config")
@patch("src.transform.transform_silver.get_minio_client")
@patch("src.transform.transform_silver.get_partition_path")
@patch("src.transform.transform_silver.read_bronze_json")
@patch("src.transform.transform_silver.save_to_silver")
@patch.dict(
    "os.environ", {"MINIO_BUCKET_BRONZE": "bronze", "MINIO_BUCKET_SILVER": "silver"}
)
def test_run_transform_success(
    mock_save, mock_read, mock_partition, mock_minio, mock_cities, mock_run_date
):
    """Test full transformation workflow with valid data."""
    mock_cities.return_value = [{"city": "Paris", "country": "FR"}]
    mock_minio.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"

    # Mock successful reads
    mock_read.side_effect = [
        {
            "coord": {"lon": 2.35, "lat": 48.85},
            "sys": {"country": "FR"},
            "main": {"temp": 20},
        },
        {"status": "ok", "data": {"aqi": 42, "iaqi": {"pm25": {"v": 12}}}},
    ]

    result = run_transform(mock_run_date)
    assert result is True
    assert mock_save.call_count == 2  # Valid + rejects


@patch("src.transform.transform_silver.load_cities_config")
@patch("src.transform.transform_silver.get_minio_client")
@patch("src.transform.transform_silver.get_partition_path")
@patch("src.transform.transform_silver.read_bronze_json")
@patch.dict(
    "os.environ", {"MINIO_BUCKET_BRONZE": "bronze", "MINIO_BUCKET_SILVER": "silver"}
)
def test_run_transform_no_data(
    mock_read, mock_partition, mock_minio, mock_cities, mock_run_date
):
    """Test that run_transform returns False when no data is found."""
    mock_cities.return_value = [{"city": "Paris", "country": "FR"}]
    mock_minio.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"

    # Simulate missing files
    mock_read.side_effect = Exception("File not found")

    result = run_transform(mock_run_date)
    assert result is False
