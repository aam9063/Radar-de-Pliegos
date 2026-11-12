"""Company profile persistence (S5, RP-06): exactly one editable row.

The single-row invariant lives here (not in SQLAlchemy constraints) the same
way ``Ficha`` keeps one dossier per licitación: PUT updates the existing row
when present, otherwise inserts the first one.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PerfilEmpresa as PerfilEmpresaDB
from app.domain.perfil_empresa import PerfilEmpresa


async def obtener_perfil(session: AsyncSession) -> PerfilEmpresa | None:
    """The stored company profile, or None while it has never been configured."""
    row = await session.scalar(select(PerfilEmpresaDB).order_by(PerfilEmpresaDB.id).limit(1))
    if row is None:
        return None
    return PerfilEmpresa.model_validate(row.datos)


async def guardar_perfil(session: AsyncSession, perfil: PerfilEmpresa) -> PerfilEmpresa:
    """Create or replace the single company profile row (PUT semantics)."""
    row = await session.scalar(select(PerfilEmpresaDB).order_by(PerfilEmpresaDB.id).limit(1))
    datos = perfil.model_dump(mode="json")
    if row is None:
        session.add(PerfilEmpresaDB(datos=datos))
    else:
        row.datos = datos
    await session.commit()
    return perfil
