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
import csv
import asyncio
import botocore.config
import logging
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")  # Replace with your AWS region
runtime = boto3.client("bedrock-runtime","us-east-1")
my_secrets = get_secrets("labtools-dev", "us-east-1", "dev")

# Create a Blueprint for your SciShield routes
scishield_bp2 = Blueprint("chemical_classification", __name__)

# OpenAI API Key
#api_key = my_secrets.get('OPEN_AI_API_KEY', None)
api_key = my_secrets.get('OPEN_AI_API_KEY', None)
product_key = my_secrets.get('PRODUCT_KEY', None)
openai.api_key = api_key


# Configure boto3 client with a larger connection pool
config = botocore.config.Config(max_pool_connections=50)
client = boto3.client("bedrock-runtime", region_name="us-east-1", config=config)


# MODEL_ID = Nova model ARN
# MODEL_ID = "us.amazon.nova-micro-v1:0"
MODEL_ID = "us.amazon.nova-lite-v1:0"


# Central Route Methods - 
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


async def invoke_nova_model_async(
    batch: List, client: object, max_retries: int = 3) -> List:
    """
    Asynchronously invokes the Nova Lite model to classify and extract chemical information from a batch of data rows.

    Args:
        batch: A list of dictionaries where each dictionary represents a data row to be processed.
        client: The Nova client instance used to make model invocation requests.
        max_retries: Maximum number of retry attempts for failed requests (default: 3).

    Returns:
        A list of dictionaries containing the processed results for each input row. Each result includes:
        - The original row data
        - A chemical classification prediction
        - Extracted chemical information fields (if applicable)
        - Error messages (if processing failed)

    Raises:
        json.JSONDecodeError: If the model response cannot be parsed as JSON.
        Exception: For other unexpected errors during processing.

    Notes:
        - Implements exponential backoff with jitter for retrying throttled requests.
        - Processes the model response to remove Markdown formatting (```json```).
        - Returns error information in the prediction field if processing fails.
        - The system prompt defines the exact output schema expected from the model.
    """
    prompt_text = "\n".join(json.dumps(row) for row in batch)
    request_payload = {
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"text": prompt_text}
                ]
            }
        ],
        "system": [
            {
                "text": """
                    You are an AI trained to identify chemicals based on text descriptions and extract relevant data if present.
                    The following is a batch of rows from a dataset. For each determine if the data has any chemical info at all.

                    Respond with a structured JSON array where each object corresponds to one row in the batch.
                    Each object should have the following fields:

                    if your prediction is not chemical, it should just have:
                    - row (the input data),
                    - prediction ("Chemical" or "Not a Chemical").

                    if it is a chemical then build and include all these fields as best you can:
                    - row (the input data),
                    - prediction ("Chemical" or "Not a Chemical"),
                    - Confidence score (a 4-digit decimal between 0.000 and 1.000),
                    - CAS number (if present in row, else null),
                    - Lot Number (if present in row, else null),
                    - Manufacturer (if present in row, else null),
                    - Quantity (if present in row, else null),
                    - Chemical Name (if present in row, else null),
                    - Product Name (if present in row, else null),
                    - Product Number (if present in row, else null),
                    - Units (if present in row, else null).

                    Respond only with the JSON array.
                """
            }
        ],
        "inferenceConfig": {
            "max_new_tokens": 4000,
            "top_p": 0.9,
            "top_k": 20,
            "temperature": 0.7
        }
    }

    for attempt in range(max_retries):
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.invoke_model(
                    modelId=MODEL_ID,
                    body=json.dumps(request_payload),
                    contentType="application/json",
                    accept="application/json"
                )
            )

            response_body = json.loads(response["body"].read())
            if "output" in response_body and "message" in response_body["output"]:
                content = response_body["output"]["message"]["content"]
                if content and "text" in content[0]:
                    raw_text = content[0]["text"]
                    # Remove possible triple backticks and language hints (e.g., ```json ... ```)
                    cleaned_text = raw_text.strip().strip("```").replace("json\n", "").replace("\n```", "")
                    return json.loads(cleaned_text)
                else:
                    return [{"row": row, "prediction": "No valid text content found in the response."} for row in batch]
            else:
                return [{"row": row, "prediction": "Invalid response structure"} for row in batch]

        except Exception as e:
            if "ThrottlingException" in str(e):
                sleep_time = min(2 ** attempt + random.uniform(0, 0.5), 60)
                await asyncio.sleep(sleep_time)
            else:
                logger.error(f"Error invoking model: {e}")
                return [{"row": row, "prediction": f"Error: {str(e)}"} for row in batch]

    return [{"row": row, "prediction": "Max retries exceeded"} for row in batch]


