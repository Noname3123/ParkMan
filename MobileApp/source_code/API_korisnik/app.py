from flask import Flask
from api.routes import configure_routes

app = Flask(__name__)

configure_routes(app) #NOTE: url prefix is /user

if __name__ == "__main__":
    app.run(debug = True, host="0.0.0.0", port=80)