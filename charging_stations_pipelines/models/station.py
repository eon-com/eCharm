from geoalchemy2.types import Geography
from sqlalchemy import Column, Date, Integer, String, Boolean, Index, ForeignKey
from sqlalchemy.orm import relationship

from charging_stations_pipelines.models import Base


class Station(Base):
    __tablename__ = "stations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String, index=True, nullable=True, unique=True)
    data_source = Column(String)
    operator = Column(String)
    payment = Column(String)
    authentication = Column(String)
    point = Column(Geography(geometry_type='POINT', srid=4326))
    date_created = Column(Date)
    date_updated = Column(Date)
    raw_data = Column(String)
    country_code = Column(String)
    address = relationship("Address", back_populates="station", uselist=False)
    charging = relationship("Charging", back_populates="station", uselist=False)
    is_merged = Column(Boolean, default=False)
    merge_status = Column(String)
    source_stations = relationship("MergedStationSource")


    def __repr__(self):
        return "<stations with id: {}>".format(self.id)


Index(
    "stations_point_geom_idx",
    Station.__table__.c.point,
    postgresql_using='gist',
)


class MergedStationSource(Base):
    __tablename__ = 'merged_station_source'
    id = Column(Integer, primary_key=True, autoincrement=True)
    merged_station_id = Column(Integer, ForeignKey('stations.id'))
    duplicate_source_id = Column(String)