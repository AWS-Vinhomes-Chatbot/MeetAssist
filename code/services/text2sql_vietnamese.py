# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * (Giữ nguyên phần license)
#  */

import json
import ast
import re
from typing import Dict, Any, Union, List, Tuple

from psycopg.connection import Connection


class TextToSQL:
    """A class for converting natural language queries to SQL, executing them, and describing results.

    This class uses Amazon Bedrock to generate SQL from natural language text,
    executes the generated SQL queries, and then describes the results in natural language.

    Attributes:
        bedrock_client: Client for Bedrock runtime service.
        logger (logging.Logger): Logger object for logging messages.
        secret_client: Client for accessing AWS Secrets Manager.
    """

    def __init__(self,
                 secret_client,
                 bedrock_client,
                 log):
        """Initialize the TextToSQL class.

        Args:
            secret_client: Client for accessing secrets.
            bedrock_client: Client for Bedrock runtime service.
            log (logging.Logger): Logger object for logging messages.
        """
        self.bedrock_client = bedrock_client
        self.logger = log
        self.secret_client = secret_client

    @staticmethod
    def __generate_sql_prompt(query, schema):
        """Generate a prompt to create a SQL statement.

        Args:
            query: The natural language query to convert to SQL
            schema: The database schema

        Returns:
            A dictionary containing the prompt for the model
        """
        # LLM prompt, not SQL, hence nosec here
        sql_prompt_text = f"""
        Hãy viết một câu lệnh SQL cho tác vụ sau đây, với tư cách là một quản trị viên CSDL chuyên nghiệp và có ý thức bảo mật cao.

        ## Hướng dẫn chung:
        - Chỉ cho phép INSERT, UPDATE, DELETE trên các bảng/cột liên quan đến lịch hẹn (ví dụ: bảng "Appointment" với cột như "AppointmentID", "Status", "Date", "UserID", "ConsultantID", v.v. – dựa trên schema).
        - Ví dụ: INSERT để đặt lịch mới, DELETE để hủy lịch, UPDATE để thay đổi thông tin lịch (như ngày giờ, trạng thái).
        - Đối với tất cả các bảng/cột khác (không liên quan đến lịch hẹn), CHỈ cho phép SELECT. Từ chối INSERT/UPDATE/DELETE trên chúng. 
        - Không bao giờ truy vấn tất cả các cột (`SELECT *`) từ một bảng; chỉ yêu cầu các cột có liên quan đến câu hỏi.

        ## Yêu cầu bảo mật:
        - Sử dụng placeholder `%s` cho các tham số (tương thích với psycopg3).
        - Không bao giờ nối chuỗi đầu vào của người dùng trực tiếp vào câu truy vấn.
        - Đặt tất cả đầu vào của người dùng làm tham số, bao gồm:
          * Các cụm từ tìm kiếm/bộ lọc (ví dụ: tên tư vấn viên, trạng thái cuộc hẹn).
          * Tên cột cho `ORDER BY`.
          * Giá trị `LIMIT`/`OFFSET`.
        - XÁC MINH RẰNG tất cả các bảng và cột đều tồn tại trong schema được cung cấp trước khi tham chiếu chúng.
        - Khi so sánh văn bản (string) Tiếng Việt, hãy luôn dùng hàm `LOWER()` hoặc `UPPER()` để chuẩn hóa (ví dụ: `LOWER(column_name) = LOWER(%s)`).

        ## Hướng dẫn Cú pháp PostgreSQL (Rất quan trọng):
        - Chỉ sử dụng cú pháp tương thích với PostgreSQL.
        - Đối với các phép tính ngày tháng và tuổi (ví dụ: tính tuổi của tư vấn viên):
          * Dùng `AGE(end_date, start_date)` để lấy khoảng thời gian.
          * Dùng `DATE_PART('year', AGE(timestamp))` để lấy tuổi (ví dụ: `DATE_PART('year', AGE(a.DateOfBirth))` để lấy tuổi của Account).
        - Đối với các phép tính tổng hợp và `GROUP BY`:
          * Quy tắc quan trọng: Mọi cột trong `SELECT` không nằm trong hàm tổng hợp (aggregate function) BẮT BUỘC phải nằm trong mệnh đề `GROUP BY`.
          * Khi dùng `CASE` với `GROUP BY`, hãy dùng CTE (subquery) để đặt bí danh (alias) cho biểu thức `CASE`, sau đó `GROUP BY` theo bí danh đó.
          * Ví dụ (đếm số lượng cuộc hẹn theo trạng thái):
            ```sql
            WITH appointments_with_status AS (
              SELECT 
                  CASE 
                      WHEN "Status" = 'completed' THEN 'Đã hoàn thành'
                      WHEN "Status" = 'pending' THEN 'Đang chờ'
                      WHEN "Status" = 'rejected' THEN 'Đã từ chối'
                      ELSE 'Khác'
                  END AS trang_thai,
                  "AppointmentID"
              FROM "Appointment"
            )
            SELECT 
                trang_thai, 
                COUNT("AppointmentID") as so_luong
            FROM appointments_with_status
            GROUP BY trang_thai
            ```
        - Lưu ý tên bảng và cột có chữ hoa: Nếu tên bảng hoặc cột trong schema có chữ hoa (ví dụ: "Account", "FullName", "RoleID"), chúng BẮT BUỘC phải được đặt trong dấu ngoặc kép (`""`).
          * Ví dụ đúng: `SELECT "FullName" FROM "Account" WHERE "AccountID" = %s`
          * Ví dụ sai: `SELECT FullName FROM Account WHERE AccountID = %s`

        ## Định dạng phản hồi:
        Đầu tiên: Phân tích kỹ schema được cung cấp để xác định tất cả các bảng và cột có sẵn.
        Không tham chiếu bất kỳ bảng hoặc cột nào không tồn tại trong schema này.
        Thứ hai: Xem xét các định dạng dữ liệu thực tế và phân biệt chữ hoa/thường trong các giá trị CSDL.

        Vui lòng phản hồi với:
        1. <sql>Câu truy vấn SQL của bạn ở đây</sql>
        2. <params>[param1, param2, ...]</params>
        3. <validation>Một xác thực ngắn gọn xác nhận rằng placeholder khớp với tham số và tất cả các bảng/cột đều tồn tại</validation>

        Đây là tác vụ:
        <task>
        Bạn là một chuyên gia SQL tập trung vào bảo mật. Một CSDL PostgreSQL được tạo với các bảng và cột sau:
        {schema}

        Viết một câu truy vấn SQL có tham số (dùng `%s`) trả về kết quả tốt nhất dựa trên yêu cầu sau của người dùng:
        {query}

        Hãy kiểm tra kỹ công việc của bạn để đảm bảo:
        1. MỌI bảng và cột bạn tham chiếu ĐỀU TỒN TẠI trong schema ở trên (lưu ý dùng dấu `""` cho tên có chữ hoa).
        2. Số lượng placeholder `%s` KHỚP CHÍNH XÁC với số lượng tham số bạn cung cấp.
        3. Không có lỗ hổng SQL injection.
        4. Xử lý đúng việc so sánh chuỗi Tiếng Việt (dùng `LOWER` hoặc `UPPER`).
        </task>
        """  # nosec

        return {"type": "text", "text": sql_prompt_text}

    @staticmethod
    def __generate_text_prompt(query, schema, results):
        """Tạo prompt từ kết quả truy vấn SQL bằng ngôn ngữ tự nhiên (Tiếng Việt).

        Args:
            query: The original SQL query
            schema: The database schema
            results: The results of the SQL query

        Returns:
            A dictionary containing the prompt for the AI
        """
        return {"type": "text", "text": f"""
               Human: Bạn là một quản trị viên CSDL rất lành nghề và là một chuyên viên tư vấn đặt lịch hẹn.
               Các hàng dưới đây đã được trả về cho câu truy vấn SQL sau:
               {str(results)}
               {str(query)}
               Schema cho CSDL như sau: {schema}
               Chỉ mô tả kết quả bằng ngôn ngữ tự nhiên (Tiếng Việt).
               KHÔNG mô tả câu truy vấn, schema CSDL, hay bất kỳ khía cạnh kỹ thuật nào của CSDL.
               Assistant:
               """}

    def __call_bedrock(self, prompt: Dict[str, Any]) -> str:
        """Call the Bedrock service with a given prompt.

        Args:
            prompt (Dict[str, Any]): The prompt to send to Bedrock.

        Returns:
            str: The text content of the response.
        """
        body = {"messages": [{"role": "user", "content": [prompt]}], "max_tokens": 2048, "top_k": 250, "top_p": 1,
                "stop_sequences": ["\\n\\nHuman:"], "anthropic_version": "bedrock-2023-05-31"}
        response = self.bedrock_client.invoke_model(
            body=json.dumps(body),
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            accept="application/json",
            contentType="application/json",
        )
        body = response["body"].read().decode("utf-8")
        text_content = json.loads(body)["content"][0]["text"]
        return text_content

    def check_if_follow_up_question(self, full_prompt: str) -> Dict[str, Any]:
        """Check if this is a follow-up question that can be answered directly.

        Args:
            full_prompt (str): The full conversation history with the current question.

        Returns:
            Dict[str, Any]: Dictionary with is_follow_up flag and answer if applicable.
        """
        prompt = {"type": "text", "text": f"""
            Human: Bạn đang xem xét một cuộc hội thoại để xác định xem câu hỏi mới nhất có phải là câu hỏi tiếp nối (follow-up) có thể được trả lời trực tiếp từ ngữ cảnh hội thoại mà không cần truy vấn CSDL hay không. Hãy phân tích cẩn thận:

            {full_prompt}

            Nhiệm vụ của bạn:
            1. Xác định xem câu hỏi mới nhất có phải là câu hỏi tiếp nối có thể được trả lời trực tiếp bằng thông tin đã có trong hội thoại không.
            2. Nếu ĐÚNG là câu hỏi tiếp nối có thể trả lời trực tiếp, hãy cung cấp câu trả lời (bằng Tiếng Việt) dựa trên ngữ cảnh hội thoại.
            3. Nếu KHÔNG phải là câu hỏi tiếp nối HOẶC yêu cầu thông tin CSDL mới, hãy nêu rõ rằng cần phải truy vấn CSDL.

            Phản hồi ở định dạng JSON:
            (LƯU Ý: KHÔNG dịch các tên key trong JSON)
            ```
            {{
              "is_follow_up": true/false,
              "answer": "Câu trả lời của bạn nếu là câu hỏi tiếp nối, ngược lại thì null"
            }}
            ```
            Assistant:
        """}

        response = self.__call_bedrock(prompt)

        # Extract JSON from response
        try:
            # Find JSON between triple backticks if present
            json_match = re.search(r'```(?:json)?\s*({\s*"is_follow_up".*?})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to extract JSON without backticks
                json_match = re.search(r'({[\s\S]*?"is_follow_up"[\s\S]*?})', response)
                json_str = json_match.group(1) if json_match else response

            result = json.loads(json_str)
            return result
        except Exception as e:
            self.logger.error(f"Error parsing follow-up check response: {e}")
            return {"is_follow_up": False, "answer": None}

    def get_sql_from_bedrock(self, query: str, schema: str) -> Union[Tuple[str, List], Dict[str, Any]]:
        """Generate SQL from a natural language query using Bedrock.

        Args:
            query (str): The natural language query.
            schema (str): The database schema.

        Returns:
            Union[Tuple[str, List], Dict[str, Any]]: The generated SQL statement and parameters or an error response dictionary.

        Raises:
            Exception: If there is an error generating SQL from the query.
        """
        # Generate the prompt for Bedrock
        sql_prompt = self.__generate_sql_prompt(query, schema)
        self.logger.debug(sql_prompt)

        # Call Bedrock to generate SQL
        text_content = self.__call_bedrock(sql_prompt)

        # Extract SQL from the AI's response
        sql_regex = re.compile(r"<sql>(.*?)</sql>", re.DOTALL)
        sql_statements = sql_regex.findall(text_content)

        # Extract parameters
        params_regex = re.compile(r"<params>(.*?)</params>", re.DOTALL)
        params_match = params_regex.findall(text_content)

        self.logger.debug(sql_statements)
        self.logger.debug(params_match)

        # Check if SQL was successfully generated
        if not sql_statements:
            return {"statusCode": 500,
                    "body": {"response": "Unable to generate SQL for the provided prompt, please try again."},
                    "headers": {"Content-Type": "application/json"}}

        # Parse parameters if available, otherwise return empty list
        params = []
        if params_match:
            try:
                # Safely evaluate the parameter list (should be a Python list literal)
                params = ast.literal_eval(params_match[0])
            except Exception as e:
                self.logger.error(f"Error parsing parameters: {e}")
                self.logger.error(f"Raw parameters string: {params_match[0]}")
                # Continue with empty params rather than failing

        # Return the SQL and parameters
        return sql_statements[0], params

    def execute_sql(self, conn: Connection, sql_data) -> Tuple[List[Tuple], List[str]]:
        """Execute SQL statements on a given database connection.

        Args:
            conn (connection): The database connection.
            sql_data: Either a SQL string or a tuple of (SQL, parameters)

        Returns:
            Tuple[List[Tuple], List[str]]: The results of the SQL execution and column names.

        Raises:
            Exception: If there is an error executing the SQL statements.
        """
        sql = sql_data
        params = []

        # Check if we have parameters
        if isinstance(sql_data, tuple) and len(sql_data) == 2:
            sql, params = sql_data

        self.logger.info(f"Executing SQL: {sql}")
        self.logger.info(f"With parameters: {params}")

        cursor = conn.cursor()
        cursor.execute(sql, params)

        # Fetch results if available
        results = []
        column_names = []

        if cursor.description:  # Check if the query returned any rows
            results = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]

        self.logger.info(f"Results: {results}")
        self.logger.info(f"Column names: {column_names}")
        return results, column_names

    def describe_results_from_query(self, sql_statements: str, results_tuple: Tuple[List[Tuple], List[str]],
                                    schema: str) -> Dict[str, Any]:
        """Generate a natural language description of SQL query results.

        Args:
            sql_statements (str): The SQL statements that were executed.
            results_tuple (Tuple[List[Tuple], List[str]]): The results of the SQL query and column names.
            schema (str): The database schema.

        Returns:
            Dict[str, Any]: A dictionary containing the response, query, results, column names, and headers.

        Raises:
            Exception: If there is an error generating the description of the query results.
        """
        results, column_names = results_tuple
        text_prompt = self.__generate_text_prompt(sql_statements, schema, results)
        text_content = self.__call_bedrock(text_prompt)
        # định dạng format JSON cho dễ dùng phía client
        return {"statusCode": 200,
                "body": {"response": text_content,
                         "query": sql_statements,
                         "query_results": results,
                         "column_names": column_names,
                         "cache_id": None},
                "headers": {"Content-Type": "application/json"}}