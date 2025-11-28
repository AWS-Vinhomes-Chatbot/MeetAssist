"""
Archive Data Lambda Handler

This Lambda is triggered by EventBridge Schedule (every 5 minutes).
It archives ALL tables from RDS to S3.

Flow:
1. Triggered by EventBridge Schedule Rule (rate: 5 minutes)
2. Delegate to ArchiveService to:
   - Query all data from ALL tables in RDS
   - Convert each table to CSV format
   - Upload to S3 (overwrite existing files)
   - Update metadata/archive_info.json
"""

import json
import os
from typing import Dict, Any
import boto3

from services.archive import ArchiveService
from services.postgres import PostgreSQLService
from util.lambda_logger import create_logger

# Setup
lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "ArchiveHandler")
logger = create_logger(lambda_function_name)

# AWS clients
session = boto3.session.Session()
sm_client = session.client(service_name="secretsmanager")
s3_client = session.client("s3")

# Environment variables
RDS_HOST = os.getenv("RDS_HOST")
RDS_PORT = os.getenv("RDS_PORT", "5432")
RDS_DATABASE = os.getenv("RDS_DATABASE", "postgres")
SECRET_NAME = os.getenv("SECRET_NAME")
BUCKET_NAME = os.getenv("BUCKET_NAME")
DATA_PREFIX = os.getenv("DATA_PREFIX", "data")

# Initialize services
pg = PostgreSQLService(secret_client=sm_client, db_host=RDS_HOST, db_name=RDS_DATABASE, log=logger)
archive_service = ArchiveService(
    s3_client=s3_client,
    bucket_name=BUCKET_NAME,
    data_prefix=DATA_PREFIX,
    logger=logger
)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Archive Lambda Handler - Triggered by EventBridge Schedule
    
    Event structure from EventBridge Schedule:
    {
        "version": "0",
        "id": "...",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
        "time": "2025-11-28T10:30:00Z",
        ...
    }
    
    This handler archives ALL tables to S3 on every invocation.
    Uses checksum to skip uploading unchanged tables.
    """
    logger.info(f"Archive event received: {json.dumps(event)}")
    
    try:
        # Connect to database
        pg.set_secret(SECRET_NAME)
        conn = pg.connect_to_db()
        
        if not conn:
            logger.error("Failed to connect to database")
            return error_response("Database connection failed", 500)
        
        try:
            # Load existing checksums from metadata
            existing_metadata = archive_service.get_metadata()
            existing_checksums = {}
            for table_name, table_info in existing_metadata.get("tables", {}).items():
                if "checksum" in table_info:
                    existing_checksums[table_name] = table_info["checksum"]
            
            # Archive ALL tables
            results = {}
            new_checksums = {}
            total_records = 0
            uploaded_count = 0
            skipped_count = 0
            
            for table_name in archive_service.get_all_tables():
                try:
                    record_count, checksum, was_uploaded = archive_service.archive_table(
                        conn, table_name, existing_checksums
                    )
                    results[table_name] = {
                        "status": "success",
                        "record_count": record_count,
                        "uploaded": was_uploaded
                    }
                    new_checksums[table_name] = checksum
                    total_records += record_count
                    
                    if was_uploaded:
                        uploaded_count += 1
                        logger.info(f"Archived {table_name}: {record_count} records (uploaded)")
                    else:
                        skipped_count += 1
                        logger.info(f"Archived {table_name}: {record_count} records (skipped - unchanged)")
                        
                except Exception as e:
                    logger.error(f"Failed to archive {table_name}: {str(e)}")
                    results[table_name] = {
                        "status": "error",
                        "error": str(e)
                    }
                    # Rollback transaction to recover from error state
                    try:
                        conn.rollback()
                    except:
                        pass
            
            # Update metadata with summary and checksums
            archive_service.update_metadata_full(results, total_records, new_checksums)
            
            logger.info(f"Archive complete: {uploaded_count} uploaded, {skipped_count} skipped, {total_records} total records")
            
            return success_response({
                "tables_archived": len(results),
                "tables_uploaded": uploaded_count,
                "tables_skipped": skipped_count,
                "total_records": total_records,
                "details": results
            })
            
        finally:
            conn.close()
            logger.info("Database connection closed")
            
    except Exception as e:
        logger.error(f"Error in archive handler: {str(e)}", exc_info=True)
        return error_response(str(e), 500)


def success_response(data: Dict, status_code: int = 200) -> Dict:
    """Build success response"""
    return {
        "statusCode": status_code,
        "body": json.dumps({
            "success": True,
            **data
        })
    }


def error_response(message: str, status_code: int = 500) -> Dict:
    """Build error response"""
    return {
        "statusCode": status_code,
        "body": json.dumps({
            "success": False,
            "error": message
        })
    }

