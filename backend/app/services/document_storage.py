"""Local storage for original PDFs (S1: guardar el PDF original)."""

import uuid
from pathlib import Path


def save_pdf(storage_dir: Path | str, licitacion_id: int, content: bytes) -> str:
    """Write the original PDF under `storage_dir` and return its relative path.

    Layout: `licitaciones/<licitacion_id>/<uuid>.pdf`. The relative path is
    what gets persisted in `documento.ruta`.
    """
    storage = Path(storage_dir)
    target_dir = storage / "licitaciones" / str(licitacion_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.pdf"
    target = target_dir / filename
    target.write_bytes(content)
    return str(target.relative_to(storage))
