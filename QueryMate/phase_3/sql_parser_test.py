
from phase_3.sql_parser import parse_sql

sql = """
SELECT user_detail.first_name,
       user_detail.last_name,
       user_detail.age,
       user_detail.gender
FROM user_detail
JOIN addresses
ON user_detail.address_id = addresses.id
WHERE addresses.state = :param_1
AND user_detail.gender = :param_2
ORDER BY RANDOM()
LIMIT :limit
"""

result = parse_sql(sql)

print("\nSQL Parsing Result:")
print(result)