#swagger docs
@scishield_bp2.route('/docs', methods=['GET', 'POST'])
def scishield_swagger() -> str:
    """
    Serve the Swagger UI documentation page for SciShield API (version 2).

    Returns:
        str: Rendered HTML template for Swagger UI with the OpenAPI specification URL.

    Notes:
        - This endpoint serves both GET and POST requests
        - Displays the Swagger UI interface configured with the SciShield OpenAPI specification
        - Uses a different YAML file (scishield_swagger2.yaml) than the primary endpoint
    """
    openapi_url = url_for('static', filename='swagger/scishield/scishield_swagger2.yaml')
    return render_template('swaggerui.html', openapi_url=openapi_url)


@scishield_bp2.route("/predict-chemicals-upload", methods=["POST"])
def predict_chemicals_upload() -> Tuple:
    """
    Process an uploaded CSV file to predict chemical information in batches using Nova model.

    Args:
        org (str): Organization identifier from form data
        api_key (str): API key from form data for authentication
        file (FileStorage): Uploaded CSV file from form data

    Returns:
        Tuple[Response, int]: A tuple containing:
            - Flask Response with JSON data
            - HTTP status code

    Notes:
        - Validates API key and file type (.csv)
        - Processes CSV in batches of 10 rows
        - Uses async processing with 1-second delay between batches
        - Returns flattened predictions for all rows

    Response Status Codes:
        - 200: Success with predictions
        - 400: Invalid CSV file or empty file
        - 500: Server error or invalid API key
    """
    try:
        # Extract fields from the form data
        org = request.form.get("org")
        api_key = request.form.get("api_key")
        uploaded_file = request.files.get("file")

        if api_key != 'labtools_1273d72650af':
            return jsonify({"status": "500", "data": {"post": "Error- API Key is Invalid"}}), 500

        if not uploaded_file or not uploaded_file.filename.endswith(".csv"):
            return jsonify({"error": "A valid CSV file is required"}), 400

        # Save the uploaded file to a temporary location
        local_path = f"/tmp/{uploaded_file.filename}"
        uploaded_file.save(local_path)

        # Read the CSV file
        rows = []
        with open(local_path, newline="") as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)  # Assume the first row is the header
            for row in reader:
                rows.append(row)

        if not rows:
            return jsonify({"error": "The CSV file is empty"}), 400

        # Define batch size
        batch_size = 10
        batches = [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]

        async def process_batches():
            results = []
            for index, batch in enumerate(batches):
                if index > 0:
                    await asyncio.sleep(1)  # Sleep 1 second between batch invocations
                result = await invoke_nova_model_async(batch, client)
                results.append(result)
            return results

        predictions = asyncio.run(process_batches())

        # Flatten the results
        flattened_predictions = [item for sublist in predictions for item in sublist]

        return jsonify({"predictions": flattened_predictions})

    except Exception as e:
        logger.error(f"Error in processing request: {str(e)}")
        return jsonify({"error": str(e)}), 500


@scishield_bp2.route("/predict-chemicals-json", methods=["POST"])
def predict_chemicals_json() -> Tuple:
    """
    Process JSON input to predict chemical information in batches using Nova model.

    Args:
        org (str): Organization identifier from JSON payload
        api_key (str): API key from JSON payload for authentication
        rows (List[Dict[str, Any]]): List of data rows to process from JSON payload

    Returns:
        Tuple[Response, int]: A tuple containing:
            - Flask Response with JSON data
            - HTTP status code

    Notes:
        - Requires valid API key ('labtools_1273d72650af')
        - Processes data in batches of 10 rows
        - Uses async processing with 1-second delay between batches
        - Returns flattened predictions for all rows
        - Sets CORS headers for cross-origin requests

    Response Status Codes:
        - 200: Success with predictions
        - 400: Missing required fields or invalid input format
        - 500: Server error or processing failure

    Example Request:
        POST /predict-chemicals-json
        {
            "org": "example-org",
            "api_key": "labtools_1273d72650af",
            "rows": [
                {"field1": "value1", ...},
                {"field2": "value2", ...}
            ]
        }
    """
    try:
        data = request.json
        org = data.get("org")
        api_key = data.get("api_key")
        rows = data.get("rows")

        if api_key != 'labtools_1273d72650af':
            final = {'status': "500", 'data': {'post': 'Error- API Key is Invalid'}}
            response = jsonify(final)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        if not org or not api_key:
            return jsonify({"error": "org and api_key are required"}), 400

        if not rows or not isinstance(rows, list):
            return jsonify({"error": "A valid list of rows is required"}), 400

        # Process rows in batches asynchronously
        batch_size = 10
        batches = [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]

        async def process_batches():
            results = []
            for index, batch in enumerate(batches):
                if index > 0:
                    await asyncio.sleep(1)  # Sleep 1 second between batch invocations
                result = await invoke_nova_model_async(batch, client)
                results.append(result)
            return results

        predictions = asyncio.run(process_batches())

        # Flatten the results
        flattened_predictions = [item for sublist in predictions for item in sublist]

        return jsonify({"predictions": flattened_predictions})

    except Exception as e:
        logger.error(f"Error in processing request: {str(e)}")
        return jsonify({"error": str(e)}), 500
