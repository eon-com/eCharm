"""Module to extract and map the raw data from the datasource to internal DB data model."""

import logging
from typing import Final, Optional, TypeVar

import pandas as pd
from geoalchemy2 import WKBElement
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from charging_stations_pipelines.models.address import Address
from charging_stations_pipelines.models.charging import Charging
from charging_stations_pipelines.models.station import Station
from charging_stations_pipelines.pipelines.at import DATA_SOURCE_KEY
from charging_stations_pipelines.shared import check_coordinates, lst_flatten, \
    str_strip_whitespace, str_to_float, try_remove_dupes

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _aggregate_attribute(points: pd.Series, attr: str) -> list[list[T]]:
    attr_list_agg: Final[list[list[T]]] = []
    for p in points:
        attr_vals: list = p.get(attr, [])
        attr_list_agg.append(attr_vals)

    return attr_list_agg


def _extract_auth_modes(points: pd.Series) -> list[str]:
    # Aggregate authentication modes
    auth_modes_agg = _aggregate_attribute(points, "authenticationModes")
    flattened_auth_modes_agg = lst_flatten(auth_modes_agg)
    auth_modes_list = try_remove_dupes(flattened_auth_modes_agg)

    return sorted(auth_modes_list)


def _extract_location(location: pd.Series) -> Optional[WKBElement]:
    lon = check_coordinates(location.get("longitude"))
    lat = check_coordinates(location.get("latitude"))

    return from_shape(Point(lon, lat)) if lon and lat else None


def map_station(row: pd.Series) -> Station:
    """Maps the data from the given pandas Series (row) to create a Station object for storage in the DB.

    :param row: A pandas "row", representing the raw data of a station.
    :return: A Station object.

    The row object should have the following attributes:

    - 'points': A list of dictionaries representing the charging points of the station.

    The Station object will have the following attributes:

    - 'country_code': A string representing the country code of the station. It should always be 'AT'.
    - 'source_id': A string representing the source ID of the station.
    - 'operator': A string representing the operator of the station.
    - 'payment': The payment information for the station is not available in the data source.
    - 'authentication': A list of authentication modes supported by the station, extracted from the 'points' \
      attribute of the row dictionary.
    - 'data_source': A string representing the data source key.
    - 'point': GPS coordinates of the station.
    - 'raw_data': The unchanged data point as it comes from the datasource, stored in DB as type 'JSON'.
    - 'date_created': The creation date of the station.
    - 'date_updated': The update date of the station.
    """
    # TODO following attributes are also available in the data source
    #  1. status          9469 non-null
    #  2. label           9469 non-null
    #  3. description     5668 non-null
    #  4. openingHours    9469 non-null
    #  5. priceUrl        2880 non-null
    #  ...
    #  6. evseCountryId   9469 non-null
    #  7. evseStationId   9469 non-null
    #  8. evseOperatorId  9469 non-null

    country_id, operator_id, station_id = str_strip_whitespace(
        row.get(["evseCountryId", "evseOperatorId", "evseStationId"]))

    station = Station()

    station.country_code = country_id  # should be always 'AT'
    # Using combination of evseCountryId, evseStationId and evseOperatorId as source_id,
    # since evseStationId alone is not unique enough
    station.source_id = f'{country_id}*{operator_id}*{station_id}'

    # there are also other attributes available in the data source,
    # which could be useful for the `operator`, e.g.:
    # 1. `contactName`, e.g.: "E-Werk der Stadtgemeinde Kindberg"
    # 2. `label`, e.g.: "Ladestelle Roßdorf Platz"
    station.operator = operator_id  # evseOperatorId, e.g. "014"

    station.payment = None
    station.authentication = _extract_auth_modes(row.get("points")) or None
    station.data_source = DATA_SOURCE_KEY
    station.point = _extract_location(row.get("location"))
    station.raw_data = row.to_json()  # Note: is stored in DB as native type 'JSON'
    station.date_created = None  # Note: is not available in the data source
    station.date_updated = None  # Note: is not available in the data source

    return station


def map_address(row: pd.Series, station_id: Optional[int]) -> Address:
    """Maps the given raw datapoint to an Address object.

    :param row: A datapoint representing the raw data.
    :param station_id: An integer representing the station ID.
    :return: An Address object.
    """
    # TODO following attributes are also available in the data source:
    #  1. contactName     9469 non-null
    #  2. telephone       8615 non-null
    #  3. email           2358 non-null
    #  4. website         4951 non-null
    address = Address()

    address.station_id = station_id
    address.street = str_strip_whitespace(row.get("street")) or None
    address.town = str_strip_whitespace(row.get("city")) or None
    address.postcode = str_strip_whitespace(row.get("postCode")) or None
    address.district = None  # Note: is not available in the data source
    address.district = None  # Note: is not available in the data source
    address.state = None  # Note: is not available in the data source
    address.state = None  # Note: is not available in the data source
    address.country = str_strip_whitespace(row.get("evseCountryId")) or None

    return address

# FIXME: write unittests
def _lst_expand(aggregated_list: list[tuple[float, int]]) -> list[float]:
    """Repeats float value according to its count in the input list.

    :param aggregated_list: A list of tuples where each tuple contains a float value and the count of how often
        the value occurs.
    :return: A new list where each float value is repeated according to its count in the input list.

    Example:
    >>> _lst_expand([(1.0, 3), (2.5, 2)])
    [1.0, 1.0, 1.0, 2.5, 2.5]
    """
    # [0] - float value, [1] - count, how often this value occurs
    return [e[0] for e in aggregated_list for _ in range(e[1])] if aggregated_list else []


def _extract_charger_details(points: pd.Series) -> tuple[list[float], list[str]]:
    # Aggregate energy_in_kw
    kw_list_agg: Final[list[tuple[float, int]]] = []
    for p in points:
        energy_in_kw = str_to_float(p.get("energyInKw"))
        kw_list_agg.append((energy_in_kw, len(p.get("connectorTypes", []) or [])))
    kw_list = _lst_expand(kw_list_agg)

    # Aggregate socket types
    socket_type_list_agg = _aggregate_attribute(points, "connectorTypes")
    socket_type_list = lst_flatten(socket_type_list_agg)

    return kw_list, socket_type_list


def map_charging(row: pd.Series, station_id: Optional[int]) -> Charging:
    """Maps the given raw datapoint to a Charging object.

    :param row: A datapoint containing information about the charging station.
    :param station_id: The ID of the charging station.
    :return: An instance of the Charging class containing the mapped charging point data.
    """
    points: Final[pd.Series] = row.get("points", [])

    kw_list, socket_type_list = _extract_charger_details(points)

    charging = Charging()
    charging.station_id = station_id
    charging.capacity = len(points) if points else None
    charging.kw_list = kw_list or None
    charging.ampere_list = None  # NOTE: is not available in the data source
    charging.volt_list = None  # NOTE: is not available in the data source
    charging.socket_type_list = socket_type_list or None
    charging.dc_support = None  # NOTE: is not available in the data source
    charging.total_kw = sum(kw_list) if kw_list else None
    charging.max_kw = max(kw_list) if kw_list else None

    return charging
