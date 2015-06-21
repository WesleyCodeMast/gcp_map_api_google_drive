import functions_framework

import base64
import functions_framework

import os
import overpy
import requests
import folium
from shapely.geometry import Polygon, Point
import geopandas as gpd
from shapely.ops import nearest_points
from google.oauth2 import service_account
from googleapiclient.discovery import build
import gspread
from google.oauth2.credentials import Credentials as GoogleCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload


# The Google Sheet ID
sheet_id = '14nKoNuhO0AHVDzjt6AUHsysEObNvczZfArpa_gNTJuQ'

# Your API key (not needed for Google Maps Geocoding API if you have API credentials)
api_key = "-"
credentials_dict = {

}
def get_address_from_google_sheet():
    try:
        # Authenticate with Google Sheets API
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        client = gspread.authorize(creds)

        # Open the Google Sheet
        sheet = client.open_by_key(sheet_id)
        # Get the first worksheet
        worksheet = sheet.get_worksheet(0)  # Assuming the data is in the first worksheet
        
        # Get all values from the worksheet
        all_values = worksheet.get_all_values()
        
        # Iterate over rows in reverse order to find the last non-empty address in column C
        for row in reversed(all_values):
            address = row[2]  # Assuming address is in column C (index 2)
            if address.strip():  # Check if the address is not empty after stripping whitespace
                print("Retrieved Address:", address)
                return address
        
        # If no address is found, print a message
        print("No address found in the sheet.")
        return None
    except Exception as e:
        print(f"Error accessing Google Sheet: {e}")
        return None

def geocode_address(address):
    try:
        # Geocoding API to get latitude and longitude
        geocoding_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address.replace(' ', '+')}&key={api_key}"
        geocoding_response = requests.get(geocoding_url)
        geocoding_data = geocoding_response.json()

        if geocoding_data['status'] == 'OK':
            location = geocoding_data['results'][0]['geometry']['location']
            lat = location['lat']
            lon = location['lng']
            return lat, lon
        else:
            print(f"Geocoding failed. Status: {geocoding_data['status']}")
            return None, None
    except Exception as e:
        print(f"Error geocoding address: {e}")
        return None, None

def generate_image(lat, lon):
    try:
        # Query OpenStreetMap data using overpy
        api = overpy.Overpass()
        bbox = f"{lat-0.01},{lon-0.01},{lat+0.01},{lon+0.01}"
        result = api.query(f"""
            way["building"]({bbox});
            (._;>;);
            out body;
        """)

        # Create GeoDataFrame with building footprints
        buildings = []
        for way in result.ways:
            nodes = [(node.lon, node.lat) for node in way.nodes]
            if nodes:  # If there are nodes, create a polygon
                polygon = Polygon(nodes)
                buildings.append(polygon)

        # Create a GeoDataFrame
        gdf_buildings = gpd.GeoDataFrame({'geometry': buildings}, crs='EPSG:4326')

        # Find the nearest polygon to the geocoded location
        point = Point(lon, lat)
        gdf_buildings['distance'] = gdf_buildings.apply(lambda row: point.distance(row.geometry), axis=1)
        nearest_building = gdf_buildings.iloc[gdf_buildings['distance'].argmin()]

        # Create a map centered on the geocoded location with satellite imagery
        map_osm = folium.Map(
            location=[lat, lon],
            zoom_start=18,
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Esri Satellite',
            overlay=False,
            control=True,
        )

        # Add the nearest building footprint to the map
        folium.GeoJson(nearest_building.geometry, name="OSM Building", style_function=lambda x: {'fillColor': 'blue', 'color': 'blue', 'weight': 1, 'fillOpacity': 0.3}).add_to(map_osm)

        # Add a marker for the geocoded location
        folium.Marker([lat, lon], popup='Geocoded Location').add_to(map_osm)

        # Save the map to an HTML file
        html_file_path = 'osm_map_with_nearest_building.html'
        map_osm.save(html_file_path)
        print(f"Map with the nearest building footprint saved as '{html_file_path}'.")
        return html_file_path
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

def get_folder_path(folder_id, drive_service):
    try:
        folder_path = []
        while True:
            folder_info = drive_service.files().get(fileId=folder_id, fields='id, name, parents').execute()
            folder_name = folder_info['name']
            folder_path.insert(0, folder_name)
            if 'parents' in folder_info and folder_info['parents']:
                folder_id = folder_info['parents'][0]
            else:
                break
        return '/'.join(folder_path)
    except Exception as e:
        print(f"Error getting folder path: {e}")
        return None

def create_google_drive_folder(folder_name, parent_folder_id='1HECVJZ1J__gzKjR4ZHhQBSMlpZvlruCQ'):
    try:
        # Authenticate with Google Drive API
        credentials = service_account.Credentials.from_service_account_info(credentials_dict, scopes=['https://www.googleapis.com/auth/drive'])
        drive_service = build('drive', 'v3', credentials=credentials)

        # Create folder metadata with parent folder ID
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]  # Specify the parent folder here
        }

        # Create the folder inside the specified parent folder
        folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
        print(f"Google Drive folder '{folder_name}' created with ID: {folder_id} inside parent folder ID: {parent_folder_id}")

        return folder_id
    except Exception as e:
        print(f"Error creating Google Drive folder: {e}")
        return None

def upload_file_to_google_drive(file_path, folder_id):
    try:
        # Authenticate with Google Drive API
        credentials = service_account.Credentials.from_service_account_info(credentials_dict, scopes=['https://www.googleapis.com/auth/drive'])
        drive_service = build('drive', 'v3', credentials=credentials)

        # Upload file to Google Drive
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, resumable=True)
        uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, parents').execute()
        file_id = uploaded_file.get('id')

        # Check if the file is uploaded to the correct folder
        uploaded_parents = uploaded_file.get('parents', [])
        if folder_id in uploaded_parents:
            print(f"File '{file_path}' uploaded to Google Drive folder with ID: {folder_id}")
        else:
            print(f"File '{file_path}' was uploaded, but not in the expected folder.")

        return file_id
    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")
        return None

def addedNewRow():
    # Get address from Google Sheet
    address = get_address_from_google_sheet()
    if address:
        # Geocode the address
        lat, lon = geocode_address(address)
        if lat is not None and lon is not None:
            # Generate image
            html_file_path = generate_image(lat, lon)
            if html_file_path:
                # Create Google Drive folder
                folder_id = create_google_drive_folder(address)
                if folder_id:
                    # Upload image to Google Drive folder
                    upload_file_to_google_drive(html_file_path, folder_id)



@functions_framework.http
def hello_http(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    # request_json = request.get_json(silent=True)
    # request_args = request.args

    # if request_json and 'name' in request_json:
    #     name = request_json['name']
    # elif request_args and 'name' in request_args:
    #     name = request_args['name']
    # else:
    #     name = 'World'
    addedNewRow()

    # return 'Hello {}!'.format(name)
