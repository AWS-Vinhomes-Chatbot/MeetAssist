# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  * software and associated documentation files (the "Software"), to deal in the Software
#  * without restriction, including without limitation the rights to use, copy, modify,
#  * merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  * permit persons to whom the Software is furnished to do so.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  * INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#  */

"""
Text2SQL Lambda Handler

This Lambda is invoked by chat_handler when intent is "schedule_type".
It receives user_message and context, generates SQL, executes query,
and returns natural language response.

Expected event payload from chat_handler:
{
    "psid": "user_psid",
    "question": "user's question about schedule",
    "context": "Turn 1: User: ... | Assistant: ...\nTurn 2: ..."
}

Response format:
{
    "statusCode": 200,
    "body": {
        "response": "Natural language answer",
        "sql": "SELECT ...",
       
    }
}
"""

import os
import json
from typing import Any, Dict

import boto3
from services.bedrock_service import BedrockService
from services.embed import EmbeddingService
from services.indexer import DataIndexerService
from repositories.postgres import PostgreSQLService
from util.lambda_logger import create_logger
from util.postgres_validation import is_valid_postgres_identifier

# Get the Lambda function name from the environment
lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "Text2SQLHandler")

# Setup logging
logger = create_logger(lambda_function_name)

# Initialize AWS clients
session = boto3.session.Session()
bedrock_client = session.client("bedrock-runtime")
sm_client = session.client("secretsmanager")

# Environment variables
RDS_HOST = os.getenv("RDS_HOST")
RDS_DATABASE_NAME = os.getenv("DB_NAME", "postgres")
RDS_SCHEMA = os.getenv("DB_SCHEMA", "public")
SECRET_NAME = os.getenv("SECRET_NAME")

# Initialize services
embed = EmbeddingService(bedrock_client=bedrock_client, logger=logger)
index = DataIndexerService(embedding_service=embed, log=logger)
pg = PostgreSQLService(secret_client=sm_client, db_host=RDS_HOST, db_name=RDS_DATABASE_NAME, log=logger)

