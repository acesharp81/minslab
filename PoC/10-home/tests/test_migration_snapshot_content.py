"""A fresh metadata bootstrap must survive the later snapshot migration."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_existing_snapshot_payloads_survive_migration_reentry():
    path = Path(__file__).resolve().parents[1] / 'db/migrations/versions/0018_snapshot_content.py'
    spec = importlib.util.spec_from_file_location('snapshot_content_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            connection.execute(sa.text('INSERT INTO home_metric_snapshot_content (id,payload) VALUES (:id,:payload)'),
                               {'id': 'immutable-snapshot', 'payload': '{"evidence":"original"}'})
            migration.upgrade()
            assert connection.scalar(sa.text('SELECT payload FROM home_metric_snapshot_content WHERE id=:id'),
                                     {'id': 'immutable-snapshot'}) == '{"evidence":"original"}'
            assert {c['name'] for c in sa.inspect(connection).get_columns('home_metric_snapshot_content')} == {'id', 'payload'}
    finally:
        engine.dispose()
