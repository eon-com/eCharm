"""
This module handles the mapping of charging data obtained from e-control.at (also known as ladestellen.at).
The data is structured into three main objects:
- 'Station': Represents the charging station.
- 'Address': Contains address information for the charging station.
- 'Charging': Provides the charging details for a particular charging station.
"""

import configparser
import logging
import os
import pathlib

import pandas as pd
from sqlalchemy.orm import Session
from tqdm import tqdm

from charging_stations_pipelines.pipelines.at import DATA_SOURCE_KEY
from charging_stations_pipelines.pipelines.at.econtrol_crawler import get_data
from charging_stations_pipelines.pipelines.at.econtrol_mapper import map_address, map_charging, map_station
from charging_stations_pipelines.pipelines.station_table_updater import StationTableUpdater

logger = logging.getLogger(__name__)


class EcontrolAtPipeline:
    """
    :class:`EcontrolAtPipeline` is a class that represents a pipeline for processing data
    from the e-control.at (aka ladestellen.at) - an official data source from the Austrian government.

    :param config: A `configparser` object containing configurations for the pipeline.
    :param session: A `Session` object representing the session used for database operations.
    :param online: A boolean indicating whether the pipeline should retrieve data online. Default is False.

    :ivar config: A `configparser` object containing configurations for the pipeline.
    :ivar session: A `Session` object representing the session used for database operations.
    :ivar online: A boolean indicating whether the pipeline should retrieve data online.
    :ivar data_dir: A string representing the directory where data files will be stored.
    """

    def __init__(self, config: configparser, session: Session, online: bool = False):
        self.config = config
        self.session = session
        self.online: bool = online
        relative_dir = os.path.join("../../..", "data")
        self.data_dir: str = os.path.join(pathlib.Path(__file__).parent.resolve(), relative_dir)

    def _retrieve_data(self):
        pathlib.Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        tmp_data_path = os.path.join(self.data_dir, self.config[DATA_SOURCE_KEY]["filename"])
        if self.online:
            logger.info("Retrieving Online Data")
            get_data(tmp_data_path)
        # NOTE, read data from json file in NDJSON (newline delimited JSON) format,
        #   i.e. one json object per line, thus `lines=True` is required
        self.data = pd.read_json(tmp_data_path, lines=True)  # pd.DataFrame

    def run(self):
        """ Runs the pipeline for a data source.
        Retrieves data, processes it, and updates the Station table (as well as Address and Charging tables).

        :return: None
        """
        logger.info(f"Running {DATA_SOURCE_KEY} Pipeline...")
        self._retrieve_data()
        station_updater = StationTableUpdater(session=self.session, logger=logger)
        count_imported_stations, count_empty_stations, count_invalid_stations = 0, 0, 0
        for _, datapoint in tqdm(iterable=self.data.iterrows(), total=self.data.shape[0]):  # type: _, pd.Series
            try:
                station = map_station(datapoint)
                if not station or not station.source_id or not station.point:
                    count_empty_stations += 1
                    continue

                station.address = map_address(datapoint, None)
                station.charging = map_charging(datapoint, None)

                count_imported_stations += 1
            except Exception as e:
                count_invalid_stations += 1
                logger.debug(
                    f"{DATA_SOURCE_KEY} entry could not be mapped! Error:\n{e}\nRow:\n----\n{datapoint}\n----\n")
                continue
            station_updater.update_station(station, DATA_SOURCE_KEY)
        logger.info(f"Finished {DATA_SOURCE_KEY} Pipeline, "
                    f"new stations imported: {count_imported_stations}, empty stations: {count_empty_stations}, "
                    f"stations which could not be parsed: {count_invalid_stations}.")
        station_updater.log_update_station_counts()
