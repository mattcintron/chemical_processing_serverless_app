import boto3
import json
import logging
import random
import asyncio
import botocore.config
from datetime import datetime
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure boto3 client with a larger connection pool
config = botocore.config.Config(max_pool_connections=50)
client = boto3.client("bedrock-runtime", region_name="us-east-1", config=config)

# Replace MODEL_ID with your Nova model ARN
MODEL_ID = "us.amazon.nova-lite-v1:0"

# Example data
example_not_a_chemical = "125L, Vial Scint 20ML Glass 500/CC"
example_chemical = "N04010, MScn Dp Well Solv. 0.4 µm NS 10PK"

# Generate combined list of chemicals and non-chemicals
chemicals = [{"Number": "N04010", "Part_Description": example_chemical} for _ in range(500)]
not_chemicals = [{"Number": "N04014", "Part_Description": example_not_a_chemical} for _ in range(500)]
combined_list = chemicals + not_chemicals
random.shuffle(combined_list)


def construct_request_payload(prompt_text):
    """
    Constructs the request payload for invoking the Nova model.
    """
    system_prompts = [
        {
            "text": '''
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

        Respond only with the JSON array.
        '''
        }
    ]
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "text": prompt_text
                }
            ]
        }
    ]

    inference_parameters = {
        "max_new_tokens": 50,
        "top_p": 0.9,
        "top_k": 20,
        "temperature": 0.7
    }

    return {
        "schemaVersion": "messages-v1",
        "messages": messages,
        "system": system_prompts,
        "inferenceConfig": inference_parameters,
    }


async def invoke_model_async(prompt_text, max_retries=3):
    """
    Asynchronous function to invoke the Bedrock model.
    """
    request_payload = construct_request_payload(prompt_text)

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

            response_body = json.loads(response['body'].read())

            # Extract the model's response
            if 'output' in response_body and 'message' in response_body['output']:
                content = response_body['output']['message']['content']
                if content and 'text' in content[0]:
                    return content[0]['text']
                else:
                    return "No valid text content found in the response."
            else:
                return {"error": "Invalid response structure", "response": response_body}

        except Exception as e:
            if "ThrottlingException" in str(e):
                sleep_time = min(2 ** attempt + random.uniform(0, 0.5), 60)
                await asyncio.sleep(sleep_time)
            else:
                logger.error(f"Error invoking model: {e}")
                return {"error": str(e)}


async def process_batches(data_list, batch_size=50):
    """
    Processes data in batches, combining rows into a single payload for each batch.
    """
    batches = [data_list[i:i + batch_size] for i in range(0, len(data_list), batch_size)]
    tasks = [invoke_model_async("\n".join(item["Part_Description"] for item in batch)) for batch in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


def nova_process_chemical_data(data_list):
    """
    Processes all data by sending it in batches and collecting the results.
    """
    results = asyncio.run(process_batches(data_list))
    return results


def lambda_handler(event, context):
    start_time = time.time()
    final_results = nova_process_chemical_data(combined_list)
    end_time = time.time()
    elapsed_time = end_time - start_time

    logger.info(f"Processing time: {elapsed_time:.2f} seconds")
    logger.info("Final Results:")  # Only log the final results once
    logger.info(json.dumps(final_results, indent=4))

    return {
        'statusCode': 200,
        'body': json.dumps({"results": final_results}, indent=4),
        'processingTimeSeconds': round(elapsed_time, 2)
    }


if __name__ == "__main__":
    lambda_handler(None, None)