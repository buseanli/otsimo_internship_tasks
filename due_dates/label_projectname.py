#This script iterates through projects and their issues, checking if each issue has a label with the corresponding project's name. If it doesn't, the script adds the label.
import github_utils
import requests
import logging

# Function to check and add the project name as a label to an issue if it's missing
def check_and_add_project_label(issue:dict, project_name: str, repo_owner:str, repo_name:str, github_token:str):
    #Check if the issue has a label matching the project's name. If not, add the label.
    labels = [label['name'] for label in issue['labels']['nodes']]
    issue_number = issue['number']
    # If the project name is not in the issue's labels, add it
    if project_name not in labels:
        logging.debug(f"Adding label '{project_name}' to issue #{issue_number} in {repo_owner}/{repo_name}")

        # GitHub API URL to add labels to an issue
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}/labels"
        
        headers = {
            'Authorization': f'Bearer {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        # Payload to add the project name as a label
        payload = {
            'labels': [project_name]
        }

        # Send the request to add the label
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            logging.debug(f"Label '{project_name}' successfully added to issue #{issue_number}")
        else:
            logging.debug(f"Failed to add label: {response.status_code}, {response.text}")
    else:
        logging.debug(f"Issue #{issue_number} already has the label '{project_name}'")

def process_issues_for_projects():
    GITHUB_TOKEN = github_utils.github_token
    ORG_NAME = github_utils.org_name

    # Fetch all projects
    projects = github_utils.fetch_projects(ORG_NAME, GITHUB_TOKEN)
    open_project_numbers = []

    # Fetch open projects and process issues
    for project in projects:
        project_details = github_utils.fetch_project_details_by_number(project['number'], ORG_NAME, GITHUB_TOKEN)
        if project_details and not project_details['closed']:
            open_project_numbers.append(project_details['number'])

            # Use the project name as the label we want to check/add to issues
            project_name = project_details['title']

            # Loop through the project items (which are issues)
            for item in project_details['items']['nodes']:
                if 'content' in item and item['content']:
                    issue = item['content']
                    
                    # Get issue-specific details
                    issue_number = issue.get('number')
                    repo_name_with_owner = issue['repository']['nameWithOwner']
                    repo_owner, repo_name = repo_name_with_owner.split('/')

                    # Check if the issue already has the project name as a label
                    labels = [label['name'] for label in issue['labels']['nodes']]
                    if project_name not in labels:
                        # Add the project name as a label to the issue if missing
                        check_and_add_project_label(issue, project_name, repo_owner, repo_name, GITHUB_TOKEN)
                        logging.debug(f'issue label which is {project_name} has been added to {issue_number} in repo {repo_name}')
                    else:
                        logging.debug(f"Issue #{issue_number} already has the label '{project_name}'")

process_issues_for_projects()