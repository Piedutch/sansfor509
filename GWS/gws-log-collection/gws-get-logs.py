from __future__ import print_function
import json
import requests
import os
import argparse
import logging
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dateutil import parser as dateparser


class Google(object):
    """
    Class for connecting to API and retreiving longs
    """

    # These applications will be collected by default
    # Applications with over 1000 entries: token, meet, mobile, login, drive, calender
    DEFAULT_APPLICATIONS = ['access_transparency', 'admin', 'calendar', 'chat', 'drive', 'gcp', 'gplus', 'groups', 'groups_enterprise', 'jamboard', 'login', 'meet', 'mobile', 'rules', 'saml', 'token', 'user_accounts', 'context_aware_access', 'chrome', 'data_studio', 'keep']

    #DEFAULT_APPLICATIONS = ['admin']

    #DEFAULT_APPLICATIONS = ['login', 'drive', 'admin', 'user_accounts', 'chat', 'calendar', 'token']

    def __init__(self, **kwargs):
        self.SERVICE_ACCOUNT_FILE = kwargs['creds_path']
        self.delegated_creds = kwargs['delegated_creds']
        self.output_path = kwargs['output_path']
        self.app_list = kwargs['apps']
        self.update = kwargs['update']
        self.overwrite = kwargs['overwrite']

        # Create output path if required
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        # Connect to Google API
        self.service = self.google_session()

    @staticmethod
    def get_application_list():
        """ 
        Returns a list of valid applicationName parameters for the activities.list() API method 
        Note: this is the complete list of valid options, and some may not be valid on particular accounts.
        """
        r = requests.get('https://admin.googleapis.com/$discovery/rest?version=reports_v1')
        return r.json()['resources']['activities']['methods']['list']['parameters']['applicationName']['enum']

    @staticmethod
    def _check_recent_date(log_file_path):
        """
        Opens an existing log file to find the datetime of the most recent record
        """
        return_date = None        
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r') as f:
                for line in f.readlines():
                    json_obj = json.loads(line)
                    line_datetime = dateparser.parse(json_obj['id']['time'])
                    if not return_date:
                        return_date = line_datetime
                    elif return_date < line_datetime:
                        return_date = line_datetime
        return return_date

    def google_session(self):
        """
        Establish connection to Google Workspace.
        """

        SCOPES = ['https://www.googleapis.com/auth/admin.reports.audit.readonly']
        creds = service_account.Credentials.from_service_account_file(self.SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        delegated_credentials = creds.with_subject(self.delegated_creds)

        service = build('admin', 'reports_v1', credentials=delegated_credentials)

        return service
    
    def get_logs(self):
        """ 
        Collect all logs from specified applications
        """

        total_saved, total_found = 0, 0

        for app in self.app_list:

            # Define output file name
            output_file = f"{self.output_path}/{app}_logs.json"

            # Get most recent log entry date (if required)
            most_recent_entry_date = self._check_recent_date(output_file) if self.update else None

            # Collect logs for specified app
            logging.info(f"Collecting logs for {app}...")
            if self.update and most_recent_entry_date:
                logging.debug(f"Only extracting records after {most_recent_entry_date}")

            saved, found = self._get_activity_logs_with_pagination(
                app, 
                output_file=output_file, 
                overwrite=self.overwrite, 
                only_after_datetime=most_recent_entry_date if self.update else None
            )
            logging.info(f"Saved {saved} of {found} entries for {app}")
            total_saved += saved
            total_found += found

        logging.info(f"TOTAL: Saved {total_saved} of {total_found} records.")

    def _get_activity_logs_with_pagination(self, application_name, output_file, overwrite=False, only_after_datetime=None):
        """ Collect activitiy logs from the specified application with pagination """

        page_token = None
        output_count = 0
        total_activities = 0

        while True:
            try:
                results = self.service.activities().list(
                    userKey='all',
                    applicationName=application_name,
                    maxResults=1000,
                    startTime='2022-12-01T00:00:00Z',
                    endTime='2023-06-12T23:59:59Z',
                    pageToken=page_token
                ).execute()
            except TypeError as e:
                logging.error(f"Error collecting logs for {application_name}: {e}")
                return False, False

            activities = results.get('items', [])
            if activities:
                with open(output_file, 'w' if overwrite else 'a') as output:
                    # Loop through activities in reverse order (so latest events are at the end)
                    for entry in activities[::-1]:
                        # TODO: See if we can speed this up to prevent looping through all activities

                        # If we're only exporting new records, check the datetime of the record
                        if only_after_datetime:
                            entry_datetime = dateparser.parse(entry['id']['time'])
                            if entry_datetime <= only_after_datetime:
                                continue  # Skip this record

                        # Output this record
                        json_formatted_str = json.dumps(entry)
                        output.write(f"{json_formatted_str}\n")
                        output_count += 1

            total_activities += len(activities)
            page_token = results.get('nextPageToken')
            if not page_token:
                break

        return output_count, total_activities

    def _get_activity_logs(self, application_name, output_file, overwrite=False, only_after_datetime=None):
        """ Collect activitiy logs from the specified application """

        # Call the Admin SDK Reports API

        page_token = None

        try:
            results = self.service.activities().list(
                userKey='all',
                applicationName=application_name,
                maxResults=1000,
                startTime='2022-12-01T00:00:00Z',
                endTime='2023-06-12T23:59:59Z',
                #startTime='2022-12-20T03:22:42.093Z',
                #endTime='2022-12-20T12:04:43.720Z',
                pageToken=page_token
                ).execute()
        except TypeError as e:
            logging.error(f"Error collecting logs for {application_name}: {e}")
            return False, False

        activities = results.get('items', [])
        output_count = 0
        if activities:
            with open(output_file, 'w' if overwrite else 'a') as output:

                # Loop through activities in reverse order (so latest events are at the end)
                for entry in activities[::-1]:
                    # TODO: See if we can speed this up to prevent looping through all activities

                    # If we're only exporting new records, check the datetime of the record
                    if only_after_datetime:
                        entry_datetime = dateparser.parse(entry['id']['time'])
                        if (entry_datetime <= only_after_datetime):
                            continue  # Skip this record

                    # Output this record
                    json_formatted_str = json.dumps(entry)
                    output.write(f"{json_formatted_str}\n")
                    output_count += 1

        return output_count, len(activities)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='This script will fetch Google Workspace logs.')

    # Configure with single config file
    parser.add_argument('--config', '-c', required=False, default='config.json',
                        help="Configuration file containing required arguments")

    # Or parse arguments separately
    parser.add_argument('--creds-path', required=False, help=".json credential file for the service account.")
    parser.add_argument('--delegated-creds', required=False, help="Principal name of the service account")
    parser.add_argument('--output-path', '-o', required=False, help="Folder to save downloaded logs")
    parser.add_argument('--apps', '-a', required=False, default=','.join(Google.DEFAULT_APPLICATIONS), 
                        help="Comma separated list of applications whose logs will be downloaded. "
                         "Or 'all' to attempt to download all available logs")
    
    # Update/overwrite behaviour
    parser.add_argument('--update', '-u', required=False, action="store_true",
                        help="Update existing log files (if present). This will only save new log records.")
    parser.add_argument('--overwrite', required=False, action="store_true",
                        help="Overwrite existing log files (if present), with all available log records.")
    
    # Logging/output levels
    parser.add_argument('--quiet', '-q', dest="log_level", action='store_const',
                        const=logging.ERROR, default=logging.INFO,
                        help="Prevent all output except errors")
    parser.add_argument('--debug', dest="log_level", action='store_const',
                        const=logging.DEBUG, default=logging.INFO,
                        help="Show debug output.")

    args = parser.parse_args()

    # Setup logging
    FORMAT = '%(asctime)s %(levelname)-8s %(message)s'
    logging.basicConfig(format=FORMAT, level=args.log_level)

    # Load values from config file, but don't overwrite arguments specified separately
    # (i.e. args passed at the command line overwrite values stored in config file)
    if args.config and os.path.exists(args.config):
        with open(args.config) as json_data_file:
            config = json.load(json_data_file)
        for key in config:
            if key not in args or not vars(args)[key]:
                vars(args)[key] = config[key]

    # Convert apps argument to list
    if args.apps.strip().lower() == 'all':
        args.apps = Google.get_application_list()
    elif args.apps:
        args.apps = [a.strip().lower() for a in args.apps.split(',')]

    # DEBUG: Show combined arguments to be used
    logging.debug(args)

    # Connect to Google API
    google = Google(**vars(args))
    google.get_logs()