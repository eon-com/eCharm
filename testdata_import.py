from __future__ import print_function

import os.path
import pathlib

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

SPREADSHEET_ID = '1bvwxsGRMaEsiuz_ghY3HEbFEMCPahINcVoGE2k_zgOc'

def main():
    directory = pathlib.Path(__file__).parent.resolve()
    """
    Access spreadsheet via Google Sheets API.
    Documentation how to setup the access: https://developers.google.com/sheets/api/quickstart/python
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    token_filename = os.path.join(directory, 'token_deepatlas.json')
    if os.path.exists(token_filename):
        creds = Credentials.from_authorized_user_file(token_filename, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.path.join(directory, 'credentials.json'), SCOPES)
            creds = flow.run_local_server(port=8083)
        # Save the credentials for the next run
        with open(token_filename, 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('sheets', 'v4', credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range='A1:Z100').execute()
        values = result.get('values', [])

        return values

    except HttpError as err:
        print(err)


if __name__ == '__main__':
    main()