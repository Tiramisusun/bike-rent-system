''' Module for handling DB insertion '''
from typing import List, Optional, Literal
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column, Relationship, Session
from sqlalchemy import Double, ForeignKey, String, DateTime
from sqlalchemy import create_engine, Engine, select, text

from dotenv import load_dotenv
import os
import logging
import json
from pathlib import Path
import click
from datetime import datetime, timezone

# Init module level logger
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    ...

class Weather(Base):
    __tablename__ = 'weather'

    id:Mapped[int] = mapped_column(primary_key=True)
    main:Mapped[str] = mapped_column(String(15))
    description:Mapped[str] = mapped_column(String(30))
    icon:Mapped[str] = mapped_column(String(10))

    def __repr__(self) -> str:
        return f"Weather(id={self.id}, main={self.main}, description={self.description})"
    
class WeatherReport(Base):
    __tablename__ = 'weather_report'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    update_time:Mapped[datetime] = mapped_column(DateTime)
    temp: Mapped[float]
    feels_like: Mapped[float]
    visibility: Mapped[int]
    wind_speed: Mapped[float]
    humidity: Mapped[int]
    weather_id: Mapped[int] = mapped_column(ForeignKey("weather.id"))

    def __repr__(self):
        return f"WeatherReport(id={self.id}, temp={self.temp}, update_time={self.update_time}, weather={self.weather_id})"

class Forecast(Base):
    __tablename__ = 'forecast'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    datetime: Mapped[int]
    period: Mapped[str] = mapped_column(String(15))
    temp: Mapped[float]
    weather_id: Mapped[int] = mapped_column(ForeignKey("weather.id"))
    weather: Mapped["Weather"] = Relationship()
    report_id: Mapped[int] = mapped_column("report", ForeignKey("weather_report.id"))
    report: Mapped["WeatherReport"] = Relationship()

    def __repr__(self) -> str:
        return f"Forecast(id={self.id}, datetime={self.datetime}, period={self.period}, weather={self.weather}, temp={self.temp})"
    
    
class Station(Base):
    __tablename__ = 'station'

    station_id: Mapped[int] = mapped_column(primary_key=True)
    contract: Mapped[str] = mapped_column(String(30))
    address: Mapped[List["Address"]] = Relationship(
        back_populates="station", cascade="all, delete-orphan"
    )
    name: Mapped[str] = mapped_column(String(60))
    longitude:Mapped[float] = mapped_column(type_=Double)
    latitude:Mapped[float] = mapped_column(type_=Double)

    def __repr__(self):
        return f"Station(id={self.station_id}, name={self.name}, address={self.address})"
    
class StationStatus(Base):
    __tablename__ = 'station_status'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id = mapped_column(ForeignKey("station.station_id"))
    station:Mapped["Station"] = Relationship()
    update_time: Mapped[datetime] = mapped_column(DateTime)
    avail_bikes: Mapped[int]
    avail_bike_stands: Mapped[int]
    status: Mapped[str] = mapped_column(String(15))

    def __repr__(self) -> str:
        return f"StationStatus(id={self.id}, station={self.station}, avail_bikes={self.avail_bikes}, capacity={self.avail_bike_stands})"

class Address(Base):
    __tablename__ = 'address'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id = mapped_column(ForeignKey("station.station_id"))
    station: Mapped["Station"] = Relationship()
    street1: Mapped[str] = mapped_column(String(30))
    street2: Mapped[str] = mapped_column(String(30), nullable=True)
    county: Mapped[str] = mapped_column(String(30), nullable=True)
    city: Mapped[str] = mapped_column(String(30), nullable=True)
    eircode: Mapped[str] = mapped_column(String(15), nullable=True)

    def __repr__(self):
        return f"Address(id={self.id}, station={self.station}, street={self.street1}, county={self.county}, eircode={self.eircode})"


def load_engine() -> Engine:
    ''' 
    Load engine connection to the specified db.
    
    Engine is a lazy connection to an SQL DB, when engine is used to create a session a connection is established.

    :return: SQL Alchemy Engine
    :rtype: Engine

    '''

    # Load required .env vars.
    try:
        assert load_dotenv(), "Could not load .env variables."
        DB_URL = os.getenv('DB_URL')
        assert DB_URL, 'Could not find required DB URL.'

        engine = create_engine(DB_URL)
        return engine
    
    except Exception as e:
        logger.error(f'Issue loading SQL engine: {str(e)}')
        raise e

