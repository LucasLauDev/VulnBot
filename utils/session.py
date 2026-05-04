from contextlib import contextmanager
from functools import wraps

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base

from config.config import Configs


db_url = f"mysql+pymysql://{Configs.db_config.mysql['user']}:{Configs.db_config.mysql['password']}@{Configs.db_config.mysql['host']}:{Configs.db_config.mysql['port']}/{Configs.db_config.mysql['database']}"

engine = create_engine(db_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base: DeclarativeMeta = declarative_base()

@contextmanager
def session_scope() -> Session:
    """上下文管理器用于自动获取 Session, 避免错误"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def with_session(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with session_scope() as session:
            try:
                result = f(session, *args, **kwargs)
                session.commit()
                return result
            except:
                session.rollback()
                raise

    return wrapper


def create_tables():
    # Import models so they register on Base.metadata before create_all().
    import db.models.conversation_model  # noqa: F401
    import db.models.message_model  # noqa: F401
    import db.models.plan_model  # noqa: F401
    import db.models.session_model  # noqa: F401
    import db.models.task_model  # noqa: F401
    try:
        import rag.kb.models.kb_document_model  # noqa: F401
        import rag.kb.models.knowledge_file_model  # noqa: F401
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)
