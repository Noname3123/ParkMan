import os
from flask import Flask
from api.routes import configure_routes
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

configure_routes(app)

if __name__ == "__main__":
    app.run(debug = True, host = "0.0.0.0", port = 80) 