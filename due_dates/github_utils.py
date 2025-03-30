#In this script, there are some required functions for other scripts implemented
import os
import requests
import json
import re
from datetime import datetime
import logging
from script import get_tokens

# Get the tokens by calling the helper function
github_token, slack_bot_token, auth_token, org_name = get_tokens()

logging.basicConfig(
    filename="github_duedate_controller.log",
    level=logging.DEBUG,
    format="%(asctime)s:%(levelname)s:%(message)s"
)

GITHUB_API_URL = 'https://api.github.com/graphql'

# GraphQL query to fetch projects
def get_query_projects(org_name:str):
    return """
{
  organization(login: "%s") {
    projectsV2(first: 100) {
      nodes {
        id
        title
        number
      }
    }
  }
}
""" % org_name

# GraphQL query to fetch project details
query_project_details = """
query($id: ID!) {
  node(id: $id) {
    ... on ProjectV2 {
      id
      title
      number
      closed
    }
  }
}
"""




def run_query(query: str, variables: dict, github_token: str) -> dict:
    if not github_token:
        logging.error("No GITHUB_TOKEN found in environment variables")
        raise ValueError("No GITHUB_TOKEN found in environment variables")

    headers = {
        'Authorization': f'Bearer {github_token}'
    }

    json_data = {'query': query}
    if variables:
        json_data['variables'] = variables

    response = requests.post(GITHUB_API_URL, json=json_data, headers=headers)

    if response.status_code != 200:
        logging.error(f"Query failed to run with status code {response.status_code}: {response.text}")
        raise Exception(f"Query failed to run with status code {response.status_code}: {response.text}")

    logging.debug("Query successful")
    return response.json()

def fetch_projects(org_name: str, github_token: str) -> list:
    query = get_query_projects(org_name)  # Call get_query_projects to get the query string
    result = run_query(query, None, github_token)
    logging.debug(f"Fetched projects: {result}")
    return result['data']['organization']['projectsV2']['nodes']

def fetch_project_details(project_id: str, github_token: str) -> dict:
    variables = {"id": project_id}
    result = run_query(query_project_details, variables, github_token)
    
    if 'errors' in result:
        logging.error(f"Errors in the query response for project {project_id}: {result['errors']}")
        return None

    if 'data' not in result:
        logging.error(f"No data in the query response for project {project_id}.")
        return None

    project = result['data']['node']
    logging.debug(f"Fetched project details: {project}")
    return project

def get_query(project_number: int, after_cursor: str, org_name: str) -> str:
    after_part = f', after: "{after_cursor}"' if after_cursor else ''
    return f"""
    {{
      organization(login: "{org_name}") {{
        projectV2(number: {project_number}) {{
          id
          title
          items(first: 100{after_part}) {{
            pageInfo {{
              hasNextPage
              endCursor
            }}
            nodes {{
              id
              content {{
                ... on Issue {{
                  title
                  number
                  repository {{
                    nameWithOwner
                  }}
                  author {{
                    login
                  }}
                  labels(first: 10) {{
                    nodes {{
                      name
                    }}
                  }}
                }}
              }}
              fieldValues(first: 10) {{
                nodes {{
                  ... on ProjectV2ItemFieldDateValue {{
                    date
                    field {{
                      ... on ProjectV2FieldCommon {{
                        name
                      }}
                    }}
                  }}
                  ... on ProjectV2ItemFieldSingleSelectValue {{
                    name
                    field {{
                      ... on ProjectV2FieldCommon {{
                        name
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """

def fetch_all_project_items(project_number: int, org_name: str, github_token: str) -> list:
    all_items = []
    after_cursor = None

    while True:
        query = get_query(project_number, after_cursor, org_name)
        result = run_query(query, None, github_token)

        if 'errors' in result:
            logging.error(f"Errors in the query response: {result['errors']}")
            return all_items

        if 'data' not in result:
            logging.error("No data in the query response.")
            return all_items

        project = result['data']['organization']['projectV2']
        project_items = project['items']['nodes']
        all_items.extend(project_items)

        page_info = project['items']['pageInfo']
        if not page_info['hasNextPage']:
            break

        after_cursor = page_info['endCursor']

    logging.debug(f"Fetched all project items: {all_items}")
    return all_items

