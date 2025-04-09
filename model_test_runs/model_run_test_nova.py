import boto3
import json
import logging
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a Bedrock Runtime client in the AWS Region of your choice.
client = boto3.client("bedrock-runtime", region_name="us-east-1")

# Example data
example_not_a_chemical = "125L, Vial Scint 20ML Glass 500/CC"
example_chemical = "N04010, MScn Dp Well Solv. 0.4 µm NS 10PK"

# Generate combined list of chemicals and non-chemicals
chemicals = [{"Number": "N04010", "Part_Description": example_chemical} for _ in range(1)]
not_chemicals = [{"Number": "N04014", "Part_Description": example_not_a_chemical} for _ in range(1)]
combined_list = chemicals + not_chemicals
random.shuffle(combined_list)

# Claude model ID (replace with the correct ID)
MODEL_ID = "us.amazon.nova-lite-v1:0"

# Helper function to clean and parse JSON response
def clean_and_parse_json(response_text):
    # Remove markdown code block markers and any leading/trailing whitespace
    cleaned_text = re.sub(r'^```json\n|```$', '', response_text.strip())
    
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error: {e}")
        logger.error(f"Problematic JSON: {cleaned_text}")
        raise

# Helper function to invoke the model with a single request
def invoke_model_with_response_stream(data_row):
    prompt_text = f"""
    You are an AI trained to identify chemicals based on text descriptions and extract relevant data if present.
    The following is a row from a dataset. Determine if the data has any chemical info in it at all.

    Respond with a structured JSON object with the following fields:

    if it dose not have any Chemical info at all it should just have 
    - row (the input data),
    - prediction ("Chemical" or "Not a Chemical").

    if it has any predict it is a Chemical and needs these
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

    Here is the row:
    {json.dumps(data_row)}

    Respond only with the JSON object.
    """

    # Define system prompt(s)
    system_list = [
        {
            "text": "You are an AI model trained to identify chemicals and extract relevant information."
        }
    ]

    # Define message(s)
    message_list = [
        {
            "role": "user",
            "content": [{"text": prompt_text.strip()}]
        }
    ]

    # Configure inference parameters
    inf_params = {"max_new_tokens": 500, "top_p": 0.9, "top_k": 20, "temperature": 0.7}

    # Prepare request body
    request_body = {
        "schemaVersion": "messages-v1",
        "messages": message_list,
        "system": system_list,
        "inferenceConfig": inf_params,
    }

    # Send request to the model
    try:
        response = client.invoke_model_with_response_stream(
            modelId=MODEL_ID,
            body=json.dumps(request_body)
        )
    except Exception as e:
        logger.error(f"Error invoking model: {e}")
        logger.error(f"Request body: {json.dumps(request_body)}")
        raise

    response_text = ""
    stream = response.get("body")
    if stream:
        for event in stream:
            try:
                chunk = event.get("chunk")
                if chunk:
                    chunk_bytes = chunk.get("bytes")
                    if chunk_bytes:
                        chunk_str = chunk_bytes.decode('utf-8')
                        try:
                            chunk_json = json.loads(chunk_str)
                            content_block_delta = chunk_json.get("contentBlockDelta")
                            if content_block_delta:
                                response_text += content_block_delta.get("delta", {}).get("text", "")
                        except json.JSONDecodeError as je:
                            logger.error(f"JSON Decode Error: {je}")
                            logger.error(f"Problematic chunk: {chunk_str}")
            except Exception as e:
                logger.error(f"Error processing chunk: {e}")

    # Attempt to parse the entire response
    try:
        return clean_and_parse_json(response_text)
    except Exception as e:
        logger.error(f"Failed to parse final response: {response_text}")
        return {
            "row": data_row,
            "error": "Failed to parse model response",
            "raw_response": response_text
        }

# Main function to process all rows and gather results
def process_chemical_data(data_list):
    results = []

    for index, data_row in enumerate(data_list):
        try:
            result = invoke_model_with_response_stream(data_row)
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing row {index}: {e}")
            results.append({"row": data_row, "error": str(e)})

    return {"results": results}

# AWS Lambda handler function
def lambda_handler(event, context):
    start_time = time.time()  # Record start time
    
    result = process_chemical_data(combined_list)
    
    end_time = time.time()  # Record end time
    elapsed_time = end_time - start_time  # Calculate elapsed time

    # Log the result and processing time
    print(json.dumps(result, indent=4))
    print(f"Processing time: {elapsed_time:.2f} seconds")

    # Return response with processing time as a separate value
    return {
        'statusCode': 200,
        'body': json.dumps(result, indent=4),
        'processingTimeSeconds': round(elapsed_time, 2)
    }

if __name__ == "__main__":
    event = ""
    lambda_handler(event, context=None)