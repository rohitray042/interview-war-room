"""Opt-in verification copies. Never mutate or send the source database externally."""

import hashlib
import sqlite3
from pathlib import Path


def fingerprint(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as source:
        digest = hashlib.sha256()
        for statement in source.iterdump():
            digest.update(statement.encode())
        return digest.hexdigest()


def copy_database(source_path, destination):
    source_path = Path(source_path).resolve(strict=True)
    destination = Path(destination).resolve()
    if source_path == destination or destination.exists():
        raise ValueError("Verification requires a new, separate destination database")
    with sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
