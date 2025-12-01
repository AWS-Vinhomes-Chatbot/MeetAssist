"""Admin Dashboard Lambda Handler

This handler routes requests to the appropriate service methods.
All business logic is delegated to DashboardService.

Note: ArchiveData Lambda is triggered by EventBridge Schedule (every 5 minutes)
to sync RDS data to S3. This decouples CRUD operations from archiving.
"""

import json
import os
from typing import Dict, Any
import boto3

from services.admin import Admin
from services.postgres import PostgreSQLService
from util.lambda_logger import create_logger

# Setup
lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "AdminHandler")
logger = create_logger(lambda_function_name)

# AWS clients
session = boto3.session.Session()
sm_client = session.client(service_name="secretsmanager")

# Environment variables
RDS_HOST = os.getenv("RDS_HOST")
RDS_PORT = os.getenv("RDS_PORT", "5432")
RDS_DATABASE = os.getenv("RDS_DATABASE", "postgres")
SECRET_NAME = os.getenv("SECRET_NAME")

# Initialize PostgreSQL service
pg = PostgreSQLService(secret_client=sm_client, db_host=RDS_HOST, db_name=RDS_DATABASE, log=logger)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Admin Lambda Handler - Routes requests to DashboardService
    
    Supported actions:
    - get_overview_stats: Get statistics for overview page
    - get_customers: Get customers list
    - get_consultants: Get consultants list  
    - get_appointments: Get appointments with filters
    - get_programs: Get community programs
    - get_tables: Get list of all tables
    - get_table_schema: Get schema for a specific table
    - get_stats: Get database statistics
    """
    logger.info(f"Event received: {json.dumps(event)}")
    
    try:
        # Parse request body
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body)
        
        action = body.get('action')
        
        if not action:
            return error_response("Missing 'action' in request body", 400)
        
        # Connect to database
        pg.set_secret(SECRET_NAME)
        conn = pg.connect_to_db()
        
        if not conn:
            return error_response("Failed to connect to database", 500)
        
        try:
            # Initialize service with connection
            service = Admin(conn, logger)
            
            # Route to appropriate method
            result = route_action(action, body, service)
            return result
            
        finally:
            conn.close()
            logger.info("Database connection closed")
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return error_response(f"Internal server error: {str(e)}", 500)


def route_action(action: str, body: Dict, service: Admin) -> Dict:
    """
    Route action to appropriate service method
    
    Args:
        action: Action name from request
        body: Request body with parameters
        service: DashboardService instance
        
    Returns:
        API Gateway response dict
    """
    logger.info(f"Routing action: {action} with body: {json.dumps(body, default=str)}")
    
    try:
        if action == 'get_overview_stats':
            data = service.get_overview_stats()
            return success_response(data)
        
        elif action == 'get_customers':
            data = service.get_customers(
                limit=body.get('limit', 100),
                offset=body.get('offset', 0),
                search=body.get('search', '')
            )
            return success_response(data)
        
        elif action == 'get_consultants':
            data = service.get_consultants(
                limit=body.get('limit', 100),
                offset=body.get('offset', 0)
            )
            return success_response(data)
        
        elif action == 'create_consultant':
            data = service.create_consultant(
                fullname=body.get('fullname'),
                email=body.get('email'),
                phonenumber=body.get('phonenumber'),
                imageurl=body.get('imageurl'),
                specialties=body.get('specialties'),
                qualifications=body.get('qualifications'),
                joindate=body.get('joindate')
            )
            return success_response(data)
        
        elif action == 'update_consultant':
            data = service.update_consultant(
                consultantid=body.get('consultantid'),
                fullname=body.get('fullname'),
                email=body.get('email'),
                phonenumber=body.get('phonenumber'),
                imageurl=body.get('imageurl'),
                specialties=body.get('specialties'),
                qualifications=body.get('qualifications'),
                joindate=body.get('joindate'),
                isdisabled=body.get('isdisabled')
            )
            return success_response(data)
        
        elif action == 'delete_consultant':
            data = service.delete_consultant(
                consultantid=body.get('consultantid')
            )
            return success_response(data)
        
        elif action == 'get_appointments':
            data = service.get_appointments(
                limit=body.get('limit', 100),
                offset=body.get('offset', 0),
                status=body.get('status')
            )
            return success_response(data)
        
        elif action == 'create_appointment':
            data = service.create_appointment(
                consultantid=body.get('consultantid'),
                customerid=body.get('customerid'),
                date=body.get('date'),
                time=body.get('time'),
                duration=body.get('duration', 60),
                meetingurl=body.get('meetingurl'),
                status=body.get('status', 'pending'),
                description=body.get('description')
            )
            return success_response(data)
        
        elif action == 'update_appointment':
            data = service.update_appointment(
                appointmentid=body.get('appointmentid'),
                consultantid=body.get('consultantid'),
                customerid=body.get('customerid'),
                date=body.get('date'),
                time=body.get('time'),
                duration=body.get('duration'),
                meetingurl=body.get('meetingurl'),
                status=body.get('status'),
                description=body.get('description')
            )
            return success_response(data)
        
        elif action == 'delete_appointment':
            data = service.delete_appointment(
                appointmentid=body.get('appointmentid')
            )
            return success_response(data)
        
        elif action == 'get_tables':
            data = service.get_tables()
            return success_response(data)
        
        elif action == 'get_table_schema':
            table_name = body.get('table_name')
            if not table_name:
                return error_response("Missing 'table_name' in request body", 400)
            try:
                data = service.get_table_schema(table_name)
                return success_response(data)
            except ValueError as e:
                return error_response(str(e), 404)
        
        elif action == 'get_stats':
            data = service.get_database_stats()
            return success_response(data)
        
        else:
            return error_response(f"Unknown action: {action}", 400)
            
    except Exception as e:
        logger.error(f"Error in {action}: {str(e)}", exc_info=True)
        return error_response(f"Failed to execute {action}: {str(e)}", 500)


def success_response(data: Dict, status_code: int = 200) -> Dict:
    """Build success response"""
    logger.info(f"Success response: {json.dumps(data, default=str)[:500]}")  # Log first 500 chars
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,GET,OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(data, default=str)
    }


def error_response(message: str, status_code: int = 500) -> Dict:
    """Build error response"""
    logger.error(f"Error response ({status_code}): {message}")
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,GET,OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'error': message})
    }
