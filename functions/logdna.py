from botocore.vendored import requests
import os
import json
import gzip
from StringIO import StringIO

# Constants:
MAX_LINE_LENGTH = 32000
MAX_REQUEST_TIMEOUT = 30

# Main Handler:
def handler(event, context):
    key, hostname, tags, baseurl = setup()
    cw_log_lines = decodeEvent(event)
    messages, options = prepare(cw_log_lines, hostname, tags)
    send_log(messages=messages, options=options, key=key, baseurl=baseurl)

# Getting Parameters from Environment Variables:
def setup():
    key = os.environ.get('LOGDNA_KEY', None)
    hostname = os.environ.get('LOGDNA_HOSTNAME', None)
    tags = os.environ.get('LOGDNA_TAGS', None)
    baseurl = buildURL(os.environ.get('LOGDNA_URL', None))
    return key, hostname, tags, baseurl

# Building URL using baseurl parameter:
def buildURL(baseurl):
    if baseurl is None:
        return 'https://logs.logdna.com/logs/ingest'
    return 'https://' + baseurl

# Parsing Event:
def decodeEvent(event):
    cw_data = str(event['awslogs']['data'])
    cw_logs = gzip.GzipFile(fileobj=StringIO(cw_data.decode('base64', 'strict'))).read()
    return json.loads(cw_logs)

# Preparing the Payload:
def prepare(cw_log_lines, hostname=None, tags=None):
    messages = list()
    options = dict()
    app = 'CloudWatch'
    meta = {'type': app}
    if 'logGroup' in cw_log_lines:
        app = cw_log_lines['logGroup'].split('/')[-1]
        meta['group'] = cw_log_lines['logGroup'];
    if 'logStream' in cw_log_lines:
        options['hostname'] = cw_log_lines['logStream'].split('/')[-1].split(']')[-1]
        meta['stream'] = cw_log_lines['logStream']
    if hostname is not None:
        options['hostname'] = hostname
    if tags is not None:
        options['tags'] = tags
    for cw_log_line in cw_log_lines['logEvents']:
        msg = cw_log_line['message']
        if  not msg.startswith('START RequestId') and not msg.startswith('END RequestId') and not msg.startswith('REPORT RequestId'):
            stripped_msg = msg.split('\t', 3)[-1]
            level = msg.split('\t')[0]

            if not level.startswith('['):
                level = ''

            message = {
                'line': '' + level + ' ' + stripped_msg,
                'timestamp': cw_log_line['timestamp'],
                'file': app,
                'meta': meta}
            messages.append(sanitizeMessage(message))
    return messages, options

# Polishing the Message:
def sanitizeMessage(message):
    if message and message['line']:
        if len(message['line']) > MAX_LINE_LENGTH:
            message['line'] = message['line'][:MAX_LINE_LENGTH] + ' (cut off, too long...)'
    return message

# Submitting the Log Payload into LogDNA:
def send_log(messages, options, baseurl, key=None):
    if key is not None:
        data = {'e': 'ls', 'ls': messages}
        requests.post(
            url=baseurl,
            json=data,
            auth=('user', key),
            params={
                'hostname': options['hostname'],
                'tags': options['tags'] if 'tags' in options else None},
            stream=True,
            timeout=MAX_REQUEST_TIMEOUT)
