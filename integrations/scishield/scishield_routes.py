# integrations/scishield/scishield_routes.py
from flask import Flask, redirect, request, render_template, url_for, session, make_response, jsonify, flash, Blueprint
from functools import wraps
import uuid
from werkzeug.utils import secure_filename
from pytz import timezone
from typing import Dict, Tuple, Optional, List
import base64  # Import the base64 module
import openai
import requests
from PIL import Image
import os
import traceback
# from labtools_authorizer import *
from vitality_tools.secrets_manager_tools import get_secrets
import boto3
import base64
import json
import re

bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")  # Replace with your AWS region
runtime = boto3.client("bedrock-runtime","us-east-1")
my_secrets = get_secrets("labtools-dev", "us-east-1", "dev")

# Create a Blueprint for your SciShield routes
scishield_bp = Blueprint("chem-snap", __name__)

# OpenAI API Key
api_key = my_secrets.get('OPEN_AI_API_KEY', None)
product_key = my_secrets.get('PRODUCT_KEY', None)
openai.api_key = api_key


# Central Route Methods - 

def extract_value_from_raw(data_string, field_name):
    """
    Extract the value for a given field from the raw JSON-like string.
    This function handles fields that might have variations in names.
    """
    # Define patterns for possible variations of each field
    field_aliases = {
        'Chemical name': [r"Chemical name or CAS number", r"Chemical Name"],
        'CAS number': [r"Chemical name or CAS number", r"CAS Number"],
        'Amount': [r"Amount"],
        'Units': [r"Units"],
        'Lot number': [r"Lot Number"],
        'Product number': [r"Product Number"],
        'Product name': [r"Product Name"],
        'Manufacturer': [r"Manufacturer"]
    }

    # Iterate over aliases for the given field and try to extract the value
    for alias in field_aliases.get(field_name, [field_name]):
        pattern = rf'"{alias}":\s*("(.*?)"|null)'
        match = re.search(pattern, data_string, re.IGNORECASE)
        if match:
            return match.group(2) if match.group(2) is not None else "null"
    return "null"


def encode_image(image_path:str):
    """
    Encode an image file into a Base64-encoded string.

    Args:
        image_path (str): The path to the image file to be encoded.

    Returns:
        str: The Base64-encoded representation of the image.

    Raises:
        FileNotFoundError: If the specified image file does not exist.
    """
    try:
        with open(image_path, "rb") as image_file:
            # Read the binary data from the image file and encode it in Base64
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
            return encoded_image
    except FileNotFoundError:
        raise FileNotFoundError(f"The specified image file '{image_path}' does not exist.")


def download_file_to_tmp(url: str, chunk_size: int = 8192) -> str:
    """
    Download a file from a given URL and save it to a unique filename in the /tmp directory.

    Args:
        url (str): The URL of the file to download.
        chunk_size (int, optional): The size of each data chunk to download at a time (default: 8192 bytes).

    Raises:
        Exception: If the download fails or the URL is invalid.

    Returns:
        str: The path of the downloaded file.
    """
    try:
        # Send an HTTP GET request to the URL
        response = requests.get(url, stream=True)

        # Check if the response status code is OK (200)
        response.raise_for_status()

        # Generate a unique filename using UUID and save it to /tmp
        unique_filename = f'/tmp/{uuid.uuid4()}.png'

        with open(unique_filename, 'wb') as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file.write(chunk)

        return unique_filename
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to download the file from {url}: {e}")


def download_file_to_tmp2(file, chunk_size: int = 8192) -> str:
    """
    Save a file from a Flask request.files['file'] object to a unique filename in the /tmp directory.

    Args:
        file (FileStorage): The file object obtained from request.files['file'] in Flask.
        chunk_size (int, optional): The size of each data chunk to download at a time (default: 8192 bytes).

    Raises:
        Exception: If the file save fails.

    Returns:
        str: The path of the saved file.
    """
    try:
        # Generate a unique filename using UUID and save it to /tmp
        unique_filename = f'/tmp/{uuid.uuid4()}.png'

        with open(unique_filename, 'wb') as saved_file:
            # Read the file in chunks and save it
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                saved_file.write(chunk)

        return unique_filename
    except Exception as e:
        raise Exception(f"Failed to save the file: {e}")


