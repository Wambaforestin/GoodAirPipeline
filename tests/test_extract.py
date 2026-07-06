import pytest
from unittest.mock import patch, MagicMock
import requests
from src.extract.extract_apis import (
    extract_openweathermap,
    extract_aqicn,
    save_to_bronze,
    run_extract,
)

#  TESTS FOR extract_openweathermap


def test_extract_openweathermap_success():
    """Test successful API call returns data."""
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"weather": [{"main": "Clear"}]}
        mock_get.return_value = mock_response

        result = extract_openweathermap("Paris", "FR", "test_key")
        assert result == {"weather": [{"main": "Clear"}]}


def test_extract_openweathermap_city_not_found():
    """Test 404 (city not found) returns None."""
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        result = extract_openweathermap("FakeCity", "FR", "test_key")
        assert result is None


def test_extract_openweathermap_server_error():
    """Test HTTP errors (401, 500, etc.) raise exception."""
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "Unauthorized"
        )
        mock_get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            extract_openweathermap("Paris", "FR", "test_key")


# ========== TESTS FOR extract_aqicn ==========


def test_extract_aqicn_success():
    """Test successful AQICN call returns data."""
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok", "data": {"aqi": 50}}
        mock_get.return_value = mock_response

        result = extract_aqicn("Paris", "test_key")
        assert result == {"status": "ok", "data": {"aqi": 50}}


def test_extract_aqicn_non_ok_status():
    """Test non-ok status returns None."""
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "error"}
        mock_get.return_value = mock_response

        result = extract_aqicn("Paris", "test_key")
        assert result is None


# ========== TESTS FOR save_to_bronze ==========


def test_save_to_bronze_creates_bucket():
    """Test bucket is created if it doesn't exist."""
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = False
    test_data = {"test": "data"}

    save_to_bronze(mock_client, "test-bucket", test_data, "path/", "file.json")
    mock_client.make_bucket.assert_called_once_with("test-bucket")


def test_save_to_bronze_saves_data():
    """Test data is saved to MinIO with correct parameters."""
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    test_data = {"city": "Paris", "temp": 20}

    save_to_bronze(mock_client, "bronze", test_data, "2023/01/01/", "paris.json")

    mock_client.put_object.assert_called_once()
    args, kwargs = mock_client.put_object.call_args
    assert kwargs["bucket_name"] == "bronze"
    assert "2023/01/01/paris.json" in kwargs["object_name"]
    assert kwargs["content_type"] == "application/json"


# ========== TESTS FOR run_extract ==========


@patch("src.extract.extract_apis.load_cities_config")
@patch("src.extract.extract_apis.get_minio_client")
@patch("src.extract.extract_apis.get_partition_path")
@patch("src.extract.extract_apis.extract_openweathermap")
@patch("src.extract.extract_apis.extract_aqicn")
@patch("src.extract.extract_apis.save_to_bronze")
@patch.dict(
    "os.environ",
    {
        "OWM_API_KEY": "test_owm_key",
        "AQICN_API_KEY": "test_aqicn_key",
        "MINIO_BUCKET_BRONZE": "test_bronze_bucket",
    },
)
def test_run_extract_success(
    mock_save, mock_aqicn, mock_owm, mock_partition, mock_minio, mock_cities
):
    """Test full extraction workflow with all APIs succeeding."""
    mock_cities.return_value = [
        {"city": "Paris", "country": "FR"},
        {"city": "London", "country": "UK"},
    ]
    mock_minio.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"

    mock_owm.return_value = {"weather": [{"main": "Clear"}]}
    mock_aqicn.return_value = {"status": "ok", "data": {"aqi": 50}}

    run_extract("2023-01-01")

    assert mock_owm.call_count == 2
    assert mock_aqicn.call_count == 2
    assert mock_save.call_count == 4  # 2 cities × 2 APIs


@patch("src.extract.extract_apis.load_cities_config")
@patch("src.extract.extract_apis.get_minio_client")
@patch("src.extract.extract_apis.get_partition_path")
@patch("src.extract.extract_apis.extract_openweathermap")
@patch("src.extract.extract_apis.extract_aqicn")
@patch("src.extract.extract_apis.save_to_bronze")
@patch.dict(
    "os.environ",
    {
        "OWM_API_KEY": "test_owm_key",
        "AQICN_API_KEY": "test_aqicn_key",
        "MINIO_BUCKET_BRONZE": "test_bronze_bucket",
    },
)
def test_run_extract_partial_failure(
    mock_save, mock_aqicn, mock_owm, mock_partition, mock_minio, mock_cities
):
    """Test workflow when one API fails (returns None)."""
    mock_cities.return_value = [{"city": "Paris", "country": "FR"}]
    mock_minio.return_value = MagicMock()
    mock_partition.return_value = "2023/01/01/"

    mock_owm.return_value = {"weather": [{"main": "Clear"}]}
    mock_aqicn.return_value = None  # Simulate AQICN failure

    run_extract("2023-01-01")

    assert mock_save.call_count == 1  # Only OpenWeatherMap data saved
