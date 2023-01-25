import os
import pathlib
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mapping.charging import map_charging_ocm
from mapping.stations import map_address_ocm, map_station_ocm
from models.station import Station
from pipelines._merger import StationMerger
from pipelines._ocm import OcmPipeline
from pipelines._osm import OsmPipeline
from pipelines._bna import BnaPipeline
from pipelines._france import FraPipeline
from pipelines._gbgov import GbPipeline
from settings import db_uri
from testing import testdata
from geojson_output import convert_to_geojson

if __name__ == "__main__":
    country_code = "GB"
    current_dir = os.path.join(pathlib.Path(__file__).parent.resolve())
    import configparser

    config: configparser = configparser.RawConfigParser()
    config.read(os.path.join(os.path.join(current_dir, "config", "config.ini")))

    if country_code == "DE":
        bna: BnaPipeline = BnaPipeline(
            config=config,
            session=sessionmaker(bind=(create_engine(db_uri, echo=True)))(),
            offline=True,
        )
        #bna.run()

    elif country_code == "FR":
        fra: FraPipeline = FraPipeline(
            config=config,
            session=sessionmaker(bind=(create_engine(db_uri, echo=True)))(),
            offline=True,
        )
        #fra.run()

    elif country_code == "GB":
        gb: GbPipeline = GbPipeline(
            country_code=country_code,
            config=config,
            session=sessionmaker(bind=(create_engine(db_uri, echo=True)))(),
            offline=False,
        )
        gb.run()    
  
    osm: OsmPipeline = OsmPipeline(
        country_code=country_code,
        config=config,
        session=sessionmaker(bind=(create_engine(db_uri, echo=True)))(),
        offline=True,
    )
    #osm.run()

    ocm: OcmPipeline = OcmPipeline(
        country_code=country_code,
        config=config,
        session=sessionmaker(bind=(create_engine(db_uri, echo=True)))(),
        offline=True,
    )
    #ocm.run()


    from pipelines._merger import StationMerger
    is_test = True
    logging.disable(logging.INFO) #only way to disable SQL Alchemy printing SQL statements, tried a lot
    merger: StationMerger = StationMerger(config=config, con=create_engine(db_uri, echo=False), is_test=is_test)
    #merger.run()


    #testdata.run()

    #convert_to_geojson(create_engine(db_uri, echo=False), country_code)
    print("")
