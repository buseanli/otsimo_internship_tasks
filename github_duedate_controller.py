import requests
import json
import re
from datetime import datetime

# Replace with your GitHub personal access token
GITHUB_TOKEN = 'your token'
ORG_NAME = 'otsimo'

# GitHub GraphQL endpoint
GITHUB_API_URL = 'https://api.github.com/graphql'

# GraphQL query to fetch projects
query_projects = """
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
""" % ORG_NAME

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

def run_query(query, variables=None):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    json_body = {'query': query}
    if variables:
        json_body['variables'] = variables
    response = requests.post(GITHUB_API_URL, json=json_body, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Query failed to run with status code {response.status_code}: {response.text}")

def fetch_projects():
    result = run_query(query_projects)
    
    if 'errors' in result:
        print("Errors in the query response:", result['errors'])
        return []

    if 'data' not in result:
        print("No data in the query response.")
        return []

    projects = result['data']['organization']['projectsV2']['nodes']
    return projects

def fetch_project_details(project_id):
    variables = {"id": project_id}
    result = run_query(query_project_details, variables)
    
    if 'errors' in result:
        print(f"Errors in the query response for project {project_id}:", result['errors'])
        return None

    if 'data' not in result:
        print(f"No data in the query response for project {project_id}.")
        return None

    project = result['data']['node']
    return project

def get_query(project_number, after_cursor=None):
    after_part = f', after: "{after_cursor}"' if after_cursor else ''
    return f"""
    {{
      organization(login: "{ORG_NAME}") {{
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

def fetch_all_project_items(project_number):
    all_items = []
    after_cursor = None

    while True:
        query = get_query(project_number, after_cursor)
        result = run_query(query)

        if 'errors' in result:
            print("Errors in the query response:", result['errors'])
            return all_items

        if 'data' not in result:
            print("No data in the query response.")
            return all_items

        project = result['data']['organization']['projectV2']
        project_items = project['items']['nodes']
        all_items.extend(project_items)

        page_info = project['items']['pageInfo']
        if not page_info['hasNextPage']:
            break

        after_cursor = page_info['endCursor']

    return all_items

def sanitize(text):
    return re.sub(r'\W+', '', text)

def list_past_due_issues(project_number):
    project_items = fetch_all_project_items(project_number)
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
            
            # Check custom fields for due date and status
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

    return past_due_issues

# Function to make a GraphQL request
def graphql_request(query, variables=None):
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Content-Type': 'application/json'
    }
    response = requests.post(GITHUB_API_URL, headers=headers, json={'query': query, 'variables': variables})
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Query failed to run with status code {response.status_code}: {response.text}")

# Function to get the repository ID
def get_repository_id(org_name, repo_name):
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
    repo_data = graphql_request(repository_query, repo_variables)
    if 'data' in repo_data and repo_data['data']['organization'] and repo_data['data']['organization']['repository']:
        return repo_data['data']['organization']['repository']['id']
    else:
        #print(f"Repository {repo_name} in organization {org_name} not found or access issue.")
        return None

# Function to get the issue ID
def get_issue_id(org_name, repo_name, issue_number):
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
    issue_data = graphql_request(issue_query, issue_variables)
    if 'data' in issue_data and issue_data['data']['organization'] and issue_data['data']['organization']['repository'] and issue_data['data']['organization']['repository']['issue']:
        return issue_data['data']['organization']['repository']['issue']['id']
    else:
        print(f"Issue #{issue_number} in repository {repo_name} not found or access issue.")
        return None

# Function to check if the "Past Due" label exists and get its ID, or create it if it doesn't exist
def get_or_create_label_id(org_name, repo_name, repository_id):
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
        "name": "Past Due"
    }
    label_data = graphql_request(label_query, label_variables)
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
        label_data = graphql_request(create_label_mutation, label_variables)
        return label_data['data']['createLabel']['label']['id']
    else:
        return label_info['id']

# Function to add the "Past Due" label to the issue
def add_label_to_issue(issue_id, label_id):
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
    labeling_data = graphql_request(add_label_mutation, add_label_variables)
    if 'errors' in labeling_data:
        print("Error adding label to the issue:", labeling_data['errors'])
    else:
        print("Labels added to the issue:")
        for label in labeling_data['data']['addLabelsToLabelable']['labelable']['labels']['nodes']:
            print(f"- {label['name']}")
        


def get_user_id_query(login):
    return f"""
    {{
      user(login: "{login}") {{
        id
      }}
    }}
    """

def fetch_user_id(login):
    query = get_user_id_query(login)
    result = run_query(query)
    
    if 'errors' in result:
        print(f"Errors in the query response for user {login}:", result['errors'])
        return None

    if 'data' not in result:
        print(f"No data in the query response for user {login}.")
        return None

    user = result['data']['user']
    return user['id']




def list_issues_without_due_dates(project_number):
    project_items = fetch_all_project_items(project_number)
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
                owner_id = fetch_user_id(owner_login) if owner_login != 'Unknown' else 'Unknown'
                issues_without_due_dates.append({
                    'owner': owner,
                    'repo': repo,
                    'number': number,
                    'title': title,
                    'author_login': owner_login,
                    'author_id': owner_id
                })

    return issues_without_due_dates







if __name__ == "__main__":
    projects = fetch_projects()
    open_projects = []
    open_project_numbers = []

    for project in projects:
        project_details = fetch_project_details(project['id'])
        if project_details and not project_details['closed']:
            open_projects.append(project_details)
            open_project_numbers.append(project_details['number'])
    
    if open_projects:
        print("Open Projects:")
        for project in open_projects:
            print(f"- Project Number: {project['number']}, Project Name: {project['title']}")
    else:
       print("No open projects found.")

    print("Open Project Numbers:", open_project_numbers)
    # List past due issues for all open projects and adding label
    for project_number in open_project_numbers:
        #print(f"\nListing past due issues for project number {project_number}:")
        past_due_issues = list_past_due_issues(project_number)
        if past_due_issues:
            for issue in past_due_issues:
                #TODO Implement adding (PAST DUE) label function here
                org_name = issue["owner"]
                repo_name = issue["repo"]
                issue_number = issue["number"]
                # Step 1: Get the repository ID
                repository_id = get_repository_id(org_name, repo_name)
                if repository_id is None:
                  continue
                print(f"Repository ID: {repository_id}")

                # Step 2: Get the issue ID
                issue_id = get_issue_id(org_name, repo_name, issue_number)
                if issue_id is None:
                  continue
                print(f"Issue ID: {issue_id}")

                # Step 3: Get or create the "Past Due" label ID
                label_id = get_or_create_label_id(org_name, repo_name, repository_id)
                print(f"Label ID: {label_id}")

                # Step 4: Add the "Past Due" label to the issue
                #!!!!!!!!!!! add_label_to_issue(issue_id, label_id)


    # List issues without due dates for all open projects
    for project_number in open_project_numbers:
        print(f"\nListing issues without due dates for project number {project_number}:")
        issues_without_due_dates = list_issues_without_due_dates(project_number)
        if issues_without_due_dates:
            for issue in issues_without_due_dates:
                print(f"- Issue #{issue['number']} in {issue['owner']}/{issue['repo']}: {issue['title']}")
                print(f"  Owner Login: {issue['author_login']}, Owner ID: {issue['author_id']}")
        else:
            print("No issues without due dates found.")
