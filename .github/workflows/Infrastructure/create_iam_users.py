import boto3
from botocore.exceptions import ClientError

def create_iam_user_with_admin_role_and_tags(user_name):
    # Create IAM client
    iam_client = boto3.client('iam')
    
    # Define the tags for the user
    tags = [
        {'Key': 'environment', 'Value': 'development'},  # Change to 'production' as needed
        {'Key': 'user', 'Value': 'matt@vitalityrobotics.com'},
        {'Key': 'project', 'Value': 'scishield-chemsnap'},
        {'Key': 'lifecycle', 'Value': 'active'},
        {'Key': 'team', 'Value': 'vitality'}
    ]
    
    try:
        # Create the IAM user
        print(f"Creating IAM user: {user_name}")
        iam_client.create_user(UserName=user_name)

        # Attach the AWS-managed Admin policy to the user
        print(f"Attaching Admin policy to the user: {user_name}")
        iam_client.attach_user_policy(
            UserName=user_name,
            PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess'
        )

        # Add tags to the IAM user
        print(f"Adding tags to user: {user_name}")
        iam_client.tag_user(
            UserName=user_name,
            Tags=tags
        )
        
        print(f"User {user_name} created successfully, Admin role attached, and tags added.")
    
    except ClientError as e:
        print(f"Error occurred: {e}")
        return None

    return user_name

if __name__ == '__main__':
    user_name = input("Enter the IAM username to create: ")
    create_iam_user_with_admin_role_and_tags(user_name)







