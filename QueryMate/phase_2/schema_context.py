# from sqlalchemy import engine,inspect
# import json
# import pandas as pd
# from phase_2.database import engine
# table_need_to_see=['user_detail','addresses']
# from phase_2.schema_inspector import inspect_database
# schema_info=inspect_database()
# filter_schema={}
# for table_name,material in schema_info.items():
#     if table_name in table_need_to_see:
#         filter_schema[table_name]=material
# print("\nDiscovered tables:", list(schema_info.keys()))
# print("Selected tables:", table_need_to_see)
# print(json.dumps(filter_schema,indent=4))
# relationship_map={}
# relationship_map = []


# relationship_map = []

# for table, material in filter_schema.items():

#     foreign_keys = material.get("foreign_keys", [])

#     for fk in foreign_keys:

#         relationship = {
#             "from_table": table,
#             "from_column": fk["columns"][0],
#             "to_table": fk["referenced_table"],
#             "to_column": fk["referenced_columns"][0]
#         }

#         relationship_map.append(relationship)

# print(relationship_map)
from phase_2.schema_inspector import inspect_database

ALLOWED_TABLES = {
    "user_detail",
    "addresses"
}

def get_schema_context():

    schema_info = inspect_database()

    if not schema_info:
        raise RuntimeError("Database schema inspection failed")

    filter_schema = {
        table_name: material
        for table_name, material in schema_info.items()
        if table_name in ALLOWED_TABLES
    }

    relationship_map = []

    for table, material in filter_schema.items():

        for fk in material.get("foreign_keys", []):

            if not fk["columns"] or not fk["referenced_columns"]:
                continue

            relationship_map.append({
                "from_table": table,
                "from_column": fk["columns"][0],
                "to_table": fk["referenced_table"],
                "to_column": fk["referenced_columns"][0]
            })

    return filter_schema, relationship_map




