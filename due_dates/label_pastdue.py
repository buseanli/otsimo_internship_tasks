#This script finds issues which has past due dates and adds the label 'Past Due'.
import os
import github_utils
import logging

def main():
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
    # List past due issues for all open projects and adding label
    for i in range (0, len(open_project_numbers)):
        past_due_issues = github_utils.list_past_due_issues(open_project_numbers[i], ORG_NAME, GITHUB_TOKEN)
        if past_due_issues:
            for issue in past_due_issues:
                org_name = issue["owner"]
                repo_name = issue["repo"]
                issue_number = issue["number"]
                # Step 1: Get the repository ID
                repository_id = github_utils.get_repository_id(org_name, repo_name, GITHUB_TOKEN)
                if repository_id is None:
                    continue
                logging.debug(f"Repository ID: {repository_id}")

                # Step 2: Get the issue ID
                issue_id = github_utils.get_issue_id(org_name, repo_name, issue_number, GITHUB_TOKEN)
                if issue_id is None:
                    continue
                logging.debug(f"Issue ID: {issue_id}")

                # Step 3: Get or create the "Past Due" label ID
                label_id = github_utils.get_or_create_label_id(org_name, repo_name, repository_id, GITHUB_TOKEN, 'Past Due')
                logging.debug(f"Label ID: {label_id}")
                # Step 4: Add the "Past Due" label to the issue
                github_utils.add_label_to_issue(issue_id, label_id, GITHUB_TOKEN)

main()