import os
import json
import logging
import boto3
import requests
from jose import  jwt
from jose.utils import base64url_decode

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamo = boto3.resource("dynamodb")
cognito_region = os.environ.get("AWS_REGION", "us-east-1")
USER_POOL_ID = os.environ.get("USER_POOL_ID")
FB_SECRET_ARN = os.environ.get("FB_SECRET_ARN")
SESSION_TABLE = os.environ.get("SESSION_TABLE_NAME")  # set this env in CDK
table = dynamo.Table(SESSION_TABLE)

# helper: get FB verify token from secretsmanager
def get_fb_verify_token():
    resp = secrets_client.get_secret_value(SecretId=FB_SECRET_ARN)
    secret_string = resp.get("SecretString")
    if secret_string:
        secret_json = json.loads(secret_string)
        return secret_json.get("verify_token")
    return None

# helper: get JWKS for Cognito and return public keys dict by kid
_jwks_cache = {}
def get_cognito_jwks():
    global _jwks_cache
    url = f"https://cognito-idp.{cognito_region}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"
    if url in _jwks_cache:
        return _jwks_cache[url]
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    jwks = r.json()
    keys = {}
    for key in jwks['keys']:
        keys[key['kid']] = key
    _jwks_cache[url] = keys
    return keys

def verify_id_token(token):
    # returns decoded claims if valid, else raise exception
    headers = jwt.get_unverified_header(token)
    kid = headers['kid']
    keys = get_cognito_jwks()
    if kid not in keys:
        raise Exception("Unknown kid")
    public_key = keys[kid]
    # use python-jose to decode with key
    return jwt.decode(token, public_key, algorithms=[public_key['alg']], audience=None, issuer=f"https://cognito-idp.{cognito_region}.amazonaws.com/{USER_POOL_ID}")

def lambda_handler(event, context):
    logger.info("Event: %s", event)
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")

    # If GET: Facebook verification challenge flow
    if http_method == "GET":
        params = event.get("queryStringParameters") or {}
        mode = params.get("hub.mode")
        challenge = params.get("hub.challenge")
        verify_token = params.get("hub.verify_token")
        # read secret from secretsmanager
        expected = get_fb_verify_token()
        if mode == "subscribe" and verify_token and verify_token == expected:
            return {"statusCode": 200, "body": challenge}
        else:
            return {"statusCode": 403, "body": "Verification token mismatch"}

    # If POST: messenger events
    if http_method == "POST":
        body = event.get("body")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        data = json.loads(body)
        # optionally: extract Authorization header with Cognito token
        headers = event.get("headers") or {}
        auth = headers.get("Authorization") or headers.get("authorization")
        user_id = None

        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
            try:
                claims = verify_id_token(token)
                user_id = claims.get("sub")
            except Exception as e:
                logger.warning("Invalid id_token: %s", e)

        # fallback: map PSID -> user via DynamoDB if needed
        # Example: events from FB contain sender.id (psid)
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                psid = messaging.get("sender", {}).get("id")
                # store/update session linking psid -> user_id
                if psid:
                    table.put_item(Item={"psid": psid, "user_id": user_id or "anonymous"})
                # do business logic...
        return {"statusCode": 200, "body": "EVENT_RECEIVED"}

    return {"statusCode": 400, "body": "Unsupported method"}