@click.command(name='init-db', short_help='Initialize db, create all required tables')
def init_db_click():
    engine = load_engine()
    init_db(engine)
    click.echo('DB successfully initialized.')

def init_db(engine:Engine):
    '''
    Initialise db by creating all required tables for specified engine.
    Auto-creates the database if it does not exist.

    :param engine: Description
    :type engine: Engine
    '''
    try:
        # Use pymysql directly to create the database if it doesn't exist
        import pymysql
        url = engine.url
        db_name = url.database
        connection = pymysql.connect(
            host=url.host,
            port=url.port or 3306,
            user=url.username,
            password=url.password,
        )
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        connection.close()

        Base.metadata.create_all(engine)
        logger.info(f'Successfully created {len(Base.metadata.tables)} tables.')
    except Exception as e:
        logger.error(f'Issue initializing db: {str(e)}')
        raise e
    
def _weather_id_not_in_db(weather_id:int, lookup_ids:list):
    return not weather_id in lookup_ids

def _gen_report(**kwargs) -> WeatherReport:
    print(f'DEBUG kwargs: {kwargs}')
  
    report = WeatherReport(temp = kwargs.get('temp'),
                            feels_like = kwargs.get('feels_like'),
                            visibility = kwargs.get('visibility'),
                            wind_speed = kwargs.get('speed'),
                            humidity= kwargs.get('humidity'),
                            update_time = kwargs.get('time'),
                            weather_id = kwargs.get('weather_id')
                            )
    return report

def _gen_forecast(**kwargs) -> Forecast:
    forecast_orm = Forecast(weather_id=kwargs.get('weather_id'),
                            report=kwargs.get('report'),
                            temp=kwargs.get('temp'),
                            period=kwargs.get('period'),
                            datetime=kwargs.get('dt')
                            )
    return forecast_orm

def _parse_weather(json_obj:dict, weather_ids:list, time:Optional[datetime]=None) -> list[Base]:
    ''' Functionality for parsing OpenWeather JSON response to ORM mappings '''
    # Access current weather first --> check if weather type already exists
    #current = json_obj.get('current', {})
    # weather = current.get('weather', {})[0]
    current = json_obj.get('main', {})
    wind = json_obj.get('wind', {})
    weather = json_obj.get('weather', {})[0]
    
    # Create container for all orm mappings
    weather_objs = []

    # Create weather orm
    weather_id = weather.get('id')
    if _weather_id_not_in_db(weather_id, weather_ids): # If this weather id does not exist
        weather_ids.append(weather_id)
        weather_orm = Weather(**weather)
        report_orm = _gen_report(weather_id=weather_orm.id, **current, **wind, visibility=json_obj.get('visibility'), time=time)
        weather_objs.extend([weather_orm, report_orm])
    
    else:
        report_orm = _gen_report(weather_id=weather_id, **current, **wind, visibility=json_obj.get('visibility'), time=time) 
        weather_objs.append(report_orm)

    

    """hourly = current.get('hourly', [])
    /weather there is no hourly, it will not excute.
    """
    hourly = json_obj.get('hourly', [])

    for forecast in hourly:
        hourly_weather = forecast.get('weather')[0]
        hourly_weather_id = hourly_weather.get('id')

        if _weather_id_not_in_db(hourly_weather_id, weather_ids):
            hourly_weather_orm = Weather(**hourly_weather)
            weather_ids.append(hourly_weather_id)
            forecast_orm = _gen_forecast(weather_id=hourly_weather_orm.id,
                                         period='hourly',
                                         report=report_orm,
                                         **forecast)
        
            weather_objs.extend([hourly_weather_orm, forecast_orm])
        
        else:
            forecast_orm = _gen_forecast(weather_id=hourly_weather_id,
                                         period='hourly',
                                         report=report_orm,
                                         **forecast)
            weather_objs.append(forecast_orm)
    
    return weather_objs

def _gen_station_status(**kwargs):
    status = StationStatus(station_id = kwargs.get('number'),
                           update_time = kwargs.get('time'),
                           avail_bikes = kwargs.get('available_bikes'),
                           avail_bike_stands = kwargs.get('available_bike_stands'),
                           status = kwargs.get('status')
                           )
    return status

