#This script is used to get environment variables from terminal
import os
import argparse

def get_tokens():
    parser = argparse.ArgumentParser(description="Process tokens for GitHub, Slack, Authorization, and Org Name.")
    
    # Add the arguments, including the new one for org_name
    parser.add_argument('--github-token', default=os.environ.get('GITHUB_TOKEN'), help='GitHub API token')
    parser.add_argument('--slack-bot-token', default=os.environ.get('SLACK_BOT_TOKEN'), help='Slack Bot token')
    parser.add_argument('--auth-token', default=os.environ.get('AUTH_TOKEN'), help='Authorization token')
    parser.add_argument('--org-name', default=os.environ.get('ORG_NAME'), help='Organization name')

    # Parse arguments
    args = parser.parse_args()

    # Return the tokens and the org name
    return args.github_token, args.slack_bot_token, args.auth_token, args.org_name