def process_image(image_path: str, final_square_size: int, delete_original: bool, verbose: bool) -> None:
    """
    Processes an image to fit it within a specified square size while maintaining its aspect ratio.

    This function resizes an image to fit within a square of a given size, 
    pads it to maintain aspect ratio, and optionally deletes the original image.

    Args:
        image_path (str): The file path of the image to be processed.
        final_square_size (int): The size of the square within which the image is to be fitted.
        delete_original (bool): If True, the original image file is deleted after processing.
        verbose (bool): If True, prints a message upon successful completion of processing.

    Returns:
        None: This function does not return anything.

    Raises:
        Exception: Propagates any exceptions raised during image processing.
    """
    try:
        # Open the image
        input_img = Image.open(image_path)

        # Get the original image dimensions
        original_width, original_height = input_img.size

        # Calculate the scaling factor to fit the image within the square
        scale_factor = min(final_square_size / original_width, final_square_size / original_height)

        # Calculate the new dimensions
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)

        # Resize the image while maintaining its aspect ratio
        input_img = input_img.resize((new_width, new_height), Image.LANCZOS)

        # Create a new blank square image with the final_square_size
        output_img = Image.new("RGB", (final_square_size, final_square_size), (0, 0, 0))

        # Calculate the position to paste the resized image (centered)
        x_offset = (final_square_size - new_width) // 2
        y_offset = (final_square_size - new_height) // 2

        # Paste the resized image onto the blank square image
        output_img.paste(input_img, (x_offset, y_offset))

        # Save the padded image to file, overwriting the original if needed
        output_image_name = os.path.splitext(image_path)[0] + f"_padded.png"
        output_img.save(output_image_name)

        # Optionally, delete the original image
        if delete_original:
            os.remove(image_path)

        # Optionally, print a verbose message
        if verbose:
            print(f"Padded: {image_path}")

    except Exception as e:
        print(f"Error processing {image_path}: {str(e)}")