def _parse_bike_dynamic(json_obj:dict) -> list[StationStatus]:

    # Create container for orm mappings
    bike_objs = []
    
    for station in json_obj:
        tm_tick = station.get('last_update')
        if isinstance(tm_tick, int):
            time = datetime.fromtimestamp((tm_tick / 1000), tz=timezone.utc)
        else:
            time = datetime.now()

        station_status = _gen_station_status(**station, time=time)
        bike_objs.append(station_status)
    
    return bike_objs
        
def _gen_station(**kwargs):
    station = Station(station_id = kwargs.get('number'),
                      contract = kwargs.get('contract_name'),
                      name = kwargs.get('name'),
                      longitude = kwargs.get('position', {}).get('lng'),
                      latitude= kwargs.get('position', {}).get('lat')
                      )
    
    return station

def _parse_bike_static(json_obj:dict) -> list[Station | Address]:
    bike_objs = [] # Create container for orm mappings

    for station in json_obj:
        station = _gen_station(**station)
        bike_objs.append(station)
    
    return bike_objs



def db_from_file(filepath, typ, engine:Optional[Engine] = None, parse_time:bool=False):
    '''
    Functionality to insert from json file.
    '''
    if not engine:
        engine = load_engine()

    fp = Path(filepath)
    assert fp.suffix == '.json', 'Error: expects a JSON file.'
    time = None # Default time to none
    if parse_time: # Attempt to parse time from filename (missing datetime in JSON)
        timestamp = fp.stem.split('_')[1]
        try:
            time = datetime.strptime(timestamp, "%Y%m%dT%H%M%S")
        except Exception as e:
            logger.warning(f'Error parsing time from filename: {fp}')

            raise e

    with open(fp, 'r') as fr:
        json_obj = json.load(fr)

    with Session(engine) as session:
        if typ == 'weather':
            weather_ids = list(session.scalars(select(Weather.id)).all()) # Get all existing weather ids as list of ints
            orm_objs = _parse_weather(json_obj, weather_ids, time)
                        
        elif typ == 'bike-dynamic':
            orm_objs = _parse_bike_dynamic(json_obj)

        elif typ == 'bike-static':
            orm_objs = _parse_bike_static(json_obj)
        
        else:
            raise Exception('Invalid resource type.')

        session.add_all(orm_objs)
        session.commit()



def db_from_directory(directory, typ, engine:Optional[Engine]=None, parse_time:bool=False):
    '''
    Functionality for recursively inserting data into db from directory of json objs.
    '''
    if not engine:
        engine = load_engine()

    orm_objs = [] # Collection for ORM mappings

    with Session(engine) as session:
        if typ == 'weather':
            weather_ids = list(session.scalars(select(Weather.id)).all()) # Get all existing weather ids as list of ints

        for root, subdirs, files in os.walk(directory):
                if subdirs:
                    logger.warning('Warning directories are expected to be flat. Sub-dirs will not be traversed.')
                
                for f in files:
                    fp = Path(root) / f

                    if parse_time: # Attempt to parse time from filename (missing datetime in JSON)
                        timestamp = fp.stem.split('_')[1]
                        try:
                            time = datetime.strptime(timestamp, "%Y%m%dT%H%M%S")
                        except Exception as e:
                            logger.warning(f'Error parsing time from filename: {fp} > {e}')
                            continue

                    if fp.suffix == '.json': # Add json obj to collection
                        with open(fp, 'r') as fr:
                            json_obj = json.load(fr)
                        
                        if typ == 'weather':
                            orm_objs.extend(_parse_weather(json_obj, weather_ids, time)) #type: ignore
                    
                        elif typ == 'bike-dynamic':
                            orm_objs.extend(_parse_bike_dynamic(json_obj))

                        elif typ == 'bike-static':
                            orm_objs.extend(_parse_bike_static(json_obj))

                    else:
                        logger.warning('Non-json files detected. These files are not compatable.')

        session.add_all(orm_objs)
        session.commit()


def db_from_multi_dir(dir_list: list[tuple[str, Literal['weather', 'bike-dynamic', 'bike-static']]], engine:Optional[Engine]=None):
    '''
    Functionality for recursively inserting data from multiple directories.
    
    :param dir_list: List of tuples [str-pathlike, data source type <Literal ['weather', 'bike-dynamic', 'bike-static']>]
    :type dir_list: tuple[str, str]
    '''
    if not engine:
        engine = load_engine()

    for directory in dir_list:
        dir_path, typ = directory
        db_from_directory(dir_path, typ, engine)
            

