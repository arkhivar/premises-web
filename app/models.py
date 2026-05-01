import os
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, scoped_session

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://premises:premises_dev_password@localhost:5432/premises_db",
)

# Strip Prisma-style ?schema=public from URL for psycopg2
_db_url = DATABASE_URL
if "?" in _db_url:
    _db_url = _db_url.split("?")[0]

engine = create_engine(_db_url)

metadata = MetaData()
metadata.reflect(bind=engine)

SessionLocal = scoped_session(sessionmaker(bind=engine))

users = metadata.tables["User"]
properties = metadata.tables["Property"]
tenants = metadata.tables["Tenant"]
contracts = metadata.tables["Contract"]
contract_templates = metadata.tables["ContractTemplate"]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
