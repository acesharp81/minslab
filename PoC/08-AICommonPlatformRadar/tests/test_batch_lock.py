from pathlib import Path

import pytest

from app.services.batch_lock import BatchAlreadyRunning, exclusive_collection_lock


def test_collection_lock_rejects_nested_run(tmp_path: Path):
    with exclusive_collection_lock(tmp_path):
        with pytest.raises(BatchAlreadyRunning):
            with exclusive_collection_lock(tmp_path):
                pass


def test_collection_lock_is_released(tmp_path: Path):
    with exclusive_collection_lock(tmp_path):
        pass
    with exclusive_collection_lock(tmp_path):
        pass
