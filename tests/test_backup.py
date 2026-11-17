import gzip
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.admin_tools import BACKUP_KEEP, backup_folder, backup_if_due


class DailyBackupTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Path(self.tempdir.name) / "banco.sqlite"
        connection = sqlite3.connect(self.database)
        connection.execute("CREATE TABLE t (value INTEGER)")
        connection.execute("INSERT INTO t VALUES (42)")
        connection.commit()
        connection.close()
        self.day = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_runs_once_a_day_and_keeps_the_data(self):
        created = backup_if_due(self.database, now=self.day)
        restored = Path(self.tempdir.name) / "restaurado.sqlite"
        restored.write_bytes(gzip.decompress(created.read_bytes()))
        copy = sqlite3.connect(restored)
        self.assertEqual(copy.execute("SELECT value FROM t").fetchone()[0], 42)
        copy.close()
        self.assertIsNone(backup_if_due(self.database, now=self.day + timedelta(hours=3)))
        self.assertIsNotNone(backup_if_due(self.database, now=self.day + timedelta(days=1)))

    def test_old_copies_leave(self):
        for offset in range(BACKUP_KEEP + 3):
            backup_if_due(self.database, now=self.day + timedelta(days=offset))
        self.assertEqual(len(list(backup_folder(self.database).iterdir())), BACKUP_KEEP)


if __name__ == "__main__":
    unittest.main()
