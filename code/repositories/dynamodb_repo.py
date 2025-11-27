"""
DynamoDB Repository - Data access layer for DynamoDB operations.

Handles all direct interactions with DynamoDB tables.
Separates data access logic from business logic.
"""

import os
import logging
import boto3
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError


logger = logging.getLogger()

# Module-level singleton for DynamoDB resource (reuse across Lambda invocations)
_dynamodb_resource = None

def get_dynamodb_resource():
    """
    Get or create DynamoDB resource singleton.
    
    This is reused across Lambda invocations to improve performance.
    """
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")
        logger.info("Created new DynamoDB resource")
    return _dynamodb_resource


class DynamoDBRepository:
    """Repository for DynamoDB operations."""
    
    def __init__(self, table_name: str = None):
        """
        Initialize DynamoDB repository.
        
        Args:
            table_name: DynamoDB table name. If None, reads from SESSION_TABLE_NAME env var.
        
        Example:
            # Use default table from env
            repo = DynamoDBRepository()
            
            # Use specific table
            repo = DynamoDBRepository(table_name="my-custom-table")
            
            # Use different env var
            repo = DynamoDBRepository(table_name=os.environ.get("OTHER_TABLE"))
        """
        # ✅ Reuse singleton DynamoDB resource
        self.dynamodb = get_dynamodb_resource()
        
        # ✅ Get table name from parameter or environment variable
        self.table_name = table_name or os.environ.get("SESSION_TABLE_NAME")
        
        if not self.table_name:
            raise ValueError("Table name must be provided or SESSION_TABLE_NAME env var must be set")
        
        self.table = self.dynamodb.Table(self.table_name)
        logger.info(f"DynamoDBRepository initialized with table: {self.table_name}")
    
    def get_item(self, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            response = self.table.get_item(Key=key)
            return response.get("Item")
        except ClientError as e:
            logger.error(f"Failed to get item from {self.table_name}: {e}")
            return None