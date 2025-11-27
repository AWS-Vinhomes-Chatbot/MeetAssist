import json
import ast
import re
from typing import Dict, Any, Union, List, Tuple
class CacheService:
    """Service for caching and retrieving data from Redis cluster."""
    def __init__(self, ):
        self.llm_model = None
        self.logger = None
        self.session_table = None
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
    def prompt_format(self,):
        prompt =
    def 
