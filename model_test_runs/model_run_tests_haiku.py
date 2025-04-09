import boto3
import json
import logging
import random
import time

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

# Replace MODEL_ID with the inference profile ARN
MODEL_ID = "arn:aws:bedrock:us-east-1:961341512141:inference-profile/us.anthropic.claude-3-5-haiku-20241022-v1:0"

# Helper function to clean and parse JSON response
def clean_and_parse_json(response_text):
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error: {e}")
        logger.error(f"Problematic JSON: {response_text}")
        raise

def invoke_model(data_row):
    """
    Invokes the model using on-demand inference with an inference profile.
    """
    prompt_text = f"""
    You are an AI trained to identify chemicals based on text descriptions and extract relevant data if present.
    The following is a row from a dataset. Determine if the data has any chemical info at all.

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
    request_body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "messages": [
            {
                "role": "user",
                "content": prompt_text.strip()
            }
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 20
    })

    # Send request to the model
    try:
        response = client.invoke_model(
            modelId=MODEL_ID,
            body=request_body,
            contentType="application/json",
            accept="application/json"
        )

        response_body = json.loads(response['body'].read().decode('utf-8'))

        # Extract the content from the response
        content = response_body.get('content', [{}])[0].get('text', '')

        return clean_and_parse_json(content)
    except Exception as e:
        logger.error(f"Error invoking model: {e}")
        raise

# Main function to process all rows and gather results
def process_chemical_data(data_list):
    results = []

    for index, data_row in enumerate(data_list):
        try:
            result = invoke_model(data_row)
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
