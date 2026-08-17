"""Initialize the database schema and load taxonomy tables.

Run:  python -m backend.db.init
"""
from backend.db.database import Base, engine, session_scope
from backend.db import models
from backend.taxonomy.registry import get_registry


def init_db(drop: bool = False):
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reg = get_registry()
    with session_scope() as db:
        db.query(models.CodeMapping).delete()
        db.query(models.NetworkReasonCodeRow).delete()
        db.query(models.InternalDisputeTypeRow).delete()
        for t in reg.types.values():
            db.add(models.InternalDisputeTypeRow(
                code=t.code, name=t.name, label=t.label, macro=t.macro,
                macro_name=t.macro_name, description=t.description,
                in_techdoc=t.in_techdoc, in_excel=t.in_excel))
            for network, codes in t.network_codes.items():
                for nc in codes:
                    db.add(models.CodeMapping(
                        internal_code=t.code, network=network, network_code=nc))
        for rc in reg.network_codes.values():
            db.add(models.NetworkReasonCodeRow(
                network=rc.network, code=rc.code, description=rc.description,
                category=rc.category, resolution_approach=rc.resolution_approach))
    print(f"Schema created. Taxonomy loaded: {len(reg.types)} internal types, "
          f"{len(reg.network_codes)} network reason codes.")


if __name__ == "__main__":
    import sys
    init_db(drop="--drop" in sys.argv)
