import os
import boto3
import tempfile
import taglib  # Make sure to have PyTagLib library installed in your Lambda deployment package


def handler(event, context):
    print(event)
    if event["Records"][0]["eventName"] == "ObjectCreated:Put":
        extractMetadata(event, context)
    elif event["Records"][0]["eventName"] == "ObjectRemoved:Delete":
        deleteMetadata(event, context)


def safe_execute(default, key, dict):
    try:
        return dict.tags[key][0]
    except KeyError:
        return default


def extractMetadata(event, context):
    # Retrieve the S3 bucket and object key from the event
    s3_bucket = event["Records"][0]["s3"]["bucket"]["name"]
    s3_object_key = event["Records"][0]["s3"]["object"]["key"]

    # Download the recently uploaded audio file from S3 to the Lambda's temporary directory
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, "temp_audio_file.mp3")
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
    )
    s3_client.download_file(s3_bucket, s3_object_key, temp_file_path)

    # Use PyTagLib to extract metadata from the audio file
    audio_file = taglib.File(temp_file_path)
    print(audio_file.tags)
    metadata = {
        "id": {"S": s3_object_key},
        "title": {
            "S": safe_execute("No title provided by makemoke", "TITLE", audio_file)
        },
        "artist": {
            "S": safe_execute("No artist provided by makemoke", "ARTIST", audio_file)
        },
        "album": {
            "S": safe_execute("No album provided by makemoke", "ALBUM", audio_file)
        },
        "duration": {"S": str(audio_file.length)},
    }

    # Write the extracted metadata to DynamoDB
    dynamodb_client = boto3.client("dynamodb")
    table_name = os.getenv("MAKEMOKEMUSICMETADATA_TABLE_NAME")
    dynamodb_client.put_item(
        TableName=table_name,
        Item=metadata,
    )

    # Clean up: delete the temporary directory and file
    os.remove(temp_file_path)
    os.rmdir(temp_dir)


def deleteMetadata(event, context):
    # Retrieve the S3 bucket and object key from the event
    s3_object_key = event["Records"][0]["s3"]["object"]["key"]

    # Delete the metadata from DynamoDB
    dynamodb_client = boto3.client("dynamodb")
    table_name = os.getenv("MAKEMOKEMUSICMETADATA_TABLE_NAME")

    options = {
        "TableName": table_name,
        "KeyConditionExpression": "id = :id",
        "ExpressionAttributeValues": {
            ":id": {"S": s3_object_key},
        },
    }

    record = dynamodb_client.query(**options)
    print(record)
    dynamodb_client.delete_item(
        TableName=table_name,
        Key={"id": record["Items"][0]["id"], "artist": record["Items"][0]["artist"]},
    )
    return
