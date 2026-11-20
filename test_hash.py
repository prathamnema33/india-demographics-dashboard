from validator import hash_password

password = "Abc12345@"

hashed = hash_password(password)

print("Hash generated:", bool(hashed))