def db_from_request(json_obj:dict, typ:Literal['weather', 'bike-dynamic', 'bike-static'], engine:Optional[Engine]=None):
    '''
    Functionality for inserting db records from memory

    :param json_obj: dict json obj in memory
    :type json_obj: dict
    :param type: type
    :type type: Literal['weather', 'bike-dynamic', 'bike-static']
    '''

    if not engine:
        engine = load_engine()
    
    with Session(engine) as session:
        if typ == 'weather':
            time = datetime.now() # Get current time for parsing rq
            weather_ids = list(session.scalars(select(Weather.id)).all()) # Get all existing weather ids as list of ints
            orm_objs = _parse_weather(json_obj, weather_ids, time)
        
        elif typ == 'bike-dynamic':
            orm_objs = _parse_bike_dynamic(json_obj)

        elif typ == 'bike-static':
            orm_objs = _parse_bike_static(json_obj)

        session.add_all(orm_objs)
        session.commit()


# READ FUNCTIONS #

def get_latest_weather(engine: Engine) -> dict | None:
    with Session(engine) as session:
        stmt = select(WeatherReport).order_by(WeatherReport.update_time.desc()).limit(1)
        report = session.scalars(stmt).first()
        if not report:
            return None
        return {
            "id": report.id,
            "temp": report.temp,
            "feels_like": report.feels_like,
            "humidity": report.humidity,
            "wind_speed": report.wind_speed,
            "visibility": report.visibility,
            "update_time": report.update_time.isoformat(),
            "weather_id": report.weather_id,
        }


def get_all_stations(engine: Engine) -> list[dict]:
    with Session(engine) as session:
        stmt = select(Station)
        stations = session.scalars(stmt).all()
        return [
            {
                "station_id": s.station_id,
                "name": s.name,
                "contract": s.contract,
                "longitude": s.longitude,
                "latitude": s.latitude,
            }
            for s in stations
        ]


def get_latest_station_status(engine: Engine) -> list[dict]:
    with Session(engine) as session:
        stmt = select(StationStatus).order_by(StationStatus.update_time.desc())
        statuses = session.scalars(stmt).all()
        return [
            {
                "id": s.id,
                "station_id": s.station_id,
                "avail_bikes": s.avail_bikes,
                "avail_bike_stands": s.avail_bike_stands,
                "status": s.status,
                "update_time": s.update_time.isoformat(),
            }
            for s in statuses
        ]


# CLICK CLI COMMANDS #

@click.command(name='multi-dir', short_help='Insert to DB from multiple directories')
@click.option('-d', '--directories',
              multiple=True, 
              type=(click.Path(exists=True), click.Choice(['weather', 'bike-dynamic', 'bike-static'])),
              help="Pair of <directory_path> and <data_type>. Can be used multiple times."
              )
def db_from_multi_dir_click(directories):
    db_from_multi_dir(directories)
    click.echo(f'Successfully processed directories: {directories}')


@click.command(name='dir', short_help='Insert data from a directory of JSON files')
@click.argument('directory', type=click.Path(exists=True))
@click.option('-p', '--parse-time', is_flag=True, default=False, help='Enable time parsing from file format, standard is "_" seperated ISO')
@click.argument('typ', type=click.Choice(['weather', 'bike-dynamic', 'bike-static']))
def db_from_directory_click(directory, typ, parse_time):
    """Inserts all JSON records from DIRECTORY into the database."""
    db_from_directory(directory, typ, parse_time=parse_time)
    click.echo(f"Successfully processed directory: {directory}")


@click.command(name='file', short_help='Insert data from a single JSON file')
@click.argument('filepath', type=click.Path(exists=True))
@click.option('-p', '--parse-time', is_flag=True, default=False, help='Enable time parsing from file format, standard is "_" seperated ISO')
@click.argument('typ', type=click.Choice(['weather', 'bike-dynamic', 'bike-static']))
def db_from_file_click(filepath, typ, parse_time):
    ''' Insert data from a single JSON file '''
    db_from_file(filepath, typ, parse_time=parse_time)
    click.echo(f"Successfully processed file: {filepath}")

@click.group(name='Software Engineering DB tools',
             short_help='Enables db initialization and insertion from a number of bulk formats',
             help='Enables db initialization and insertion from a number of bulk formats, functionality can also be run w/ crontab')
def cli():
    ...
cli.add_command(db_from_directory_click)
cli.add_command(db_from_file_click)
cli.add_command(db_from_multi_dir_click)
cli.add_command(init_db_click)

if __name__ == '__main__':
    cli()