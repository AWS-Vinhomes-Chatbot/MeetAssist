"""
DynamoDB Repository - Data access layer for DynamoDB operations.

Handles all direct interactions with DynamoDB tables.
Separates data access logic from business logic.
"""

import os
import logging
import json
import boto3
from decimal import Decimal
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


def _convert_decimals(obj):
    """
    Recursively convert Decimal values to int/float for Python compatibility.
    DynamoDB returns Decimal for all numbers.
    """
    if isinstance(obj, Decimal):
        # Convert to int if it's a whole number, else float
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj


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
    
    def get_item(self, key: Dict[str, Any] = None, Key: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Get item from table.
        
        Supports both styles:
        - get_item(key={"psid": "123"})  # Repository style
        - get_item(Key={"psid": "123"})  # AWS SDK style
        """
        actual_key = Key or key
        if not actual_key:
            logger.error("No key provided to get_item")
            return None
        try:
            response = self.table.get_item(Key=actual_key)
            item = response.get("Item")
            # Convert Decimal to int/float for Python compatibility
            return _convert_decimals(item) if item else None
        except ClientError as e:
            logger.error(f"Failed to get item from {self.table_name}: {e}")
            return None
    
    def put_item(self, item: Dict[str, Any] = None, Item: Dict[str, Any] = None) -> bool:
        """
        Put an item into the table.
        
        Supports both styles:
        - put_item(item={...})  # Repository style
        - put_item(Item={...})  # AWS SDK style
            
        Returns:
            True if successful, False otherwise
        """
        actual_item = Item or item
        if not actual_item:
            logger.error("No item provided to put_item")
            return False
        try:
            self.table.put_item(Item=actual_item)
            return True
        except ClientError as e:
            logger.error(f"Failed to put item to {self.table_name}: {e}")
            return False
    
    def update_item(self, key: Dict[str, Any] = None, updates: Dict[str, Any] = None, 
                    Key: Dict[str, Any] = None, UpdateExpression: str = None,
                    ExpressionAttributeValues: Dict[str, Any] = None,
                    ExpressionAttributeNames: Dict[str, str] = None) -> bool:
        """
        Update an item in the table.
        
        Supports both styles:
        - update_item(key={"psid": "123"}, updates={"field": "value"})  # Simple style
        - update_item(Key={"psid": "123"}, UpdateExpression="SET ...", 
                      ExpressionAttributeValues={...})  # AWS SDK style
            
        Returns:
            True if successful, False otherwise
        """
        actual_key = Key or key
        if not actual_key:
            logger.error("No key provided to update_item")
            return False
            
        try:
            # AWS SDK style - use expressions directly
            if UpdateExpression:
                params = {
                    "Key": actual_key,
                    "UpdateExpression": UpdateExpression
                }
                if ExpressionAttributeValues:
                    params["ExpressionAttributeValues"] = ExpressionAttributeValues
                if ExpressionAttributeNames:
                    params["ExpressionAttributeNames"] = ExpressionAttributeNames
                self.table.update_item(**params)
                return True
            
            # Simple style - build expression from updates dict
            if not updates:
                logger.error("No updates provided to update_item")
                return False
                
            update_expr_parts = []
            expr_attr_names = {}
            expr_attr_values = {}
            
            for idx, (attr_name, attr_value) in enumerate(updates.items()):
                placeholder_name = f"#attr{idx}"
                placeholder_value = f":val{idx}"
                update_expr_parts.append(f"{placeholder_name} = {placeholder_value}")
                expr_attr_names[placeholder_name] = attr_name
                expr_attr_values[placeholder_value] = attr_value
            
            update_expression = "SET " + ", ".join(update_expr_parts)
            
            self.table.update_item(
                Key=actual_key,
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values
            )
            return True
        except ClientError as e:
            logger.error(f"Failed to update item in {self.table_name}: {e}")
            return False
    
    def delete_item(self, key: Dict[str, Any] = None, Key: Dict[str, Any] = None) -> bool:
        """
        Delete an item from the table.
        
        Supports both styles:
        - delete_item(key={"psid": "123"})  # Repository style
        - delete_item(Key={"psid": "123"})  # AWS SDK style
            
        Returns:
            True if successful, False otherwise
        """
        actual_key = Key or key
        if not actual_key:
            logger.error("No key provided to delete_item")
            return False
        try:
            self.table.delete_item(Key=actual_key)
            return True
        except ClientError as e:
            logger.error(f"Failed to delete item from {self.table_name}: {e}")
            return False
    
    def query(self, key_condition_expression, expression_attribute_values: Dict[str, Any], 
              limit: int = None) -> Optional[list]:
        """
        Query items from the table.
        
        Args:
            key_condition_expression: Key condition for the query
            expression_attribute_values: Values for the expression
            limit: Maximum number of items to return
            
        Returns:
            List of items or None if error
        """
        try:
            params = {
                "KeyConditionExpression": key_condition_expression,
                "ExpressionAttributeValues": expression_attribute_values
            }
            if limit:
                params["Limit"] = limit
            
            response = self.table.query(**params)
            return response.get("Items", [])
        except ClientError as e:
            logger.error(f"Failed to query {self.table_name}: {e}")
            return None