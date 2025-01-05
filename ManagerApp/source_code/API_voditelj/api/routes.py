from flask import request, jsonify, Blueprint

api = Blueprint('api', __name__)

#Simulirani podaci
parks = []

@api.route('/parks', methods = ['POST']) #Definiranje URL route-a za dodavanje parkinga
def add_park():
    data = request.get_json()
    parks.append(data) #Dodavanje parkinga u simuliranu listu
    return jsonify({"message": "Park added"}), 201

@api.route('/parks', methods = ['GET']) #Definiranje URL route-a za pregled svih parkinga
def get_all_parks():
    return jsonify(parks)

@api.route('/parks/<int:park_id>', methods = ['GET']) #Definiranje URL route-a za pregled određenog parkinga
def get_park(park_id):
    #Traženje parkinga sa specifičnim ID-jem
    park = next((park for park in parks if park['id'] == park_id), None)
    if park is not None:
        return jsonify(park)
    else:
        return jsonify({"message": "Park not found"}), 404
    
@api.route('/parks/<int:park_id>', methods = ['DELETE']) #Definiranje URL route-a za brisanje određenog parkinga
def delete_park(park_id):
    global parks #Omogućava modificiranje liste definirane izvan funkcije
    park = next((park for park in parks if park['id'] == park_id), None)
    if park is not None:
        parks = [p for p in parks if p['id'] != park_id] #Brisanje na način da se stvara nova lista bez parkinga koji se briše
        return jsonify({"message": "Park deleted"})
    else:
        return jsonify({"message": "Park not found"}), 404

def configure_routes(app):
    app.register_blueprint(api, url_prefix = '/api')