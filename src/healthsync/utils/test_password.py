import bcrypt

# The hash from database
stored_hash = "$2b$12$lTbYGfvveSiF7QiK8qUkbeLiXxqoQg2M0uZcJKVLEtIGa/61LnC6O"

# The plaintext password from CSV
plaintext_password = "JK9nyCj6guUi"

# Check if they match
if bcrypt.checkpw(plaintext_password.encode('utf-8'), stored_hash.encode('utf-8')):
    print("✅ Password matches!")
else:
    print("❌ Password does NOT match")
    print("The password in the database is different from the CSV")