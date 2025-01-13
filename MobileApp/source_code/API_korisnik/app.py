import os
from flask import Flask
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
from dotenv import load_dotenv
from api.routes import configure_routes

load_dotenv()

app = Flask(__name__)

TIMESCALE_DB_URI = os.getenv("TIMESCALE_DB_URI", "Paste the URI here")

timescale_conn = connect(TIMESCALE_DB_URI)
timescale_cursor = timescale_conn.cursor(cursor_factory = RealDictCursor)

configure_routes(app, timescale_conn) #NOTE: url prefix is /user

if __name__ == "__main__":
    app.run(debug = True, host="0.0.0.0", port=80)