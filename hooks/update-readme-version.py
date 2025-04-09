from __future__ import absolute_import
import json
import traceback
from github import Github # pip install PyGithub
from github.InputGitTreeElement import InputGitTreeElement
import os 
import shutil
import time
import subprocess
import sys
from vitality_tools.secrets_manager_tools import get_secrets
import re

my_secrets = get_secrets("vitalitytools", "us-east-1", "prod")

# sys.path.append("..")
from functions import find_between

def color_based_on_percentage(percent_done):
    if percent_done < 70:
        return "red"
    elif percent_done < 90:
        return "yellow"
    else:
        return "green"


def readme_update_version(type:str ='path', versionPath:str = '../version.json', readmePath:str = '../README.md'):
    try:
        # Read the JSON file
        with open(versionPath, "r") as f:
            data = f.read()

        # Increment the patch version
        data = data.strip('""')
        data = data.split(".")
        
        # Converting elements to integers
        data = [int(num) for num in data]

        if type == 'patch':
            major_ver = data[0]
            minor_ver = data[1]
            patch = int(data[2]) + 1
        elif type == 'minor':
            major_ver = data[0]
            minor_ver = data[1] + 1
            patch = 0
        elif type == 'major':
            major_ver = data[0] + 1
            minor_ver = 0
            patch = 0
        else:
            print(" Error- no version update type given ")
            return

        data = str(major_ver) + "." + str(minor_ver) + "." + str(patch)
        # Write the updated JSON file
        with open(versionPath, "w") as f:
            json.dump(data, f, indent=2)
        # Read the readme file
        with open(readmePath, "r") as f:
            text = f.read()

        old_version_badge = find_between(str(text), "<!-- Start Version Badges -->", "<!-- End Version Badges -->")
        badge_output = f"https://img.shields.io/badge/version-{data}-green"
        new_badge = f"\n<img loading='lazy' src='{badge_output}' class='img_ev3q'>\n"
        updated_readme_str = str(text).replace(old_version_badge, new_badge)

        # Write the updated readme file
        with open(readmePath, "w") as f:
            f.write(updated_readme_str)
            print("READme successfully edited")
        return True
    except Exception as e:
        print(e)
        traceback.print_exc()
        print("Something went wrong editing the READme version")
        return False


def update_readme_func_test_count(json_file_path, readme_file_path):
    try:
        # Read the JSON file
        with open(json_file_path, "r") as json_file:
            data = json.load(json_file)

        # Count the number of items with "DONE" status and total number of items
        done_count = sum(1 for value in data.values() if value == "DONE")
        total_count = len(data)

        # Calculate percentage of "DONE" items
        percent_done = (done_count / total_count) * 100 if total_count > 0 else 0

        # Determine color based on percentage
        color = color_based_on_percentage(percent_done)

        # Generate the text variable with color
        text_var = f'functional tests-{done_count}/{total_count} {percent_done:.2f} percent-{color}'

        # Read the README file
        with open(readme_file_path, "r") as readme_file:
            readme_lines = readme_file.readlines()

        # Find the line containing "functional tests"
        for i, line in enumerate(readme_lines):
            if "functional tests" in line:
                readme_lines[i] = f"<img loading='lazy' src='https://img.shields.io/badge/{text_var}' class='img_ev3q'>\n"
                break

        # Write the updated README file
        with open(readme_file_path, "w") as readme_file:
            readme_file.writelines(readme_lines)

        print("README file updated successfully.")
        return True
    except Exception as e:
        print(f"Error updating README file: {e}")
        return False


def push_changes_to_branch(repo_name: str, existing_directory_path: str, target_directory_path: str, branch_name: str, msg: str):
    """
    Create a new branch in a GitHub repository and add files from an existing directory to it.
    
    Args:
        repo_name (str): The name of the GitHub repository.
        existing_directory_path (str): Path to the existing directory containing files to be added.
        target_directory_path (str): Target directory path in the repository where files will be added.
        branch_name (str): Name of the new branch to be created.
        msg (str): The commit message.
    """
    # Check GitHub token exists
    github_token = my_secrets.get('GITHUB_TOKEN', None)
    if github_token is None:
        print("GitHub token not found. Please set the GITHUB_TOKEN environment variable.")
        return

    # Authenticate with GitHub using access token
    g = Github(github_token)

    # Get the repository
    repo = g.get_repo(repo_name)
    print(f'repo found {repo}')

    # Define the source branch name
    source_branch_name = branch_name

    # Check if the source branch exists
    try:
        source_branch = repo.get_branch(source_branch_name)
    except Exception as e:
        print(f"Source branch '{source_branch_name}' not found: {e}")
        return

    # Create a new branch if it doesn't exist already
    try:
        target_branch = repo.get_branch(branch_name)
        print(f"Branch '{branch_name}' already exists.")
    except Exception:
        print(f"Creating new branch '{branch_name}'...")
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source_branch.commit.sha)
        time.sleep(1)
        target_branch = repo.get_branch(branch_name)
        print(f"New branch '{branch_name}' created successfully.")

    # Copy existing directory to a temporary location
    temp_directory_path = '/tmp/temp_directory'
    if os.path.exists(temp_directory_path):
        shutil.rmtree(temp_directory_path)
    shutil.copytree(existing_directory_path, temp_directory_path)

    # Add new files to the repository
    new_files = [os.path.join(temp_directory_path, f) for f in os.listdir(temp_directory_path) if os.path.isfile(os.path.join(temp_directory_path, f))]
    for file_path in new_files:
        #target_directory_path = target_directory_path.replace('../','../')
        with open(file_path, 'rb') as file:
            content = file.read()
            file_name = os.path.basename(file_path)
            # Check if the target directory path exists
            try:
                contents = repo.get_contents(target_directory_path, ref=branch_name)
            except Exception:
                print(f"Creating directory '{target_directory_path}' on branch '{branch_name}'...")
                repo.create_file(path=f"{target_directory_path}/temp.txt", message="Create directory", content=b"", branch=branch_name)
                time.sleep(1)
            try:
                contents = repo.get_contents(os.path.join(target_directory_path, file_name), ref=branch_name)
                # If the file exists, update its content
                repo.update_file(contents.path, msg, content, contents.sha, branch_name)
                print(f"File '{file_name}' updated successfully in '{target_directory_path}' on branch '{branch_name}'")
            except Exception as e:
                # If the file doesn't exist, create it
                try:
                    repo.create_file(os.path.join(target_directory_path, file_name), msg, content, branch=branch_name)
                    print(f"File '{file_name}' created successfully in '{target_directory_path}' on branch '{branch_name}'")
                except Exception as e:
                    print(f"Error creating/updating file '{file_name}' in '{target_directory_path}' on branch '{branch_name}': {e}")
                        
    # Clean up temporary directory
    shutil.rmtree(temp_directory_path)
    print(f"New files added to branch '{branch_name}'.")


