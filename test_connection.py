import oracledb

try:
    conn = oracledb.connect(
        user="system",
        password="Dawar@1407",
        host="localhost",
        port=1521,
        sid="orcl"
    )

    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM USERS")
    count = cursor.fetchone()[0]

    print("Users:", count)
    print("Database Connected Successfully!")

    cursor.close()
    conn.close()

except Exception as e:
    print("Error:", e)