import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
import json
import requests
import time
import urllib.parse
from base64 import b64encode
import hmac
import hashlib
import binascii
import datetime
from dotenv import load_dotenv
import os

load_dotenv()

st.header("HERE Tour Planning Demo")

grant_type = 'client_credentials'
oauth_consumer_key = os.getenv('HERE_ACCESS_KEY_ID')
access_key_secret = os.getenv('HERE_ACCESS_KEY_SECRET')
oauth_nonce = str(int(time.time()*1000))
oauth_timestamp = str(int(time.time()))
oauth_signature_method = 'HMAC-SHA256'
oauth_version = '1.0'
url = 'https://account.api.here.com/oauth2/token'

st.sidebar.header("Setup")

# HMAC-SHA256 hashing algorithm to generate the OAuth signature
def create_signature(secret_key, signature_base_string):
    encoded_string = signature_base_string.encode()
    encoded_key = secret_key.encode()
    temp = hmac.new(encoded_key, encoded_string, hashlib.sha256).hexdigest()
    byte_array = b64encode(binascii.unhexlify(temp))
    return byte_array.decode()

# concatenate the six oauth parameters, plus the request parameters from above, sorted alphabetically by the key and separated by "&"
def create_parameter_string(grant_type, oauth_consumer_key,oauth_nonce,oauth_signature_method,oauth_timestamp,oauth_version):
    parameter_string = ''
    parameter_string = parameter_string + 'grant_type=' + grant_type
    parameter_string = parameter_string + '&oauth_consumer_key=' + oauth_consumer_key
    parameter_string = parameter_string + '&oauth_nonce=' + oauth_nonce
    parameter_string = parameter_string + '&oauth_signature_method=' + oauth_signature_method
    parameter_string = parameter_string + '&oauth_timestamp=' + oauth_timestamp
    parameter_string = parameter_string + '&oauth_version=' + oauth_version
    return parameter_string

parameter_string = create_parameter_string(grant_type, oauth_consumer_key,oauth_nonce,oauth_signature_method,oauth_timestamp,oauth_version)
encoded_parameter_string = urllib.parse.quote(parameter_string, safe='')
encoded_base_string = 'POST' + '&' + urllib.parse.quote(url, safe='')
encoded_base_string = encoded_base_string + '&' + encoded_parameter_string

# create the signing key
signing_key = access_key_secret + '&'

oauth_signature = create_signature(signing_key, encoded_base_string)
encoded_oauth_signature = urllib.parse.quote(oauth_signature, safe='')

#---------------------Requesting Token---------------------
body = {'grant_type' : '{}'.format(grant_type)}

headers = {
            'Content-Type' : 'application/x-www-form-urlencoded',
            'Authorization' : 'OAuth oauth_consumer_key="{0}",oauth_nonce="{1}",oauth_signature="{2}",oauth_signature_method="HMAC-SHA256",oauth_timestamp="{3}",oauth_version="1.0"'.format(oauth_consumer_key,oauth_nonce,encoded_oauth_signature,oauth_timestamp)
          }

response = requests.post(url, data=body, headers=headers)
bearer_token = json.loads(response.text)['access_token']

#---------------------Fleet config ---------------------#

d = st.sidebar.date_input("Plan", datetime.date.today())
st.write('Tour planning for:', str(d)+"T"+"07:00"+":00.000Z")

form = st.sidebar.form("tpa_form")

fixed_cost = form.slider('Fixed cost', 0, 10, 5)
distance_cost = form.slider('Distance cost (per km)', 0, 10, 5)
time_cost = form.slider('Time cost (per Hour)', 0, 20, 10)

vehicle_capacity = form.text_input('Vehicle capacity (Boxes)', 20)
vehicle_amount = form.text_input('Nr. of Vehicles', 10)

vehicle_profile = form.selectbox('Vehicle Profile',('car', 'truck'))

shift = form.slider("Vehicle shift:", 0, 23, (6, 23))

show_json = form.checkbox('Show Request/Response')

form.form_submit_button("Submit")

# Tour Planning Request
uploaded_file = st.file_uploader("Choose a file")

if uploaded_file is not None:
    df_plan = pd.read_excel(uploaded_file, sheet_name='plan')
    df_fleet = pd.read_excel(uploaded_file, sheet_name='fleet')
    valid_file = True
else:
    st.write("Please upload valid excel file.")
    valid_file = False