def is_image_large(file_path: str, max_size_mb: float = 20) -> bool:
    """
    Check if an image file exceeds a specified size limit.

    Args:
        file_path: Path to the file to be checked.
        max_size_mb: Maximum allowed file size in megabytes (default: 20).

    Returns:
        bool: True if the file size exceeds max_size_mb, False otherwise.

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    # Check if the file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

    # Get the file size in bytes
    file_size_bytes = os.path.getsize(file_path)

    # Convert bytes to megabytes
    file_size_mb = file_size_bytes / (1024 * 1024)

    # Check if the file size is greater than the specified maximum size
    return file_size_mb > max_size_mb


def extract_value_git(data_string: str, key: str) -> str:
    """
    Extract a value associated with a given key from a specially formatted string.

    Args:
        data_string: The input string containing key-value pairs.
        key: The key whose value needs to be extracted.

    Returns:
        str: The extracted value, stripped of leading/trailing whitespace.
    """
    start_index = data_string.find(f'"{key}"') + len(f'"{key}"') + 2
    end_index = data_string.find(',', start_index)
    value = data_string[start_index:end_index]
    return value.strip()


def extract_value_claude(input_string: str) -> Dict:
    """
    Transform a JSON string into a dictionary with standardized keys.

    Args:
        input_string: JSON string containing chemical information with various key formats.

    Returns:
        Dict[str, Any]: Dictionary with standardized keys mapped from the input.

    Note:
        The function converts all keys to lowercase before processing and maps
        them to standardized output keys based on substring matching.
    """
    # Define the mapping rules for substrings to desired output keys
    key_map = {
        "chemical": "Chemical Name",
        "cas": "CAS Number",
        "amount": "Amount",
        "unit": "Units",
        "lot": "Lot Number",
        "product_num": "Product Number",
        "product_nam": "Product Name",
        "manuf": "Manufacturer"
    }

    # Load the input string into a Python dictionary and convert keys to lowercase
    input_dict = json.loads(input_string.lower())

    # Initialize the output dictionary
    output_dict = {}

    # Iterate through the input dictionary and map the keys based on substrings
    for key, value in input_dict.items():
        # Find the appropriate output key based on substring matching
        for substring, output_key in key_map.items():
            if substring in key:
                output_dict[output_key] = value
                break  # Stop searching once a match is found

    return output_dict


def is_image_file(file_path: str) -> bool:
    """
    Check if a file has a valid image extension.

    Args:
        file_path: Path to the file to be checked.

    Returns:
        bool: True if the file extension matches known image formats, False otherwise.
    """
    valid_extensions = ['.png', '.jpeg', '.jpg', '.webp', '.gif']
    _, file_extension = os.path.splitext(file_path.lower())
    return file_extension in valid_extensions

#swagger docs
@scishield_bp.route('/docs', methods=['GET', 'POST'])
def scishield_swagger() -> str:
    """
    Serve the Swagger UI documentation page for SciShield API.

    Returns:
        str: Rendered HTML template for Swagger UI with the OpenAPI specification URL.

    Note:
        This endpoint serves both GET and POST requests and displays the Swagger UI
        interface configured with the SciShield OpenAPI specification.
    """
    
    openapi_url = url_for('static', filename='swagger/scishield/scishield_swagger.yaml')
    return render_template('swaggerui.html', openapi_url=openapi_url)


# git image routes
@scishield_bp.route('/image_upload_url', methods=['POST'])
def scishield_interpret_image() -> Tuple:
    """
    Process an image from a URL and extract chemical label information using GPT-4 vision.

    Args:
        org (str): Organization identifier from form data.
        api_key (str): API key from form data for authentication.
        url (str): URL of the image to process from form data.

    Returns:
        Tuple[Response, int]: JSON response with status and extracted data, and HTTP status code.
        Possible status codes:
        - 200: Successfully processed image
        - 206: Partial success (some null values detected)
        - 500: Error (invalid API key, invalid image, or processing failure)

    Note:
        The image is downloaded temporarily, validated for type and size (max 20MB),
        then sent to GPT-4 vision for label information extraction.
    """
    try:
        org = request.form.get('org', '')
        apikey = request.form.get('api_key', '')
        url = request.form.get('html', '')


        if(apikey != product_key):
            final = { 'status' : "500", 'data' : {'post': 'Error- API Key is Invaild'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        if(not is_image_file(url)):
            final = { 'status' : "500", 'data' : {'post': 'Error- Image is Invaild File Type - Vaild file types are : [.png, .jpeg, .jpg, .webp, .gif]'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        # get the image
        tmp_path = download_file_to_tmp(url)
        if(is_image_large(tmp_path, 20)):
            final = { 'status' : "500", 'data' : {'post': 'Error - Image is too large'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
            
        base64_image = encode_image(tmp_path)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
            {
                "role": "user",
                "content": [
                {
                    "type": "text",
                    "text": """Please provide a structured JSON response that contains info on the label in the photo sepcificly look for: 
                ( Chemical name or CAS number, 
                Amount, 
                Units, 
                Lot number, 
                Product number, 
                Product name , 
                Manufacturer )
                if no label info is detected say null
                if grade information is found add to product name if its not keep text as is
                if no product name use chemical name
                add no text besdies null about what you can't find to response
                """
                },
                {
                    "type": "image_url",
                    "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
                ]
            }
            ],
            "max_tokens": 300
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        json_response = res.json()
        print(json_response)

        # Extracting the content from the API response
        data_string = json_response['choices'][0]['message']['content']

        # Extracting the required information
        clean_dict = {
            'Chemical name': extract_value_from_raw(data_string, 'Chemical name'),
            'CAS number': extract_value_from_raw(data_string, 'CAS number'),
            'Amount': extract_value_from_raw(data_string, 'Amount'),
            'Units': extract_value_from_raw(data_string, 'Units'),
            'Lot number': extract_value_from_raw(data_string, 'Lot number'),
            'Product number': extract_value_from_raw(data_string, 'Product number'),
            'Product name': extract_value_from_raw(data_string, 'Product name'),
            'Manufacturer': extract_value_from_raw(data_string, 'Manufacturer')
        }

        clean_dict['raw output'] = data_string

        # Final clean-up of values
        final_dict = {}
        for key, value in clean_dict.items():
            # Further cleaning unnecessary symbols
            cleaned_value = value.replace('"', '').replace('/', '').replace('\\', '').replace('}','').replace('\n','').replace('`','')
            final_dict[key] = cleaned_value

        final = { 'status' : "200", 'data' : {'post': final_dict}}
        if('null' in data_string):
            final = { 'status' : "206", 'data' : {'post': final_dict}}

        
        # Displaying the clean dictionary
        print(final)
        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        final = { 'status' : "500", 'data' : {'post': 'Error- Image Failed to Upload'}}
        # Displaying the clean dictionary
        print(e)
        print(traceback_str)

        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


@scishield_bp.route('/image_upload_b64', methods=['POST'])
def scishield_interpret_image2() -> Tuple:
    """
    Process an uploaded image file and extract chemical label information using GPT-4 vision.

    Args:
        org (str): Organization identifier from form data.
        api_key (str): API key from form data for authentication.
        file (FileStorage): Uploaded image file from form data.

    Returns:
        Tuple[Response, int]: JSON response with status and extracted data, and HTTP status code.
        Possible status codes:
        - 200: Successfully processed image
        - 206: Partial success (some null values detected)
        - 500: Error (invalid API key, invalid image, or processing failure)

    Note:
        The uploaded file is saved temporarily, validated for type and size (max 20MB),
        then sent to GPT-4 vision for label information extraction.
    """
    try:
        org = request.form.get('org', '')
        apikey = request.form.get('api_key', '')
        file = request.files['file']


        if(apikey != product_key):
            final = { 'status' : "500", 'data' : {'post': 'Error- API Key is Invaild'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        
        # get the image
        tmp_path = download_file_to_tmp2(file)

        #process_image(tmp_path, 1024, False, False)
        if(is_image_large(tmp_path, 20)):
            final = { 'status' : "500", 'data' : {'post': 'Error - Image is too large'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
            
        if(not is_image_file(tmp_path)):
            final = { 'status' : "500", 'data' : {'post': 'Error- Image is Invaild File Type - Vaild file types are : [.png, .jpeg, .jpg, .webp, .gif]'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        base64_image = encode_image(tmp_path)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Please provide a structured JSON response that contains info on the label in the photo specifically look for: 
                        (Chemical name or CAS number, 
                        Amount, 
                        Units, 
                        Lot number, 
                        Product number, 
                        Product name, 
                        Manufacturer)
                        if no label info is detected say null
                        if grade information is found add to product name if its not keep text as is
                        if no product name use chemical name
                        add no text besides null about what you can't find to response
                        """
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        json_response = res.json()
        print(json_response)

        # Extracting the content from the API response
        data_string = json_response['choices'][0]['message']['content']

        # Extracting the required information
        clean_dict = {
            'Chemical name': extract_value_from_raw(data_string, 'Chemical name'),
            'CAS number': extract_value_from_raw(data_string, 'CAS number'),
            'Amount': extract_value_from_raw(data_string, 'Amount'),
            'Units': extract_value_from_raw(data_string, 'Units'),
            'Lot number': extract_value_from_raw(data_string, 'Lot number'),
            'Product number': extract_value_from_raw(data_string, 'Product number'),
            'Product name': extract_value_from_raw(data_string, 'Product name'),
            'Manufacturer': extract_value_from_raw(data_string, 'Manufacturer')
        }

        clean_dict['raw output'] = data_string

        # Final clean-up of values
        final_dict = {}
        for key, value in clean_dict.items():
            # Further cleaning unnecessary symbols
            cleaned_value = value.replace('"', '').replace('/', '').replace('\\', '').replace('}','').replace('\n','').replace('`','')
            final_dict[key] = cleaned_value

        final = { 'status' : "200", 'data' : {'post': final_dict}}
        if('null' in data_string):
            final = { 'status' : "206", 'data' : {'post': final_dict}}

        
        # Displaying the clean dictionary
        print(final)
        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        final = { 'status' : "500", 'data' : {'post': 'Error- Image Failed to Upload'}}
        # Displaying the clean dictionary
        print(e)
        print(traceback_str)

        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