# Text2SQL uses Claude Sonnet for complex SQL generation
text_to_sql = BedrockService(
    model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=4096,
    temperature=0.3
)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for Text-to-SQL processing.
    
    Invoked by chat_handler Lambda when user intent is "schedule_type".
    Receives user question and conversation context, generates SQL,
    executes query, and returns natural language response.

    Args:
        event: Event payload containing:
            - psid (str): User's PSID
            - question (str): User's question about schedule
            - context (str): Conversation context string from session_service.get_context_for_llm()
        context: Lambda context object

    Returns:
        Dict with statusCode and body containing:
            - response (str): Natural language answer
            - sql (str): Generated SQL query
            - row_count (int): Number of rows returned

    Raises:
        Exception: If database connection fails or SQL generation fails
    """
    logger.info("Text2SQL Lambda invoked")
    logger.debug(f"Event: {event}")

    # Extract parameters from event (sent by chat_handler)
    psid = event.get("psid", "")
    user_message = event.get("question", "")
    conversation_context = event.get("context", "")
    is_mutation = event.get("mutation", False)
    appointment_info = event.get("appointment_info", {})
    
    if not user_message:
        logger.error("No question provided in event")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "response": "Không có câu hỏi được cung cấp.",
                "error": "missing_question"
            }),
            "headers": {"Content-Type": "application/json"}
        }
    
    # Handle mutation requests (INSERT/UPDATE/DELETE for appointments)
    if is_mutation:
        logger.info(f"Processing mutation request for {psid}")
        return _handle_mutation(psid, user_message, appointment_info)
    
    logger.info(f"Processing question for {psid}: '{user_message[:50]}...'")
    logger.debug(f"Context: {conversation_context[:200]}..." if conversation_context else "No context")

    # Validate database identifiers
    if not (is_valid_postgres_identifier(RDS_DATABASE_NAME) and is_valid_postgres_identifier(RDS_SCHEMA)):
        logger.error(f"Invalid PostgreSQL identifiers: schema={RDS_SCHEMA}, db={RDS_DATABASE_NAME}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "response": "Lỗi cấu hình hệ thống.",
                "error": "invalid_db_config"
            }),
            "headers": {"Content-Type": "application/json"}
        }
    
    # Connect to database
    pg.set_secret(SECRET_NAME)
    t2sql_conn = pg.connect_to_db()
    if not t2sql_conn:
        logger.error("Failed to connect to database")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "response": "Không thể kết nối đến cơ sở dữ liệu.",
                "error": "db_connection_failed"
            }),
            "headers": {"Content-Type": "application/json"}
        }
    
    try:
        # Combine context with current question for better SQL generation
        full_prompt = user_message
        
        if conversation_context:
            full_prompt = f"Ngữ cảnh hội thoại:\n{conversation_context}\n\nCâu hỏi hiện tại: {user_message}"
        
        # Get schema context using embeddings
        schema_results = index.compare_embeddings(t2sql_conn, user_message)
        
        schema_context = []
        for result in schema_results:
            logger.info(f"Schema result - table: {result.get('table')}, similarity: {result.get('similarity')}")
            logger.debug(f"Schema embedding_text: {result.get('embedding_text', '')[:200]}...")
            schema_context.append(result["embedding_text"])
        schema_context_text = "\n\n".join(schema_context)
        
        # Log schema context for debugging
        logger.info(f"Schema context found: {len(schema_results)} results, total length: {len(schema_context_text)} chars")
        if not schema_context_text:
            logger.warning("No schema context found from embeddings!")
        else:
            # Log first 500 chars of schema context for debugging
            logger.info(f"Schema context preview: {schema_context_text[:500]}...")
        
        # Generate SQL from natural language using Bedrock
        sql_result = text_to_sql.get_sql_from_bedrock(full_prompt, schema_context_text)
        
        # Check if SQL generation failed (returns dict with error)
        if isinstance(sql_result, dict) and sql_result.get("statusCode") == 500:
            logger.error(f"Failed to generate SQL. Response: {sql_result}")
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "response": "Không thể tạo truy vấn SQL cho câu hỏi này. Vui lòng thử lại.",
                    "error": "sql_generation_failed"
                }),
                "headers": {"Content-Type": "application/json"}
            }
        
        # sql_result is tuple (sql, params)
        sql_query, sql_params = sql_result
        logger.info(f"Generated SQL: {sql_query}")
        logger.info(f"SQL params: {sql_params}")
        
        # Execute the SQL statement
        sql_response, column_names = text_to_sql.execute_sql(t2sql_conn, (sql_query, sql_params))
        logger.info(f"Query returned {len(sql_response)} rows")
        logger.debug(f"Column names: {column_names}")
        
        # Format SQL response as list of dicts for easier processing
        formatted_results = []
        for row in sql_response:
            row_dict = dict(zip(column_names, row))
            formatted_results.append(row_dict)
        
        # Return response matching docstring format
        return {
            "statusCode": 200,
            "body": json.dumps({
                "sql_result": formatted_results,
                "question": user_message,
                "schema_context_text": schema_context_text
            }, ensure_ascii=False, default=str),
            "headers": {"Content-Type": "application/json"}
        }
        
    except Exception as e:
        logger.error(f"Error processing Text2SQL request: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "response": "Đã xảy ra lỗi khi xử lý câu hỏi của bạn.",
                "error": str(e)
            }),
            "headers": {"Content-Type": "application/json"}
        }
    finally:
        # Close database connection
        if t2sql_conn:
            try:
                t2sql_conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")


def _handle_mutation(psid: str, mutation_request: str, appointment_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle mutation requests (INSERT/UPDATE/DELETE) for appointment booking.
    
    Args:
        psid: User's PSID
        mutation_request: Natural language mutation request
        appointment_info: Appointment info template with collected data
        
    Returns:
        Response dict with statusCode and body
    """
    logger.info(f"Processing mutation for {psid}: {mutation_request[:100]}...")
    logger.debug(f"Appointment info: {appointment_info}")
    
    # Connect to database
    pg.set_secret(SECRET_NAME)
    mutation_conn = pg.connect_to_db()
    if not mutation_conn:
        logger.error("Failed to connect to database for mutation")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "response": "Không thể kết nối đến cơ sở dữ liệu.",
                "error": "db_connection_failed",
                "appointment_info": appointment_info
            }),
            "headers": {"Content-Type": "application/json"}
        }
    
    try:
        # Get schema context for mutation tables - only need appointment and customer
        # Simplified: no longer need consultantschedule for mutations
        mutation_tables = ["appointment", "customer"]
        schema_results = index.compare_embeddings(mutation_conn, mutation_request, top_k=2, table_filter=mutation_tables)
        schema_context = []
        for result in schema_results:
            schema_context.append(result["embedding_text"])
        schema_context_text = "\n\n".join(schema_context)
        
        logger.info(f"Schema context for mutation: {len(schema_results)} results")
        
        # Get SQL from Bedrock using mutation-specific prompt with appointment info
        sql_result = text_to_sql.get_mutation_sql_from_bedrock(
            query=mutation_request,
            schema=schema_context_text,
            customer_id=psid,  # Use psid as customer identifier
            appointment_info=appointment_info  # Pass collected appointment info
        )
        
        # Check if SQL generation failed
        if isinstance(sql_result, dict) and sql_result.get("statusCode"):
            logger.error(f"Failed to generate mutation SQL: {sql_result}")
            return {
                "statusCode": sql_result.get("statusCode", 500),
                "body": json.dumps({
                    "response": sql_result.get("body", {}).get("response", "Không thể tạo lệnh đặt lịch."),
                    "error": "mutation_sql_generation_failed",
                    "appointment_info": appointment_info
                }),
                "headers": {"Content-Type": "application/json"}
            }
        
        sql_query, sql_params, operation = sql_result
        logger.info(f"Generated mutation SQL: {sql_query}")
        logger.info(f"Mutation params: {sql_params}")
        logger.info(f"Operation type: {operation}")
        
        # Execute the mutation
        try:
            with mutation_conn.cursor() as cursor:
                cursor.execute(sql_query, sql_params)
                
                # Check if INSERT with RETURNING
                if "RETURNING" in sql_query.upper():
                    result = cursor.fetchone()
                    logger.info(f"Mutation result (RETURNING): {result}")
                    
                    # Handle race condition: if result is None or (None,), slot was taken
                    if result is None or (result and result[0] is None):
                        mutation_conn.rollback()
                        logger.warning(f"Race condition detected: slot already booked")
                        return {
                            "statusCode": 409,
                            "body": json.dumps({
                                "response": "Rất tiếc, slot này vừa bị người khác đặt mất! Vui lòng chọn slot khác.",
                                "error": "slot_already_booked",
                                "appointment_info": appointment_info
                            }, ensure_ascii=False),
                            "headers": {"Content-Type": "application/json"}
                        }
                else:
                    result = cursor.rowcount
                    logger.info(f"Mutation affected {result} rows")
                
                mutation_conn.commit()
                
                # Build success response based on operation type
                booking_action = appointment_info.get("booking_action", "create")
                
                if booking_action == "cancel":
                    success_message = (
                        f"Hủy lịch thành công!\n\n"
                        f"📋 Thông tin lịch hẹn đã hủy:\n"
                        f"🆔 Mã lịch hẹn: #{appointment_info.get('appointment_id')}"
                    )
                elif booking_action == "update":
                    success_message = (
                        f"Đổi lịch thành công!\n\n"
                        f"📋 Thông tin lịch hẹn mới:\n"
                        f"📅 Ngày: {appointment_info.get('appointment_date')}\n"
                        f"🕐 Giờ: {appointment_info.get('appointment_time')}\n"
                        f"👨‍💼 Tư vấn viên: {appointment_info.get('consultant_name')}"
                    )
                else:  # create
                    success_message = (
                        f"Đặt lịch thành công!\n\n"
                        f"📋 Thông tin lịch hẹn:\n"
                        f"👤 Tên: {appointment_info.get('customer_name')}\n"
                        f"📞 SĐT: {appointment_info.get('phone_number')}\n"
                        f"📅 Ngày: {appointment_info.get('appointment_date')}\n"
                        f"🕐 Giờ: {appointment_info.get('appointment_time')}\n"
                        f"👨‍💼 Tư vấn viên: {appointment_info.get('consultant_name')}"
                    )
                
                if appointment_info.get("notes"):
                    success_message += f"\n📌 Ghi chú: {appointment_info.get('notes')}"
                
                return {
                    "statusCode": 200,
                    "body": json.dumps({
                        "response": success_message,
                        "sql": sql_query,
                        "appointment_info": appointment_info,
                        "result": str(result) if result else "success"
                    }, ensure_ascii=False),
                    "headers": {"Content-Type": "application/json"}
                }
                
        except Exception as db_error:
            mutation_conn.rollback()
            error_str = str(db_error).lower()
            logger.error(f"Database error during mutation: {db_error}")
            
            # Check for specific constraint violations
            if "unique" in error_str or "duplicate" in error_str or "uq_consultant_schedule" in error_str:
                # Unique constraint violation - slot already booked
                return {
                    "statusCode": 409,
                    "body": json.dumps({
                        "response": "Rất tiếc, slot này đã được đặt! Vui lòng chọn slot khác.",
                        "error": "slot_already_booked",
                        "appointment_info": appointment_info
                    }, ensure_ascii=False),
                    "headers": {"Content-Type": "application/json"}
                }
            elif "foreign key" in error_str or "violates" in error_str:
                # FK constraint violation - invalid reference
                return {
                    "statusCode": 400,
                    "body": json.dumps({
                        "response": "Thông tin không hợp lệ. Vui lòng kiểm tra lại.",
                        "error": "invalid_reference",
                        "appointment_info": appointment_info
                    }, ensure_ascii=False),
                    "headers": {"Content-Type": "application/json"}
                }
            else:
                return {
                    "statusCode": 500,
                    "body": json.dumps({
                        "response": "Lỗi khi thực hiện đặt lịch. Vui lòng thử lại.",
                        "error": str(db_error),
                        "appointment_info": appointment_info
                    }, ensure_ascii=False),
                    "headers": {"Content-Type": "application/json"}
                }
            
    except Exception as e:
        logger.error(f"Error processing mutation: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "response": "Đã xảy ra lỗi khi xử lý đặt lịch.",
                "error": str(e),
                "appointment_info": appointment_info
            }),
            "headers": {"Content-Type": "application/json"}
        }
    finally:
        if mutation_conn:
            try:
                mutation_conn.close()
                logger.debug("Mutation database connection closed")
            except Exception as e:
                logger.warning(f"Error closing mutation connection: {e}")
