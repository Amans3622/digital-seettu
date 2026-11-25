import mysql.connector
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=current_app.config["DB_HOST"],
            port=current_app.config["DB_PORT"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"],
            charset="utf8mb4",
            autocommit=False,
        )
    return g.db


def close_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None and conn.is_connected():
        conn.close()


def query(sql, params=(), one=False):
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone() if one else cursor.fetchall()
    finally:
        cursor.close()


def execute(sql, params=()):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        last_id = cursor.lastrowid
        conn.commit()
        return last_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