def sanitize(text: str) -> str:
    return re.sub(r'\W+', '', text)

def fetch_project_details_by_number(project_number: int, org_name: str, github_token: str) -> dict:
    #Fetch project details by project number
    query_project_by_number = """
    query($org_name: String!, $project_number: Int!) {
      organization(login: $org_name) {
        projectV2(number: $project_number) {
          id
          title
          closed
          number
          items(first: 100) {
            nodes {
              id
              content {
                ... on Issue {
                  id
                  title
                  number
                  labels(first: 10) {
                    nodes {
                      name
                    }
                  }
                  repository {
                    nameWithOwner
                  }
                  author {
                    login
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    variables = {
        "org_name": org_name,
        "project_number": project_number
    }
    result = run_query(query_project_by_number, variables, github_token)
    
    if 'errors' in result:
        logging.error(f"Errors in the query response for project number {project_number}: {result['errors']}")
        return None

    if 'data' not in result or not result['data']['organization']['projectV2']:
        logging.error(f"No data found for project number {project_number}.")
        return None

    project = result['data']['organization']['projectV2']
    logging.debug(f"Fetched project details for project number {project_number}: {project}")
    return project


def list_past_due_issues(project_number: int, org_name: str, github_token: str) -> list:
    project_items = fetch_all_project_items(project_number, org_name, github_token)
    current_date = datetime.now().date()
    past_due_issues = []

    for item in project_items:
        content = item.get('content')
        if content and 'title' in content and 'number' in content:
            title = content['title']
            number = content['number']
            labels = [label['name'] for label in content['labels']['nodes']]
            repository = content['repository']['nameWithOwner'].split('/')
            owner = repository[0]
            repo = repository[1]

            # Check for "Backlog" label
            if "Backlog" in labels:
                continue
            
            has_due_date = False
            is_done = False
            due_date = None

            for field in item.get('fieldValues', {}).get('nodes', []):
                field_name = sanitize(field.get('field', {}).get('name', ''))
                field_value = sanitize(field.get('name', ''))

                if field_name == "DueDate" and field.get('date'):
                    has_due_date = True
                    due_date = datetime.strptime(field.get('date'), '%Y-%m-%d').date()
                if field_name == "Status" and re.search(r'\bdone\b', field_value, re.IGNORECASE):
                    is_done = True

            if is_done:
                continue

            if has_due_date and due_date < current_date:
                past_due_issues.append({
                    'owner': owner,
                    'repo': repo,
                    'number': number,
                    'title': title,
                    'due_date': due_date
                })

    logging.debug(f"Listed past due issues: {past_due_issues}")
    return past_due_issues

# Function to get the repository ID
def get_repository_id(org_name: str, repo_name: str, github_token: str) -> str:
    repository_query = '''
    query($organization: String!, $repo: String!) {
      organization(login: $organization) {
        repository(name: $repo) {
          id
        }
      }
    }
    '''
    repo_variables = {
        "organization": org_name,
        "repo": repo_name
    }
    repo_data = run_query(repository_query, repo_variables, github_token)
    if 'data' in repo_data and repo_data['data']['organization'] and repo_data['data']['organization']['repository']:
        logging.debug(f"Repository ID fetched: {repo_data['data']['organization']['repository']['id']}")
        return repo_data['data']['organization']['repository']['id']
    else:
        logging.error(f"Repository {repo_name} in organization {org_name} not found or access issue.")
        return None

# Function to get the issue ID
def get_issue_id(org_name: str, repo_name: str, issue_number: int, github_token: str) -> str:
    issue_query = '''
    query($organization: String!, $repo: String!, $number: Int!) {
      organization(login: $organization) {
        repository(name: $repo) {
          issue(number: $number) {
            id
          }
        }
      }
    }
    '''
    issue_variables = {
        "organization": org_name,
        "repo": repo_name,
        "number": issue_number
    }
    issue_data = run_query(issue_query, issue_variables, github_token)
    if 'data' in issue_data and issue_data['data']['organization'] and issue_data['data']['organization']['repository'] and issue_data['data']['organization']['repository']['issue']:
        logging.debug(f"Issue ID fetched: {issue_data['data']['organization']['repository']['issue']['id']}")
        return issue_data['data']['organization']['repository']['issue']['id']
    else:
        logging.error(f"Issue #{issue_number} in repository {repo_name} not found or access issue.")
        return None

# Function to check if the "Past Due" label exists and get its ID, or create it if it doesn't exist
def get_or_create_label_id(org_name: str, repo_name: str, repository_id: str, github_token: str, label_name:str) -> str:
    label_query = '''
    query($organization: String!, $repo: String!, $name: String!) {
      organization(login: $organization) {
        repository(name: $repo) {
          label(name: $name) {
            id
          }
        }
      }
    }
    '''
    label_variables = {
        "organization": org_name,
        "repo": repo_name,
        "name": label_name
    }
    label_data = run_query(label_query, label_variables, github_token)
    label_info = label_data['data']['organization']['repository']['label']

    if label_info is None:
        create_label_mutation = '''
        mutation($repositoryId: ID!, $name: String!, $color: String!, $description: String) {
          createLabel(input: {repositoryId: $repositoryId, name: $name, color: $color, description: $description}) {
            label {
              id
              name
            }
          }
        }
        '''
        label_variables = {
            "repositoryId": repository_id,
            "name": "Past Due",
            "color": "FFC0CB",  # Pink color for "Past Due" label
            "description": "This issue is past due"
        }
        label_data = run_query(create_label_mutation, label_variables, github_token)
        logging.debug(f"Label created: {label_data['data']['createLabel']['label']['id']}")
        return label_data['data']['createLabel']['label']['id']
    else:
        logging.debug(f"Label ID fetched: {label_info['id']}")
        return label_info['id']

# Function to add the "Past Due" label to the issue
def add_label_to_issue(issue_id: str, label_id: str, github_token: str):
    add_label_mutation = '''
    mutation($issueId: ID!, $labelIds: [ID!]!) {
      addLabelsToLabelable(input: {labelableId: $issueId, labelIds: $labelIds}) {
        labelable {
          labels(first: 10) {
            nodes {
              name
            }
          }
        }
      }
    }
    '''
    add_label_variables = {
        "issueId": issue_id,
        "labelIds": [label_id]
    }
    labeling_data = run_query(add_label_mutation, add_label_variables, github_token)
    if 'errors' in labeling_data:
        logging.error(f"Error adding label to the issue: {labeling_data['errors']}")
    else:
        logging.debug("Labels added to the issue:")
        for label in labeling_data['data']['addLabelsToLabelable']['labelable']['labels']['nodes']:
            logging.debug(f"- {label['name']}")

def get_user_id_query(login: str) -> str:
    return f"""
    {{
      user(login: "{login}") {{
        id
      }}
    }}
    """

def fetch_user_id(login: str, github_token: str) -> str:
    query = get_user_id_query(login)
    result = run_query(query, None, github_token)
    
    if 'errors' in result:
        logging.error(f"Errors in the query response for user {login}: {result['errors']}")
        return None

    if 'data' not in result:
        logging.error(f"No data in the query response for user {login}.")
        return None

    user = result['data']['user']
    logging.debug(f"User ID fetched: {user['id']}")
    return user['id']

def list_issues_without_due_dates(project_number: int, org_name: str, github_token: str) -> list:
    project_items = fetch_all_project_items(project_number, org_name, github_token)
    issues_without_due_dates = []

    for item in project_items:
        content = item.get('content')
        if content and 'title' in content and 'number' in content:
            title = content['title']
            number = content['number']
            repository = content['repository']['nameWithOwner'].split('/')
            owner = repository[0]
            repo = repository[1]

            has_due_date = False

            for field in item.get('fieldValues', {}).get('nodes', []):
                field_name = sanitize(field.get('field', {}).get('name', ''))
                if field_name == "DueDate" and field.get('date'):
                    has_due_date = True
                    break

            if not has_due_date:
                issue_owner = content.get('author', {})
                owner_login = issue_owner.get('login', 'Unknown')
                issues_without_due_dates.append({
                    'owner': owner,
                    'repo': repo,
                    'number': number,
                    'title': title,
                    'author_login': owner_login
                })

    logging.debug(f"Listed issues without due dates: {issues_without_due_dates}")
    return issues_without_due_dates