# claude image routes 
@scishield_bp.route('/claude35/sonnet/image_upload', methods=['POST'])
def scishield_c_interpret_image1() -> Tuple:
    """
    Process an uploaded image file and extract chemical label information using Claude 3.5 Sonnet.

    Args:
        org (str): Organization identifier from form data (currently unused).
        api_key (str): API key from form data for authentication (currently unchecked).
        file (FileStorage): Uploaded image file from form data.

    Returns:
        Tuple[Response, int]: JSON response with status and extracted data, and HTTP status code.
        Possible status codes:
        - 200: Successfully processed image with all fields found
        - 206: Partial success (some null values detected)
        - 500: Error (invalid image type, size too large, or processing failure)

    Note:
        - The image is validated for type (.png, .jpeg, .jpg, .webp, .gif) and size (max 9MB)
        - Uses Claude 3.5 Sonnet model to extract chemical label information
        - Returns cleaned data with special characters removed
        - Includes raw model output in the response for debugging
    """
    try:
        org = request.form.get('org', '')
        apikey = request.form.get('api_key', '')
        file = request.files['file']

        if(apikey != product_key):
            final = { 'status' : "500", 'data' : {'post': 'Error- API Key is Invaild'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        
        # get the image
        tmp_path = download_file_to_tmp2(file)

        #process_image(tmp_path, 1024, False, False)
        if(is_image_large(tmp_path, 9)):
            final = { 'status' : "500", 'data' : {'post': 'Error - Image is too large for Claude'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
            
        if(not is_image_file(tmp_path)):
            final = { 'status' : "500", 'data' : {'post': 'Error- Image is Invaild File Type - Vaild file types are : [.png, .jpeg, .jpg, .webp, .gif]'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        base64_image = encode_image(tmp_path)
        request_text = """Please provide a structured JSON response that contains info on the label in the photo specifically look for: 
                        (Chemical name or CAS_Number, 
                        Amount, 
                        Units, 
                        Lot_Number, 
                        Product_Number, 
                        Product_Name, 
                        Manufacturer)
                        make sure the keys for each apear exactly as written above,
                        if no label info is detected say null,
                        if grade information is found add to product name if its not keep text as is,
                        if no product name use chemical name,
                        add no text besides null about what you can't find to response.
                        """

        body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64_image,
                                    },
                                },
                                {"type": "text", "text": request_text},
                                #{"type": "text", "text": "What is in this image?"},
                            ],
                        }
                    ],
                }
            )

        response = runtime.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            body=body
        )
        response_body = json.loads(response.get("body").read())
        data_string = response_body['content'][0]['text']
        print(response_body['content'][0]['text'])
        #Extracting the required information
        print('data string')
        print()
        print(data_string)
        print()
        clean_dict = extract_value_claude(data_string)
        clean_dict['raw output'] = data_string
        final_dict = {}
        for key, value in clean_dict.items():
            try:
                if value is not None:  # Check if value is not None
                    value = str(value)
                    cleaned_value = value.replace('"', '').replace('/', '').replace('\\', '').replace('}','').replace('\n','').replace('`','')
                else:
                    cleaned_value = 'Null'  # Or set it to any default value you'd prefer
                final_dict[key] = cleaned_value
            except:
                 cleaned_value = 'Null'
                 final_dict[key] = cleaned_value

        final = { 'status' : "200", 'data' : {'post': final_dict}}
        if('null' in data_string):
            final = { 'status' : "206", 'data' : {'post': final_dict}}
        # final = { 'status' : "200", 'data' : {'post': data_string}}
        # if('null' in data_string):
        #     final = { 'status' : "206", 'data' : {'post': data_string}}
        # Displaying the clean dictionary

        print(final)
        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        final = { 'status' : "500", 'data' : {'post': 'Error- Image Failed to Download'}}
        # Displaying the clean dictionary
        print(e)
        print(traceback_str)

        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