def push_files_to_branch(repo_name: str, file_paths: list, branch_name: str, msg: str):
    """
    Create a new branch in a GitHub repository and add files from a list of file paths to it.
    
    Args:
        repo_name (str): The name of the GitHub repository.
        file_paths (list): List of file paths to be added.
        branch_name (str): Name of the new branch to be created.
        msg (str): The commit message.
    """
    # Check GitHub token exists
    github_token = my_secrets.get('GITHUB_TOKEN', None)
    if github_token is None:
        print("GitHub token not found. Please set the GITHUB_TOKEN environment variable.")
        return

    # Authenticate with GitHub using access token
    g = Github(github_token)

    # Get the repository
    repo = g.get_repo(repo_name)
    print(f'Repo found: {repo}')

    # Define the source branch name
    source_branch_name = branch_name

    # Check if the source branch exists
    try:
        source_branch = repo.get_branch(source_branch_name)
    except Exception as e:
        print(f"Source branch '{source_branch_name}' not found: {e}")
        return

    # Create a new branch if it doesn't exist already
    try:
        target_branch = repo.get_branch(branch_name)
        print(f"Branch '{branch_name}' already exists.")
    except Exception:
        print(f"Creating new branch '{branch_name}'...")
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source_branch.commit.sha)
        time.sleep(1)
        target_branch = repo.get_branch(branch_name)
        print(f"New branch '{branch_name}' created successfully.")

    # Add new files to the repository
    for file_path in file_paths:
        with open(file_path, 'rb') as file:
            content = file.read()
            file_name = os.path.basename(file_path)
            # Check if the file exists in the branch
            try:
                contents = repo.get_contents(file_name, ref=branch_name)
                # If the file exists, update its content
                repo.update_file(contents.path, msg, content, contents.sha, branch_name)
                print(f"File '{file_name}' updated successfully on branch '{branch_name}'")
            except Exception as e:
                # If the file doesn't exist, create it
                try:
                    repo.create_file(file_name, msg, content, branch=branch_name)
                    print(f"File '{file_name}' created successfully on branch '{branch_name}'")
                except Exception as e:
                    print(f"Error creating/updating file '{file_name}' on branch '{branch_name}': {e}")


if __name__ == "__main__":
    try:
        repo_name ='Vitality-Robotics-Inc/serverless-app-boilerplate'
        if len(sys.argv) != 5: 
            print("Usage: python3 update-readme-version.py <version_type>")
            sys.exit(1)
        
        version_type = str(sys.argv[1])
        version_path = str(sys.argv[2])
        read_path = str(sys.argv[3])
        branch = str(sys.argv[4])
        target_branch = branch.replace('refs/heads/','')

        # file1 = 'version.json'
        # file2 = 'README.md'
        func_path = 'functional_test_count.json'
        files = [version_path,read_path]
        msg='Update version and README badge'

        readme_update_version(version_type, version_path, read_path)
        update_readme_func_test_count(func_path, read_path)
        push_files_to_branch(repo_name, files, branch, msg)
    except Exception as e:
        print(e)
        traceback.print_exc()



    #LOCAL TESTING
    # file1 = 'version.json'
    # file2 = 'README.md'
    # readme_update_version('patch', file1, file2)
    # files = [file1,file2]

    # repo_name ='Vitality-Robotics-Inc/labtools_api_client'
    # msg='Update version and README badge'
    # folder_path = 'hookas'
    # folder_path_new = 'hookas'
    # #push_changes_to_branch(repo_name, target_branch, msg)
    # #root_directory = './'
    # #push_changes_to_branch(repo_name, root_directory, root_directory, 'add_badges2', msg)
    # push_files_to_branch(repo_name, files, 'add_badges', msg)