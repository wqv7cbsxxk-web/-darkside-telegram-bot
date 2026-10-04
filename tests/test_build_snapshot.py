import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build_mini_app_data as builder

class BuildSnapshotTests(unittest.TestCase):
    def test_unchanged_feed_does_not_advance_snapshot_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            index=Path(directory)/'index.html';index.write_text(builder.INDEX.read_text())
            with patch.object(builder,'INDEX',index):
                builder.build();before=index.read_text()
                with patch.object(builder.time,'time',return_value=9999999999):builder.build()
                self.assertEqual(index.read_text(),before)