@scishield_bp.route('/claude3/sonnet/image_upload', methods=['POST'])
def scishield_c_interpret_image2() -> Tuple:
    """
    Process an uploaded image file and extract chemical label information using Claude 3 Sonnet model.

    Args:
        org (str): Organization identifier from form data.
        api_key (str): API key from form data for authentication.
        file (FileStorage): Uploaded image file from form data.

    Returns:
        Tuple[Response, int]: A tuple containing:
            - Flask Response object with JSON data
            - HTTP status code (200, 206, or 500)

    Notes:
        - Validates API key before processing
        - Checks image file type (.png, .jpeg, .jpg, .webp, .gif) and size (<9MB)
        - Uses Claude 3 Sonnet model to extract chemical label information
        - Returns cleaned data with standardized keys and removed special characters
        - Includes raw model output in response for debugging purposes

    Response Status Codes:
        - 200: Success - All requested fields found
        - 206: Partial Success - Some null values detected
        - 500: Error - Invalid API key, invalid image, or processing failure
    """
    try:
        org = request.form.get('org', '')
        apikey = request.form.get('api_key', '')
        file = request.files['file']

        if(apikey != product_key):
            final = { 'status' : "500", 'data' : {'post': 'Error- API Key is Invaild'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        
        # get the image
        tmp_path = download_file_to_tmp2(file)

        #process_image(tmp_path, 1024, False, False)
        if(is_image_large(tmp_path, 9)):
            final = { 'status' : "500", 'data' : {'post': 'Error - Image is too large for Claude'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
            
        if(not is_image_file(tmp_path)):
            final = { 'status' : "500", 'data' : {'post': 'Error- Image is Invaild File Type - Vaild file types are : [.png, .jpeg, .jpg, .webp, .gif]'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        base64_image = encode_image(tmp_path)
        request_text = """Please provide a structured JSON response that contains info on the label in the photo specifically look for: 
                        (Chemical name or CAS_Number, 
                        Amount, 
                        Units, 
                        Lot_Number, 
                        Product_Number, 
                        Product_Name, 
                        Manufacturer)
                        make sure the keys for each apear exactly as written above,
                        if no label info is detected say null,
                        if grade information is found add to product name if its not keep text as is,
                        if no product name use chemical name,
                        add no text besides null about what you can't find to response.
                        """

        body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64_image,
                                    },
                                },
                                {"type": "text", "text": request_text},
                                #{"type": "text", "text": "What is in this image?"},
                            ],
                        }
                    ],
                }
            )

        response = runtime.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=body
        )
        response_body = json.loads(response.get("body").read())
        data_string = response_body['content'][0]['text']
        print(response_body['content'][0]['text'])
        #Extracting the required information

        clean_dict = extract_value_claude(data_string)
        clean_dict['raw output'] = data_string
        final_dict = {}
        for key, value in clean_dict.items():
            try:
                if value is not None:  # Check if value is not None
                    value = str(value)
                    cleaned_value = value.replace('"', '').replace('/', '').replace('\\', '').replace('}','').replace('\n','').replace('`','')
                else:
                    cleaned_value = 'Null'  # Or set it to any default value you'd prefer
                final_dict[key] = cleaned_value
            except:
                 cleaned_value = 'Null'
                 final_dict[key] = cleaned_value


        final = { 'status' : "200", 'data' : {'post': final_dict}}
        if('null' in data_string):
            final = { 'status' : "206", 'data' : {'post': final_dict}}
        # final = { 'status' : "200", 'data' : {'post': data_string}}
        # if('null' in data_string):
        #     final = { 'status' : "206", 'data' : {'post': data_string}}
        # Displaying the clean dictionary

        print(final)
        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        final = { 'status' : "500", 'data' : {'post': 'Error- Image Failed to Download'}}
        # Displaying the clean dictionary
        print(e)
        print(traceback_str)

        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

