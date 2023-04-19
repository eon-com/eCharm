import configparser
import logging

import geopandas as gpd
import pandas as pd
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

from charging_stations_pipelines.deduplication import attribute_match_thresholds_strategy
from charging_stations_pipelines.models.station import Station


logger = logging.getLogger(__name__)

class StationMerger:
    def __init__(self, country_code: str, config: configparser, con, is_test: bool = False):
        self.country_code = country_code
        self.config = config
        self.con = con
        self.is_test = is_test

        if self.is_test:
            self.country_code = "DE"

        country_code_to_gov_source = {
            "DE": "BNA",
            "FR": "FRGOV",
            "GB": "GBGOV",
            "IT": ""  # No gov source for Italy so far (5.4.2023)
        }
        if country_code not in country_code_to_gov_source:
            raise Exception(f"country code '{country_code}' unknown in merger")
        self.gov_source = country_code_to_gov_source[country_code]

    def merge_attributes(self, station: pd.Series, duplicates_to_merge: pd.DataFrame):
        """
        Might be used in the future.

        :param station:
        :param duplicates_to_merge:
        :return:
        """
        for att_name in [
            "amperage",
            "operator",
            "payment",
            "socket_type",
            "authentication",
            "capacity",
            "voltage",
        ]:
            att_values = duplicates_to_merge[att_name].dropna().unique().tolist()
            att_values = [str(x) for x in att_values if len(str(x)) > 0]
            if att_name in station.dropna():
                att_value = str(station[att_name])
                att_values += (
                    [att_value] if ";" not in att_value else att_value.split(";")
                )
            att_values = set(att_values)
            new_value = (
                ";".join([str(x) for x in att_values]) if att_values else None
            )
            station.at[att_name] = new_value
        station.at["merged_attributes"] = True
        return

    def _merge_duplicates(self, stations_to_merge) -> Station:
        """
        Input DataFrame has columns
                station_id, source_id, data_source, point, operator, capacity, street, town, distance

        :param stations_to_merge: pd.DataFrame containing all stations which should be merged.
        :return:
        """

        def get_attribute_by_priority(column_name, priority_list=None):
            attribute = None
            if priority_list is None:
                priority_list = [self.gov_source, 'OCM', 'OSM']
            for source in priority_list:
                # get stations of source with attribute not empty, and return only attribute column
                stations_by_source = stations_to_merge[stations_to_merge['data_source'] == source][column_name].dropna()
                if len(stations_by_source) > 0:
                    attribute = stations_by_source.iloc[0]
                    break
            if not attribute:
                logger.debug(f"attribute {column_name} not found ?!?!? {stations_to_merge}")
            return attribute

        merged_station = Station()
        merged_station.country_code = self.country_code
        merged_station.is_merged = True

        if isinstance(stations_to_merge, pd.Series):
            merged_station.data_source = stations_to_merge['data_source']
            merged_station.point = stations_to_merge['point'].wkt
            merged_station.operator = stations_to_merge['operator']
            merged_station.source_id = f"MERGED_{stations_to_merge['source_id']}"
        else:
            merged_station.data_source = ",".join(stations_to_merge['data_source'].unique())
            merged_station.source_id = f"MERGED_{','.join(stations_to_merge['source_id'].tolist())}"
            # TODO: implement SQL table mapping from merged station to source stations
            # merged_station.relations = source ids

            # get other attributes by priority:
            # coordinates in dataframe are WKB ? maybe convert to WKT?
            point = get_attribute_by_priority('point', priority_list=['OSM', 'OCM', self.gov_source])
            merged_station.point = point.wkt
            merged_station.operator = get_attribute_by_priority('operator')

        return merged_station

    def run(self):
        '''
            Note: We should use geography types as it's much more accurate than projection from WSG-84 to Mercator
            E.g.
            select ST_Distance(ST_Transform('SRID=4326;POINT (11.5739817 48.1589335)'::geometry, 3857), 
                    ST_Transform('SRID=4326;POINT (11.5375666 48.1532363)'::geometry, 3857));
            --> 4163 meters 
            select ST_Distance('SRID=4326;POINT (11.5739817 48.1589335)'::geography, 
                            'SRID=4326;POINT (11.5375666 48.1532363)'::geography);
            --> 2782 meters (correct)
        '''

        # First get list of stations esp. their coordinates
        get_stations_list_sql = """
            SELECT id as station_id, point FROM stations WHERE NOT is_merged AND country_code='{country_code}'
        """.format(country_code=self.country_code)

        if self.is_test:
            munich_center_coordinates = "POINT (11.4717 48.1548)"
            get_stations_list_sql = """
                SELECT id as station_id, point FROM stations 
                WHERE ST_Dwithin(point, 
                              ST_PointFromText('{center_coordinates}', 4326)::geography, 
                              {radius_m}) AND NOT is_merged; 
            """.format(center_coordinates=munich_center_coordinates, radius_m=5000)

        gdf: gpd.GeoDataFrame = gpd.read_postgis(get_stations_list_sql,
                                                 con=self.con, geom_col="point")

        gdf.sort_values(by=['station_id'], inplace=True, ignore_index=True)

        session = sessionmaker(bind=(self.con))()

        def write_session(session):
            try:
                session.commit()
                session.flush()
            except Exception as e:
                logger.error(f"Writing merged stations failed! Error: {e}")
                session.rollback()

        # For each station's coordinate find all surrounding stations within a certain radius (including itself)
        radius_m = 100
        for idx in tqdm(range(gdf.shape[0])):
            current_station: gpd.GeoSeries = gdf.iloc[idx]

            # find real duplicates to current station
            duplicates, current_station_full = self.find_duplicates(current_station['station_id'],
                                                                    current_station['point'], radius_m)
            if not duplicates.empty:
                stations_to_merge = duplicates.append(current_station_full)
                station_ids = stations_to_merge['station_id_col'].tolist()
            else:
                logger.debug(f"Only current station, no duplicates")
                stations_to_merge = current_station_full  # .to_frame()
                station_ids = [current_station['station_id'].item()]

            if not stations_to_merge.empty:
                # merge attributes of duplicates into one station
                logger.debug(station_ids)
                session.query(Station).filter(Station.id.in_(station_ids)) \
                    .update({Station.merge_status: "is_duplicate"}, synchronize_session='fetch')
                merged_station: Station = self._merge_duplicates(stations_to_merge)
                session.add(merged_station)
                write_session(session)

        # write_session(session)

    def find_duplicates(self, current_station_id, current_station_coordinates, radius_m,
                        filter_by_source_id: bool = False) -> (gpd.GeoDataFrame, gpd.GeoSeries):

        find_surrounding_stations_sql = """ 
            SELECT 
                s.id as station_id,
                s.source_id as source_id,
                s.data_source, s.point, s.operator,
                c.capacity,
                a.street, a.town,
                ST_DISTANCE(s.point, 
                              ST_PointFromText('{center_coordinates}', 4326)::geography) as distance
            FROM stations s
            LEFT JOIN charging c ON s.id = c.station_id
            LEFT JOIN address a ON s.id = a.station_id 
            WHERE ST_Dwithin(s.point, 
                              ST_PointFromText('{center_coordinates}', 4326)::geography, 
                              {radius_m}) 
                              AND NOT is_merged
                              AND (merge_status <> 'is_duplicate' OR merge_status is null) 
                              AND country_code='{country_code}';
        """

        sql = find_surrounding_stations_sql.format(station_id=current_station_id,
                                                   center_coordinates=current_station_coordinates,
                                                   radius_m=radius_m,
                                                   country_code=self.country_code)
        nearby_stations: gpd.GeoDataFrame = gpd.read_postgis(sql, con=self.con, geom_col="point")

        if nearby_stations.empty:
            logger.debug(f"##### Already merged, id {current_station_id} #####")
            return gpd.GeoDataFrame(), gpd.GeoSeries()

        logger.debug(f"coordinates of current station: {current_station_coordinates}, ID: {current_station_id}")
        logger.debug(f"# nearby stations incl current: {len(nearby_stations)}")
        # copy station id to new column otherwise it's not addressable as column after setting index
        station_id_col = 'station_id_col'
        nearby_stations[station_id_col] = nearby_stations['station_id']

        nearby_stations.set_index('station_id', inplace=True)

        if filter_by_source_id:
            station_id_name = 'source_id'
        else:
            station_id_name = station_id_col

        # get the current station with all it's attributes
        current_station_full: pd.Series = \
            nearby_stations[nearby_stations[station_id_name] == current_station_id].squeeze()

        logger.debug(current_station_full)

        pd.set_option('display.max_columns', None)
        # skip if only center station itself was found
        if len(nearby_stations) >= 2:

            if not current_station_full.empty:
                duplicate_candidates = nearby_stations[nearby_stations[station_id_name] != current_station_id]
                duplicate_candidates["is_duplicate"] = False
                current_station_full["is_duplicate"] = True
                duplicate_candidates["address"] = duplicate_candidates[["street", "town"]]. \
                    apply(lambda x: f"{x['street']},{x['town']}", axis=1)
                current_station_full['address'] = f"{current_station_full['street']},{current_station_full['town']}"
                duplicate_candidates = attribute_match_thresholds_strategy.attribute_match_thresholds_duplicates(
                    current_station=current_station_full,
                    duplicate_candidates=duplicate_candidates,
                    station_id_name=station_id_name,
                    max_distance=radius_m
                )
                duplicates = duplicate_candidates[duplicate_candidates["is_duplicate"]]
                return duplicates, current_station_full

        return gpd.GeoDataFrame(), current_station_full
