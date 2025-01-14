import os
from flask import Flask
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
from dotenv import load_dotenv
from api.routes import configure_routes

load_dotenv()

app = Flask(__name__)

configure_routes(app) #NOTE: url prefix is /user

if __name__ == "__main__":
    app.run(debug = True, host="0.0.0.0", port=80)