@scishield_bp.route('/claude3/haiku/image_upload', methods=['POST'])
def scishield_c_interpret_image3() -> Tuple:
    """
    Process an uploaded image file and extract chemical label information using Claude 3 Haiku model.

    Args:
        org (str): Organization identifier from form data (currently unused in processing).
        api_key (str): API key from form data for authentication.
        file (FileStorage): Uploaded image file from form data.

    Returns:
        Tuple[Response, int]: A tuple containing:
            - Flask Response object with JSON data
            - HTTP status code (200, 206, or 500)

    Notes:
        - Validates API key against product_key before processing
        - Checks image file type (.png, .jpeg, .jpg, .webp, .gif) and size (<9MB)
        - Uses Claude 3 Haiku model (anthropic.claude-3-haiku-20240307-v1:0) for extraction
        - Processes response to clean special characters and standardize null values
        - Includes raw model output in response for debugging

    Response Status Codes:
        - 200: Success - All requested fields found
        - 206: Partial Success - Some null values detected in response
        - 500: Error - Invalid API key, invalid image, or processing failure
    """
    try:
        org = request.form.get('org', '')
        apikey = request.form.get('api_key', '')
        file = request.files['file']

        if(apikey != product_key):
            final = { 'status' : "500", 'data' : {'post': 'Error- API Key is Invaild'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        
        # get the image
        tmp_path = download_file_to_tmp2(file)

        #process_image(tmp_path, 1024, False, False)
        if(is_image_large(tmp_path, 9)):
            final = { 'status' : "500", 'data' : {'post': 'Error - Image is too large for Claude'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
            
        if(not is_image_file(tmp_path)):
            final = { 'status' : "500", 'data' : {'post': 'Error- Image is Invaild File Type - Vaild file types are : [.png, .jpeg, .jpg, .webp, .gif]'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        base64_image = encode_image(tmp_path)
        request_text = """Please provide a structured JSON response that contains info on the label in the photo specifically look for: 
                        (Chemical name or CAS_Number, 
                        Amount, 
                        Units, 
                        Lot_Number, 
                        Product_Number, 
                        Product_Name, 
                        Manufacturer)
                        make sure the keys for each apear exactly as written above,
                        if no label info is detected say null,
                        if grade information is found add to product name if its not keep text as is,
                        if no product name use chemical name,
                        add no text besides null about what you can't find to response.
                        """

        body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64_image,
                                    },
                                },
                                {"type": "text", "text": request_text},
                                #{"type": "text", "text": "What is in this image?"},
                            ],
                        }
                    ],
                }
            )

        response = runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=body
        )
        response_body = json.loads(response.get("body").read())
        data_string = response_body['content'][0]['text']
        print(response_body['content'][0]['text'])
        #Extracting the required information
        print('data string')
        print()
        print(data_string)
        print()
        clean_dict = extract_value_claude(data_string)
        clean_dict['raw output'] = data_string
        final_dict = {}
        for key, value in clean_dict.items():
            try:
                if value is not None:  # Check if value is not None
                    value = str(value)
                    cleaned_value = value.replace('"', '').replace('/', '').replace('\\', '').replace('}','').replace('\n','').replace('`','')
                else:
                    cleaned_value = 'Null'  # Or set it to any default value you'd prefer
                final_dict[key] = cleaned_value
            except:
                 cleaned_value = 'Null'
                 final_dict[key] = cleaned_value

        final = { 'status' : "200", 'data' : {'post': final_dict}}
        if('null' in data_string):
            final = { 'status' : "206", 'data' : {'post': final_dict}}
        # final = { 'status' : "200", 'data' : {'post': data_string}}
        # if('null' in data_string):
        #     final = { 'status' : "206", 'data' : {'post': data_string}}
        # Displaying the clean dictionary

        print(final)
        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        final = { 'status' : "500", 'data' : {'post': 'Error- Image Failed to Download'}}
        # Displaying the clean dictionary
        print(e)
        print(traceback_str)

        response = jsonify(final)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


