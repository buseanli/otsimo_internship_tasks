#This script lists issues without due dates and sends a Slack message to the authors notifying them the issue has no due date.
import os
import re
import requests
import json
import github_utils
import logging

def list_issues_without_due_dates():
    GITHUB_TOKEN = github_utils.github_token
    ORG_NAME = github_utils.org_name
    projects = github_utils.fetch_projects(ORG_NAME, GITHUB_TOKEN)
    open_projects = []
    open_project_numbers = []
    
    for project in projects:
        project_details = github_utils.fetch_project_details(project['id'], GITHUB_TOKEN)
        if project_details and not project_details['closed']:
            open_projects.append(project_details)
            open_project_numbers.append(project_details['number'])
    
    if open_projects:
        logging.debug("Open Projects:")
        for project in open_projects:
            logging.debug(f"- Project Number: {project['number']}, Project Name: {project['title']}")
    else:
        logging.debug("No open projects found.")

    logging.debug("Open Project Numbers: " + str(open_project_numbers))

    #List issues without due dates for all open projects
    for project_number in open_project_numbers:
        logging.debug(f"\nListing issues without due dates for project number {project_number}:")
        issues_without_due_dates = github_utils.list_issues_without_due_dates(project_number, ORG_NAME, GITHUB_TOKEN)
        if issues_without_due_dates:
            for issue in issues_without_due_dates:
                logging.debug(f"- Issue #{issue['number']} in {issue['owner']}/{issue['repo']}: {issue['title']}")
                logging.debug(f"  Owner Login: {issue['author_login']}")
        else:
            logging.debug("No issues without due dates found.")
# Function to send a message to Slack
def send_slack_message(user_id: str, link: str, issuenumber: int, title: str):
    # Message template
    message_template = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":alarm_clock:  <@{user_id}> \n Beep-boop, you forgot to add the due date to the issue, #{issuenumber}  <{link}| {title}>"
                }
            }
        ]
    }

    # Replace placeholders with actual values
    message_text = message_template['blocks'][0]['text']['text']
    message_template['blocks'][0]['text']['text'] = message_text.format(user_id=user_id, link=link,issuenumber=issuenumber, title=title)
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

def main():

    url = "https://apis.otsimo.com/api/v1/yoshi/listusers"
    headers = {
        "Authorization": github_utils.auth_token
    }

    response = requests.request("GET", url, headers=headers)
    data = list(response.json()['users'])

    GITHUB_TOKEN = github_utils.github_token
    ORG_NAME = github_utils.org_name
    projects = github_utils.fetch_projects(ORG_NAME, GITHUB_TOKEN)
    open_projects = []
    open_project_numbers = []

    for project in projects:
        project_details = github_utils.fetch_project_details(project['id'], GITHUB_TOKEN)
        if project_details and not project_details['closed']:
            open_projects.append(project_details)
            open_project_numbers.append(project_details['number'])

    for i in range(0,len(open_project_numbers)):
        issues_without_due_dates = list_issues_without_due_dates(open_project_numbers[i], ORG_NAME, GITHUB_TOKEN)
        for issue in issues_without_due_dates:
            issue_number = issue['number']
            title = issue['title']
            repo = issue['repo']
            author = issue['author_login']
            for user in data:
                if user['githubName'] == author:
                    USER_ID = user['slackUserId']
                    issue_url = f'https://github.com/{ORG_NAME}/{repo}/issues/{issue_number}'
                    send_slack_message(USER_ID, issue_url,issue_number, title)
        
    

main()