if valid_file:

    st.subheader("Plan")
    st.dataframe(df_plan)

    st.subheader("Fleet")
    st.dataframe(df_fleet)

    trp_fleet = {'types': [], 'profiles': []}
    trp_plan = {'jobs': [], 'relations': []}


    #job start and end
    shift_start_timestamp = str(d)+"T"+str(shift[0]).zfill(2)+":00:00Z"
    shifts_end_timestamp = str(d)+"T"+str(shift[1]).zfill(2)+":00:00Z"


    car_shift_start = {'time': shift_start_timestamp,
                       'location': {'lat': float(df_fleet['shift_start_lat'][0]),
                                    'lng': float(df_fleet['shift_start_lng'][0])
                                    }}

    car_shift_end = {'time': shifts_end_timestamp,
                      'location': {'lat': float(df_fleet['shift_end_lat'][0]),
                                   'lng': float(df_fleet['shift_end_lng'][0])
                                   }}



    if vehicle_profile == 'car':

        vehicle_description = {'id': 'vehicle_1',
                              'profile': 'sprinter',
                              'costs': {'fixed': (float(fixed_cost)),
                                        'distance': distance_cost/float(1000),
                                        'time': time_cost/float(3600)
                                        },
                              'shifts': [{'start': car_shift_start,
                                          'end': car_shift_end}],
                              'capacity': [int(vehicle_capacity)],
                              'amount': int(vehicle_amount)}

        vehicle_profile_description = {'type': 'car', 'name': 'sprinter'}

    elif vehicle_profile == 'truck':

        vehicle_description = {'id': 'truck1',
                              'profile': 'scania',
                              'costs': {'fixed': (float(fixed_cost)),
                                        'distance': (float(distance_cost)),
                                        'time': (float(time_cost))
                                        },
                              'shifts': [{'start': car_shift_start,
                                          'end': car_shift_end}],
                              'capacity': [vehicle_capacity],
                              'amount': vehicle_amount}

        vehicle_profile_description = {'type': 'truck', 'name': 'scania'}

    trp_fleet['types'] = [vehicle_description]
    trp_fleet['profiles'] = [vehicle_profile_description]

    # Plan
    my_jobs = []

    i = 0
    for _, row in df_plan.iterrows():
        place = {}
        #job start and end
        job_start_timestamp = str(d)+"T"+str(row['job_start'])+".000Z"
        job_end_timestamp = str(d)+"T"+str(row['job_end'])+".000Z"

        if row['job_type'] == 'delivery':
            place = {'deliveries' : []}
            place['deliveries'].append({'times':[[job_start_timestamp, job_end_timestamp]],
                                               'location': {'lat': row['job_lat'], 'lng': row['job_lng']},
                                               'duration': row['job_duration'],
                                               'demand': [row['job_demand']]})

        if row['job_type'] == 'pickup':
            place = {'pickups' : []}
            place['pickups'].append({'times':[[job_start_timestamp, job_end_timestamp]],
                                               'location': {'lat': row['job_lat'], 'lng': row['job_lng']},
                                               'duration': row['job_duration'],
                                               'demand': [row['job_demand']]})

        my_jobs.append({'id': row['job_id'], 'places': place})


    trp_plans = {'jobs': my_jobs}

    trp_request = {'id': 'request1',
                   'fleet': trp_fleet,
                   'plan': trp_plans}

    trp_request_json = json.dumps(trp_request)

    if show_json:
        st.subheader("Request")
        st.json(trp_request_json)


    # TRP Requesting
    authorization_token = "Bearer " + bearer_token
    headers = {
                'Content-Type' : 'application/json',
                "Authorization": authorization_token
              }

    # visualization
    centroid_lat = df_plan['job_lat'].mean()
    centroid_lng = df_plan['job_lng'].mean()

    import openrouteservice as ors
    client = ors.Client(key=os.getenv('ORS_CLIENT_KEY'))

    tpa_response = requests.post("https://tourplanning.hereapi.com/v2/problems", data=trp_request_json, headers=headers)

    if show_json:
        st.subheader("Response")
        st.json(tpa_response.text)

    st.subheader("Solution")
    res = json.loads(tpa_response.text)

    tour_stats = {'Total Cost': [res['statistic']['cost']],
                  'Total Distance': [res['statistic']['distance']/float(1000)],
                  'Total Driving Time': [res['statistic']['times']['driving']/float(3600)],
                  'Total Serving Time': [res['statistic']['times']['serving']/float(3600)],
                  'Total Waiting Time': [res['statistic']['times']['waiting']/float(3600)],
                  'Total Break Time': [res['statistic']['times']['break']/float(3600)],
                  }

    df_stats = pd.DataFrame(tour_stats)
    st.dataframe(df_stats)

    tiles_url = "https://2.base.maps.ls.hereapi.com/maptile/2.1/maptile/newest/normal.day/{z}/{x}/{y}/512/png8?apiKey=" + os.getenv('HERE_MAP_API_KEY')

    m = folium.Map([centroid_lat, centroid_lng], zoom_start=11, tiles=tiles_url, attr="<a href=here.com/>With Love From HERE Technologies</a>")

    for i in range(len(res['tours'])):

        coordinates = []
        for stop in res['tours'][i]['stops']:
            coordinates.append([stop['location']['lng'], stop['location']['lat']])
            folium.Marker([stop['location']['lat'], stop['location']['lng']],
                                radius=5,
                                fill_color="#00008b",
                                fill=True
                               ).add_to(m)




        route = client.directions(
            coordinates=coordinates,
            format='geojson',
            validate=False,
        )
        folium.PolyLine(color="#00008b", locations=[list(reversed(coord))
                                   for coord in
                                   route['features'][0]['geometry']['coordinates']]).add_to(m)

        folium_static(m)
