import os
import csv
#from coordinates import load_shelters_from_csv, find_closest_shelter, process_transit_routes
import requests
from flask import Flask, request, jsonify
import json
from geopy.distance import geodesic
from dotenv import load_dotenv
#from flask_cors import CORS

load_dotenv()
global apikey
apikey = os.environ.get('GOOGLE_MAPS_API_KEY')
app = Flask(__name__)
#CORS(app)


#import bus shelter CSV information, to change to database call probably lol
def load_shelters_from_csv(csv_file):
    shelters = []
    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            geometry = json.loads(row['geometry'])
            coordinates = geometry['coordinates']
            if coordinates:  # Check if coordinates list is not empty
                latitude = float(coordinates[0][1])  # Access the first pair of coordinates
                longitude = float(coordinates[0][0])
                shelter = {
                    'name': row['ADDRESSSTREET'],
                    'latitude': latitude,
                    'longitude': longitude
                }
                shelters.append(shelter)
                #collection.insert_one(shelter)   #Inserted into database
    return shelters


#To find the closes shelter
def find_closest_shelter(point, shelters):
    min_distance = float('inf')
    closest_shelter = None
    # Extract latitude and longitude from the point dictionary
    latitude = point['latitude'] if 'latitude' in point else point['lat']
    longitude = point['longitude'] if 'longitude' in point else point['lng']
    # Calculate distance to each shelter and find the closest one
    for shelter in shelters:
        distance = geodesic((latitude, longitude), (shelter['latitude'], shelter['longitude'])).meters
        if distance < min_distance:
            min_distance = distance
            closest_shelter = shelter
    return closest_shelter

def process_transit_routes(origin, destination, shelters):
    global apikey
    # Use Google Directions API to find transit route between origin and destination
    directions_api_url = 'https://maps.googleapis.com/maps/api/directions/json'
    params = {
        'origin': f'{origin["latitude"]},{origin["longitude"]}',
        'destination': f'{destination["latitude"]},{destination["longitude"]}',
        'mode': 'transit',
        'key': apikey
    }

    response = requests.get(directions_api_url, params=params)
    if response.status_code == 200:
        transit_route = response.json()
    else:
        return {'error': 'Failed to fetch transit route from Google Directions API'}


    # Process the transit route steps
    if 'routes' in transit_route and len(transit_route['routes']) > 0:
        route = transit_route['routes'][0]

        for leg in route['legs']:
            for i, step in enumerate(leg['steps']):
                if step['travel_mode'] == 'TRANSIT':
                    if 'transit_details' in step and 'arrival_stop' in step['transit_details']:
                        arrival_stop_location = step['transit_details']['arrival_stop']['location']

                        closest_shelter = find_closest_shelter(arrival_stop_location, shelters)

                        if closest_shelter is None:
                            remaining_steps = leg['steps'][i:]
                            for remaining_step in remaining_steps:
                                if remaining_step['travel_mode'] == 'TRANSIT' and 'arrival_stop' in remaining_step[
                                    'transit_details']:
                                    transit_stop_location = remaining_step['transit_details']['arrival_stop'][
                                        'location']
                                    closest_shelter = find_closest_shelter(transit_stop_location, shelters)
                                    if closest_shelter:
                                        distance = geodesic(
                                            (arrival_stop_location['lat'], arrival_stop_location['lng']),
                                            (closest_shelter['latitude'], closest_shelter['longitude'])).meters
                                        duration_minutes = distance / 60
                                        walking_step = {
                                            'distance': {'text': f'{distance:.1f} m', 'value': distance},
                                            'duration': {'text': f'{duration_minutes:.0f} mins',
                                                         'value': duration_minutes * 60},
                                            'end_location': closest_shelter,
                                            'html_instructions': f'Walk to shelter: {closest_shelter["name"]}',
                                            'travel_mode': 'WALKING'
                                        }
                                        leg['steps'] = leg['steps'][:i] + [walking_step] + remaining_steps[
                                                                                           remaining_steps.index(
                                                                                               remaining_step):]
                                        break
                            else:
                                continue
    #print(transit_route)
    return transit_route

@app.route("/")
def hello_world():
    variable = start_routing()
    #var = variable.content
    print(dir(variable))
    print(variable.json)
    var = variable.json
    response_content_str = str(var)
    print(variable.data)
    print(variable.response)
    return "<p>"+response_content_str+"</p>"

@app.route("/calculate", methods=['POST'])
def start_routing():

    # Load shelters from CSV
    global apikey

    #loads coordinates data from csv file
    shelters = load_shelters_from_csv('ShelterData.csv')

    ## receive points from front end, convert to geopoints
    data = request.json  # Assuming JSON data is sent from the frontend
    start_address = data.get('startingLocation')
    end_address = data.get('destinationLocation')
    #start_address = "Unionville Go, Markham, Ontario"
    #end_address = "7455 Birchmount Road, Markham, Ontario"
    addressList = [start_address, end_address]

    if not addressList:
        return jsonify({'error': 'Address parameter is required'}), 400

    coordinates = []

    for address in addressList:
        geocode_url = f'https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={apikey}'
        response = requests.get(geocode_url)

        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                location = data['results'][0]['geometry']['location']
                latitude = location['lat']
                longitude = location['lng']
                coordinates.append({'address': address, 'latitude': latitude, 'longitude': longitude})
            else:
                return jsonify ({'error': 'Failed to geocode address'}), 500
        else:
            return jsonify({'error': 'Failed to connect to geocoding service'}), 500
          
    # start_point = {'latitude': float(43.850910), 'longitude': float(-79.313790)}
    # end_point = {'latitude': float(43.8339576), 'longitude': float(-79.3204871)}

    # Find the closest shelters to the start and end points
    start_shelter = find_closest_shelter(coordinates[0], shelters)
    end_shelter = find_closest_shelter(coordinates[1], shelters)
    print(start_shelter)
    print(end_shelter)
    #print(start_shelter[1])
    start2 = {'latitude': float(start_shelter['latitude']), 'longitude': float(start_shelter['longitude'])}
    end2 = {'latitude': float(end_shelter['latitude']), 'longitude': float(end_shelter['longitude'])}

    # Process transit routes and adjust for shelters
    route_info = process_transit_routes(start2, end2, shelters)

    #print(route_info)
    #print(jsonify(route_info))

    return jsonify(route_info)

if __name__ == '__main__':
    app.run()