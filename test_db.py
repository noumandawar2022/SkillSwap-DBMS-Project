from database.db_connection import get_connection

try:
    conn = get_connection()
    print("Connected Successfully!")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM USERS")

    print("Users:", cursor.fetchone()[0])

    cursor.close()
    conn.close()

except Exception as e:
    print("Error:", e)