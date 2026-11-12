"""Write user data without exposing a partially written file to readers."""

import json
import os
from pathlib import Path
import tempfile


def write_json(path: Path, data: object) -> None:
    # Serialize before touching the destination, including when serialization itself fails.
    content = json.dumps(data, ensure_ascii=False, indent=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
