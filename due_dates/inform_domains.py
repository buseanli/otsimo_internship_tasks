import os
import re
import requests
import json
import github_utils
import logging

# Function to fetch and list issues without 'Domain' field
def list_issues_without_domain(project_number: int, org_name: str, github_token: str) -> list:
    #Fetch all issues from the project and list those without a 'Domain' field.
    project_items = github_utils.fetch_all_project_items(project_number, org_name, github_token)
    issues_without_domain = []

    for item in project_items:
        content = item.get('content')
        if content and 'title' in content and 'number' in content:
            title = content['title']
            number = content['number']
            labels = [label['name'] for label in content['labels']['nodes']]
            repository = content['repository']['nameWithOwner'].split('/')
            owner = repository[0]
            repo = repository[1]
            author_login = content['author']['login']

            has_domain = False

            # Iterate over the field values to check for the 'Domain' field
            for field in item.get('fieldValues', {}).get('nodes', []):
                field_name = field.get('field', {}).get('name', '')
                if field_name == "Domain":
                    has_domain = True
                    break  # Stop if 'Domain' field is found

            # If there's no 'Domain' field, add the issue to the list
            if not has_domain:
                issues_without_domain.append({
                    'owner': owner,
                    'repo': repo,
                    'number': number,
                    'title': title,
                    'author_login': author_login
                })

    return issues_without_domain

# Function to send a message to Slack
def send_slack_message(user_id, link, issuenumber, title):
    #Send a message to a Slack user reminding them to add a 'Domain' field to an issue.
    message_template = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    #CHANGE THAT
                    "text": ":rotating_light: Hey <@{user_id}>, \n Heads up, you forgot to add the 'Domain' field to issue #{issuenumber} <{link}|{title}>"
                }
            }
        ]
    }

    # Replace placeholders with actual values
    message_text = message_template['blocks'][0]['text']['text']
    message_template['blocks'][0]['text']['text'] = message_text.format(
        user_id=user_id, link=link, issuenumber=issuenumber, title=title
    )
    
    SLACK_BOT_TOKEN = github_utils.slack_bot_token

    # Set the API endpoint and headers
    url = 'https://slack.com/api/chat.postMessage'
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}'
    }

    # Create the payload
    payload = {
        'channel': user_id,  # Use the user ID directly
        'blocks': message_template['blocks']
    }

    # Send the message
    response = requests.post(url, headers=headers, data=json.dumps(payload))

    # Check the response
    if response.status_code == 200:
        response_data = response.json()
        if response_data.get('ok'):
            print('Message sent successfully!')
        else:
            print(f"Error: {response_data.get('error')}")
    else:
        print(f'Failed to send message: {response.text}')

# Main function
def main():
    """
    Main function to list issues without 'Domain' field and send Slack messages.
    """
    # Fetch user data from Otsimo API
    url = "https://apis.otsimo.com/api/v1/yoshi/listusers"
    headers = {
        "Authorization": github_utils.auth_token
    }
    response = requests.get(url, headers=headers)
    users_data = response.json()['users']

    GITHUB_TOKEN = github_utils.github_token
    ORG_NAME = github_utils.org_name

    # Fetch open projects
    projects = github_utils.fetch_projects(ORG_NAME, GITHUB_TOKEN)
    open_project_numbers = []

    for project in projects:
        project_details = github_utils.fetch_project_details(project['id'], GITHUB_TOKEN)
        if project_details and not project_details['closed']:
            open_project_numbers.append(project_details['number'])

    # List issues without 'Domain' fields and send Slack messages
    for project_number in open_project_numbers:
        issues_without_domain = list_issues_without_domain(project_number, ORG_NAME, GITHUB_TOKEN)
        for issue in issues_without_domain:
            issue_number = issue['number']
            title = issue['title']
            repo = issue['repo']
            author = issue['author_login']

            # Find the Slack user ID for the issue author
            for user in users_data:
                if user['githubName'] == author:
                    #USER_ID = user['slackUserId']
                    USER_ID = 'U07DMT2F54J'
                    issue_url = f'https://github.com/{ORG_NAME}/{repo}/issues/{issue_number}'
                    
                    # Send a Slack message
                    send_slack_message(USER_ID, issue_url, issue_number, title)
                    break

# Run the main function
if __name__ == "__main__":
    main()
