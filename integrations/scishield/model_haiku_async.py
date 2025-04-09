import boto3
import json
import logging
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import botocore.config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure boto3 client with a larger connection pool
config = botocore.config.Config(max_pool_connections=50)
client = boto3.client("bedrock-runtime", region_name="us-east-1", config=config)

# Replace MODEL_ID with the inference profile ARN
MODEL_ID = "arn:aws:bedrock:us-east-1:961341512141:inference-profile/us.anthropic.claude-3-5-haiku-20241022-v1:0"

# Example data
example_not_a_chemical = "125L, Vial Scint 20ML Glass 500/CC"
example_chemical = "N04010, MScn Dp Well Solv. 0.4 µm NS 10PK"

# Generate combined list of chemicals and non-chemicals
chemicals = [{"Number": "N04010", "Part_Description": example_chemical} for _ in range(500)]
not_chemicals = [{"Number": "N04014", "Part_Description": example_not_a_chemical} for _ in range(500)]
combined_list = chemicals + not_chemicals
random.shuffle(combined_list)

# Helper function to clean and parse JSON response
def clean_and_parse_json(response_text):
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error: {e}")
        logger.error(f"Problematic JSON: {response_text}")
        return {"error": f"JSON Decode Error: {e}", "response": response_text}

async def invoke_with_retries(request_body, max_retries=2):
    """
    Invoke the model with exponential backoff and jitter.
    """
    for attempt in range(max_retries):
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.invoke_model(
                    modelId=MODEL_ID,
                    body=request_body,
                    contentType="application/json",
                    accept="application/json"
                )
            )
            response_body = json.loads(response['body'].read().decode('utf-8'))
            content = response_body.get('content', [{}])[0].get('text', '')
            return clean_and_parse_json(content)
        except Exception as e:
            if "ThrottlingException" in str(e):
                sleep_time = min(2 ** attempt + random.uniform(0, 0.5), 60)  # Cap at 60 seconds
                logger.warning(f"Throttling detected. Retrying in {sleep_time:.2f} seconds...")
                await asyncio.sleep(sleep_time)
            else:
                logger.error(f"Error invoking model: {e}")
                return {"error": str(e)}

async def invoke_model_async(batch):
    """
    Asynchronous function to invoke the Bedrock model with a batch of data.
    """
    # Combine rows into a single JSON structure for the batch
    prompt_text = f"""
    You are an AI trained to identify chemicals based on text descriptions and extract relevant data if present.
    The following is a batch of rows from a dataset. For each row, determine if the data has any chemical info at all.

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

    request_body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8000,
        "messages": [
            {"role": "user", "content": prompt_text.strip()}
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 20
    })

    # Use the existing invoke_with_retries logic
    return await invoke_with_retries(request_body)

async def process_batches(data_list, batch_size=50):
    """
    Processes data in batches, combining rows into a single payload for each batch.
    """
    # Break data_list into batches
    batches = [data_list[i:i + batch_size] for i in range(0, len(data_list), batch_size)]

    tasks = [invoke_model_async(batch) for batch in batches]

    # Gather results asynchronously
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

def haiku_process_chemical_data(data_list):
    """
    Processes all data by sending it in batches and collecting the results.
    """
    results = asyncio.run(process_batches(data_list))
    return {"results": results}

# AWS Lambda handler function
def lambda_handler(event, context):
    start_time = time.time()  # Record start time

    result = haiku_process_chemical_data(combined_list)
    end_time = time.time()  # Record end time
    elapsed_time = end_time - start_time  # Calculate elapsed time

    # Log the result and processing time
    logger.info(json.dumps(result, indent=4))
    logger.info(f"Processing time: {elapsed_time:.2f} seconds")

    # Return response with processing time as a separate value
    return {
        'statusCode': 200,
        'body': json.dumps(result, indent=4),
        'processingTimeSeconds': round(elapsed_time, 2)
    }

if __name__ == "__main__":
    event = ""
    lambda_handler(event, context=None)
