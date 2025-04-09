import boto3
import json
from datetime import datetime

# Initialize the Bedrock Runtime client for the desired AWS region
client = boto3.client("bedrock-runtime", region_name="us-east-1")

# Specify the model ID for Amazon Nova Lite
MODEL_ID = "us.amazon.nova-lite-v1:0"

# Define system prompts to guide the model's behavior
system_prompts = [
    {
        "text": "You are a creative writing assistant. When the user provides a topic, craft a short story based on that topic."
    }
]

# Create a list of messages representing the conversation history
messages = [
    {
        "role": "user",
        "content": [
            {
                "text": "A camping trip"
            }
        ]
    }
]

# Set inference parameters to control the model's output
inference_parameters = {
    "max_new_tokens": 500,
    "top_p": 0.9,
    "top_k": 20,
    "temperature": 0.7
}

# Construct the request payload
request_payload = {
    "schemaVersion": "messages-v1",
    "messages": messages,
    "system": system_prompts,
    "inferenceConfig": inference_parameters,
}

# Record the start time to measure response latency
start_time = datetime.now()

# Invoke the model and retrieve the response
response = client.invoke_model(
    modelId=MODEL_ID,
    body=json.dumps(request_payload)
)

# Extract the response body
response_body = json.loads(response['body'].read())

# Calculate the time taken to receive the response
time_to_response = datetime.now() - start_time

# Display the request ID and response time
request_id = response.get("ResponseMetadata", {}).get("RequestId", "N/A")
print(f"Request ID: {request_id}")
print(f"Time to response: {time_to_response}")

# Output the model's response
if 'output' in response_body and 'message' in response_body['output']:
    content = response_body['output']['message']['content']
    if content and 'text' in content[0]:
        print("\nModel Response:")
        print(content[0]['text'])
    else:
        print("No text content found in the response.")
else:
    print("Invalid response structure.")