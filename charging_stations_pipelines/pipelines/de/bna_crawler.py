"""Module to download the BNA (Bundesnetzagentur) data from a specified URL."""

import logging
import os
from urllib.parse import urlparse, urljoin

import requests as requests
from bs4 import BeautifulSoup

from charging_stations_pipelines.shared import download_file

logger = logging.getLogger(__name__)


def get_bna_data(tmp_data_path):
    """Downloads BNA (Bundesnetzagentur) data (Excel sheet 'ladesaeulenregister.xlsx') from its website into a temporary
    file.

    :param tmp_data_path: The path to save the downloaded data file.
    :type tmp_data_path: str
    :return: None
    """
    download_link_url = "https://data.bundesnetzagentur.de/Bundesnetzagentur/SharedDocs/Downloads/DE/Sachgebiete/Energie/Unternehmen_Institutionen/E_Mobilitaet/Ladesaeulenregister.xlsx"

    logger.info(f"Downloading BNA data from {download_link_url}...")
    download_file(download_link_url, tmp_data_path)
    logger.info(f"Downloaded BNA data to {tmp_data_path}")
    logger.info(f"Downloaded file size: {os.path.getsize(tmp_data_path)} bytes")
