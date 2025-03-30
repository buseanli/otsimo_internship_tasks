#This scripts finds issues which are marked 'Done' after its due date and labels them with 'Resolved Late' label.
import datetime
import github_utils
import re
import logging
import requests

def list_past_due_issues(project_number: int, org_name: str, github_token: str) -> list:
    #Fetch issues from the project and identify those that are resolved after their due dates.
    project_items = github_utils.fetch_all_project_items(project_number, org_name, github_token)
    current_date = datetime.datetime.now().date()
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

            # Skip if the issue has a "Backlog" label
            if "Backlog" in labels:
                continue

            has_due_date = False
            is_done = False
            due_date = None

            # Loop through the fieldValues to find due date and status
            for field in item.get('fieldValues', {}).get('nodes', []):
                field_name = github_utils.sanitize(field.get('field', {}).get('name', ''))
                field_value = github_utils.sanitize(field.get('name', ''))

                # Check if the field is "DueDate"
                if field_name == "DueDate" and field.get('date'):
                    has_due_date = True
                    due_date = datetime.datetime.strptime(field.get('date'), '%Y-%m-%d').date()
                # Check if the status is "Done"
                if field_name == "Status" and re.search(r'done', field_value, re.IGNORECASE):
                    is_done = True


            # If the issue is marked as done and the due date is in the past
            if has_due_date and is_done:
                if due_date < current_date:
                    # Since the status is found as "Done", append the issue to past due issues
                    past_due_issues.append({
                        'owner': owner,
                        'repo': repo,
                        'number': number,
                        'title': title,
                        'due_date': due_date
                    })

    logging.debug(f"Listed past due issues: {past_due_issues}")
    return past_due_issues

def get_done_status_timestamp(owner: str, repo: str, issue_number: int, github_token: str) -> datetime.date:
    """
    Fetch the timeline of the issue and check when it was marked 'done' based on the status change.
    """
    query = """
    query($owner: String!, $repo: String!, $issue_number: Int!) {
      repository(owner: $owner, name: $repo) {
        issue(number: $issue_number) {
          timelineItems(first: 100, itemTypes: [PROJECT_CARD, CROSS_REFERENCED_EVENT, PROJECT_V2_ITEM_FIELD_VALUE_CHANGED_EVENT]) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldValueChangedEvent {
                field {
                  name
                }
                projectV2Item {
                  content {
                    ... on Issue {
                      number
                      title
                    }
                  }
                }
                value
                createdAt
              }
            }
          }
        }
      }
    }
    """
    variables = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number
    }
    headers = {
        'Authorization': f'Bearer {github_token}',
        'Content-Type': 'application/json'
    }

    response = requests.post('https://api.github.com/graphql', json={'query': query, 'variables': variables}, headers=headers)

    if response.status_code == 200:
        result = response.json()
        timeline_items = result['data']['repository']['issue']['timelineItems']['nodes']

        # Look for the event where the Status is changed to "Done"
        for event in timeline_items:
            if event.get('__typename') == 'ProjectV2ItemFieldValueChangedEvent':
                field_name = event['field'].get('name', '').lower()
                field_value = event.get('value', '').lower()
                # Check if the field is "Status" and if the value is "done"
                if field_name == 'status' and 'done' in field_value:
                    done_timestamp = event['createdAt']
                    done_date = datetime.datetime.strptime(done_timestamp, '%Y-%m-%dT%H:%M:%SZ').date()
                    return done_date

    return None

def get_or_create_label(org_name: str, repo_name: str, repository_id: str, github_token: str, label_name:str) -> str:
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
    label_data = github_utils.run_query(label_query, label_variables, github_token)
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
            "name": "Resolved Late",
            "color": "E67E22",  # Burnt orange color for "Resolved Late" label
            "description": "This issue is resolved after due date."
        }
        label_data = github_utils.run_query(create_label_mutation, label_variables, github_token)
        logging.debug(f"Label created: {label_data['data']['createLabel']['label']['id']}")
        return label_data['data']['createLabel']['label']['id']
    else:
        logging.debug(f"Label ID fetched: {label_info['id']}")
        return label_info['id']
    
def label_past_due_issues(org_name: str, github_token: str, label_name: str = "Resolved Late"):
    # Fetch all open projects, find issues resolved after their due date, and label them.
    # Fetch open projects
    projects = github_utils.fetch_projects(org_name, github_token)

    for project in projects:
        project_details = github_utils.fetch_project_details(project['id'], github_token)

        # If the project is closed, skip it
        if project_details['closed']:
            continue
        
        # Get the project number and list all issues past due date and marked as done
        past_due_issues = list_past_due_issues(project_details['number'], org_name, github_token)
        # Label those past due issues as "Resolved Late"
        for issue in past_due_issues:
            repo_owner = issue['owner']
            repo_name = issue['repo']
            issue_number = issue['number']
            issue_id = github_utils.get_issue_id(org_name, repo_name, issue_number, github_token)
            repository_id = github_utils.get_repository_id(org_name, repo_name, github_token)
            if repository_id is None:
                continue
            logging.debug(f"Repository ID: {repository_id}")

            label_id = get_or_create_label(org_name, repo_name, repository_id, github_token, label_name)
            github_utils.add_label_to_issue(issue_id, label_id, github_token)
            logging.debug(f'{label_name} Label is added to the issue {issue_number} in {repo_name}')

def main():
    GITHUB_TOKEN = github_utils.github_token
    ORG_NAME = github_utils.org_name
    # Label issues resolved after their due dates as "Resolved Late"
    label_past_due_issues(ORG_NAME, GITHUB_TOKEN)

if __name__ == "__main__":
    main()
