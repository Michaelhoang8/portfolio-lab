"""Create and verify complete SQLite snapshots without overwriting existing files."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

TABLES = ('tickets', 'events', 'products', 'movements', 'movement_requests',
          'experiments', 'api_notes', 'api_idempotency')


def read_only(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=1)


def inspect_database(db):
    """Check one consistent read transaction, including relational integrity."""
    db.execute('BEGIN')
    try:
        checks = [row[0] for row in db.execute('PRAGMA integrity_check')]
        if checks != ['ok']:
            raise ValueError('SQLite integrity check failed')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(TABLES).issubset(tables):
            raise ValueError('This is not a current Portfolio Lab database; required tables are missing')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Database contains broken foreign-key references')
        return {'integrity': 'ok', 'rows': {name: db.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
                                          for name in TABLES}}
    finally:
        db.rollback()


def verify(path):
    with closing(read_only(path)) as db:
        return inspect_database(db)


def create_backup(source, destination, timeout=30):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if destination.resolve() == source:
        raise ValueError('Backup destination must differ from the source database')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Backup destination already exists; choose a new filename')
    started = time.monotonic()

    def progress(_status, _remaining, _total):
        if time.monotonic() - started > timeout:
            raise TimeoutError('Backup exceeded its time limit; no output was published')

    # Open read-only before allocating an artifact: a typo must not create an empty source.
    with closing(read_only(source)) as original:
        with tempfile.NamedTemporaryFile(prefix='.portfolio-backup-', suffix='.db',
                                         dir=destination.parent, delete=False) as staging:
            temporary = Path(staging.name)
        try:
            with closing(sqlite3.connect(temporary)) as target:
                original.backup(target, pages=256, progress=progress, sleep=.05)
                target.execute('PRAGMA journal_mode=DELETE')
                report = inspect_database(target)
            with temporary.open('r+b') as artifact:
                os.fsync(artifact.fileno())
            # A same-directory hard link publishes the completed file exclusively, even
            # if another process creates the requested destination during the backup.
            os.link(temporary, destination)
            return {'path': str(destination), 'bytes': destination.stat().st_size, **report}
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='Create a new, verified snapshot')
    create.add_argument('--database', default='data/portfolio.db')
    create.add_argument('--output', required=True)
    check = commands.add_parser('verify', help='Check SQLite integrity, references, and required tables')
    check.add_argument('database')
    args = parser.parse_args()
    try:
        report = create_backup(args.database, args.output) if args.command == 'create' else verify(args.database)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f'Backup failed: {error}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
