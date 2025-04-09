import boto3
import json
import logging
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time
import random
import asyncio
import botocore.config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure boto3 client with a larger connection pool
config = botocore.config.Config(max_pool_connections=50)
client = boto3.client("bedrock-runtime", region_name="us-east-1", config=config)

# Example data
example_not_a_chemical = "125L, Vial Scint 20ML Glass 500/CC"
example_chemical = "N04010, MScn Dp Well Solv. 0.4 µm NS 10PK"

# Generate combined list of chemicals and non-chemicals
chemicals = [{"Number": "N04010", "Part_Description": example_chemical} for _ in range(50)]
not_chemicals = [{"Number": "N04014", "Part_Description": example_not_a_chemical} for _ in range(50)]
combined_list = chemicals + not_chemicals
random.shuffle(combined_list)

# Nova model ID (replace with the correct ID)
MODEL_ID = "us.amazon.nova-lite-v1:0"

# Helper function to clean and parse JSON response
def clean_and_parse_json(response_text):
    cleaned_text = re.sub(r'^```json\n|```$', '', response_text.strip())
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error: {e}")
        logger.error(f"Problematic JSON: {cleaned_text}")
        return {"error": f"JSON Decode Error: {e}", "response": cleaned_text}

def invoke_model_sync(data_row):
    """
    Synchronous function to invoke the Nova model for a single row.
    """
    prompt_text = f"""
    You are an AI trained to identify chemicals based on text descriptions and extract relevant data if present.
    The following is a row from a dataset. Determine if the data has any chemical info in it at all.

    Respond with a structured JSON object with the following fields:

    if it does not have any chemical info at all, it should just have:
    - row (the input data),
    - prediction ("Chemical" or "Not a Chemical").

    if it has any, predict it is a chemical and include these fields:
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

    # Prepare request body
    request_body = {
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt_text.strip()}]
            }
        ],
        "system": [
            {"text": "You are an AI model trained to identify chemicals and extract relevant information."}
        ],
        "inferenceConfig": {
            "max_new_tokens": 4000,
            "top_p": 0.9,
            "top_k": 20,
            "temperature": 0.7
        }
    }

    retries = 5  # Number of retries
    for attempt in range(retries):
        try:
            response = client.invoke_model_with_response_stream(
                modelId=MODEL_ID,
                body=json.dumps(request_body)
            )
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
                                chunk_json = json.loads(chunk_str)
                                content_block_delta = chunk_json.get("contentBlockDelta")
                                if content_block_delta:
                                    response_text += content_block_delta.get("delta", {}).get("text", "")
                    except json.JSONDecodeError as je:
                        logger.error(f"JSON Decode Error: {je}")
                        logger.error(f"Problematic chunk: {chunk_str}")
            return clean_and_parse_json(response_text)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < retries - 1:
                sleep_time = 2 ** attempt  # Exponential backoff
                time.sleep(sleep_time)
            else:
                logger.error(f"Error invoking model: {e}")
                return {"row": data_row, "error": str(e)}

async def invoke_model_batch(batch):
    """
    Asynchronous function to invoke the Nova model with a batch of data.
    """
    # Combine rows into a single JSON structure for the batch
    prompt_text = f"""
    You are an AI trained to identify chemicals based on text descriptions and extract relevant data if present.
    The following is a batch of rows from a dataset. For each row, determine if the data has any chemical info in it at all.

    Respond with a structured JSON array where each object corresponds to one row in the batch.
    Each object should have the following fields:

    if it does not have any chemical info at all, it should just have:
    - row (the input data),
    - prediction ("Chemical" or "Not a Chemical").

    if it has any, predict it is a chemical and include these fields:
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

    Here is the batch:
    {json.dumps(batch)}

    Respond only with the JSON array.
    """

    # Prepare request body
    request_body = {
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt_text.strip()}]
            }
        ],
        "system": [
            {"text": "You are an AI model trained to identify chemicals and extract relevant information."}
        ],
        "inferenceConfig": {
            "max_new_tokens": 5000,
            "top_p": 0.9,
            "top_k": 20,
            "temperature": 0.7
        }
    }

    retries = 2  # Number of retries
    for attempt in range(retries):
        try:
            response = client.invoke_model_with_response_stream(
                modelId=MODEL_ID,
                body=json.dumps(request_body)
            )
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
                                chunk_json = json.loads(chunk_str)
                                content_block_delta = chunk_json.get("contentBlockDelta")
                                if content_block_delta:
                                    response_text += content_block_delta.get("delta", {}).get("text", "")
                    except json.JSONDecodeError as je:
                        logger.error(f"JSON Decode Error: {je}")
                        logger.error(f"Problematic chunk: {chunk_str}")
            return clean_and_parse_json(response_text)
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < retries - 1:
                sleep_time = 2 ** attempt  # Exponential backoff
                time.sleep(sleep_time)
            else:
                logger.error(f"Error invoking model: {e}")
                return {"batch": batch, "error": str(e)}

async def process_batches(data_list, batch_size=50):
    """
    Processes data in batches, combining rows into a single payload for each batch.
    """
    # Break data_list into batches
    batches = [data_list[i:i + batch_size] for i in range(0, len(data_list), batch_size)]

    tasks = [invoke_model_batch(batch) for batch in batches]

    # Gather results asynchronously
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

def nova_process_chemical_data(data_list):
    """
    Processes all data by sending it in batches and collecting the results.
    """
    results = asyncio.run(process_batches(data_list))
    return {"results": results}

# AWS Lambda handler function
def lambda_handler(event, context):
    start_time = time.time()  # Record start time

    result = nova_process_chemical_data(combined_list)

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
