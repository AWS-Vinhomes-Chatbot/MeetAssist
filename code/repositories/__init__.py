"""Repositories package for data access layer."""

from .dynamodb_repo import DynamoDBRepository
from .ses_repo import SESRepository

__all__ = ['DynamoDBRepository', 'SESRepository']
