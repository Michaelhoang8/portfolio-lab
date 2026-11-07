from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from portfolio import backup, services
from portfolio.db import connect, initialize


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'workspace.db'
        self.output = self.root / 'snapshot.db'
        initialize(self.source)
        self.db = connect(self.source)
        self.addCleanup(self.db.close)

    def test_live_wal_backup_and_restore_preserve_full_state(self):
        product = services.product_create(self.db, {'name':'Test','sku':'BACKUP','reorder_point':3})['id']
        for index in range(125):
            services.movement_create(self.db, {'product_id':product,'delta':1,'note':'Fixture',
                                              'request_key':f'backup-{index}'})
        ticket=services.ticket_create(self.db, {'title':'Recover me','description':'Fixture','priority':'high'})['id']
        services.ticket_archive(self.db,ticket,{'archived':True,'expected_version':1})
        services.experiment_create(self.db, {'name':'Fixture','a_visitors':100,'a_conversions':10,
                                           'b_visitors':100,'b_conversions':15})
        with self.db:
            self.db.execute("INSERT INTO api_notes(id,title,content,status) VALUES ('fixture','Note','Preserved','draft')")
            self.db.execute("INSERT INTO api_idempotency VALUES ('notes','key','fingerprint','{}')")
        self.assertTrue(Path(str(self.source)+'-wal').exists())
        expected = '\n'.join(self.db.iterdump())
        report = backup.create_backup(self.source, self.output)
        self.assertEqual(report['rows']['movements'],125)
        self.assertEqual(report['rows']['movement_requests'],125)
        self.assertEqual(report['rows']['api_idempotency'],1)
        self.assertEqual(report['integrity'],'ok')
        services.movement_create(self.db, {'product_id':product,'delta':10,'note':'After snapshot'})
        restored = self.root / 'restored.db'
        backup.create_backup(self.output, restored)
        with closing(connect(restored)) as db:
            self.assertEqual('\n'.join(db.iterdump()),expected)
            replay = services.movement_create(db, {'product_id':product,'delta':1,'note':'Fixture','request_key':'backup-124'})
            self.assertTrue(replay['replayed'])
            self.assertEqual(services.snapshot(db)['products'][0]['stock'],125)
            self.assertEqual(services.snapshot(db)['tickets'][0]['archived'],1)
        self.assertFalse(Path(str(self.output)+'-wal').exists())
        self.assertEqual(backup.verify(self.output)['rows']['movements'],125)

    def test_concurrent_commit_during_incremental_copy_stays_consistent(self):
        with self.db:
            self.db.execute('CREATE TABLE padding (content BLOB)')
            self.db.execute('INSERT INTO padding VALUES (zeroblob(3000000))')
        writer=self.db
        wrote=[]
        class ConcurrentSource(sqlite3.Connection):
            def backup(self,target,**options):
                original_progress=options['progress']
                def progress(status,remaining,total):
                    original_progress(status,remaining,total)
                    if remaining and not wrote:
                        with writer:
                            product=writer.execute("INSERT INTO products(sku,name,reorder_point) VALUES ('LIVE','Live write',1)").lastrowid
                            writer.execute("INSERT INTO movements(product_id,delta,note) VALUES (?,7,'Atomic receipt')",(product,))
                        wrote.append(True)
                return super().backup(target,**{**options,'progress':progress})
        def source_connection(path):
            return sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,factory=ConcurrentSource)
        with patch.object(backup,'read_only',side_effect=source_connection):
            report=backup.create_backup(self.source,self.output)
        self.assertTrue(wrote)
        self.assertEqual(report['rows']['products'],report['rows']['movements'])
        with closing(connect(self.output)) as db:
            self.assertEqual(db.execute('SELECT length(content) FROM padding').fetchone()[0],3000000)
            if report['rows']['products']:
                self.assertEqual(services.snapshot(db)['products'][0]['stock'],7)

    def test_missing_source_does_not_create_files(self):
        missing = self.root / 'missing.db'
        with self.assertRaises(sqlite3.OperationalError):
            backup.create_backup(missing,self.output)
        self.assertFalse(missing.exists())
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.portfolio-backup-*')),[])

    def test_existing_destination_and_source_are_never_overwritten(self):
        self.output.write_bytes(b'Keep this file')
        with self.assertRaises(FileExistsError):
            backup.create_backup(self.source,self.output)
        self.assertEqual(self.output.read_bytes(),b'Keep this file')
        with self.assertRaises(ValueError):
            backup.create_backup(self.source,self.source)
        self.assertEqual(backup.verify(self.source)['integrity'],'ok')

    def test_destination_race_preserves_the_winning_file(self):
        link = os.link
        def race(source,destination):
            Path(destination).write_bytes(b'Another process created this')
            return link(source,destination)
        with patch.object(backup.os,'link',side_effect=race),self.assertRaises(FileExistsError):
            backup.create_backup(self.source,self.output)
        self.assertEqual(self.output.read_bytes(),b'Another process created this')
        self.assertEqual(list(self.root.glob('.portfolio-backup-*')),[])

    def test_corrupt_or_unrelated_database_is_not_published(self):
        for content in (b'not sqlite',b''):
            invalid=self.root/'invalid.db';invalid.write_bytes(content)
            with self.assertRaises((ValueError,sqlite3.DatabaseError)):
                backup.create_backup(invalid,self.output)
            self.assertFalse(self.output.exists())
            self.assertEqual(list(self.root.glob('.portfolio-backup-*')),[])

    def test_broken_references_are_rejected(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        with self.db:
            self.db.execute("INSERT INTO events(ticket_id,detail) VALUES (999,'Broken')")
        with self.assertRaisesRegex(ValueError,'foreign-key'):
            backup.create_backup(self.source,self.output)
        self.assertFalse(self.output.exists())

    def test_timeout_removes_staging_without_publishing(self):
        with patch.object(backup.time,'monotonic',side_effect=[0,31]),self.assertRaises(TimeoutError):
            backup.create_backup(self.source,self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.portfolio-backup-*')),[])


if __name__ == '__main__':
    unittest.main()
