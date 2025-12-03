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

import json
import logging
import os
from typing import List, Optional

import boto3
import botocore.client

logger = logging.getLogger()

# Module-level singleton for Bedrock client (reuse across Lambda invocations)
_bedrock_embed_client = None


def get_bedrock_embed_client(region: str = None):
    """
    Get or create Bedrock Runtime client singleton for embedding.
    
    This is reused across Lambda invocations to improve performance.
    Uses Amazon Titan Text Embeddings V2 in ap-northeast-1 (Tokyo).
    
    Args:
        region: AWS region (default: ap-northeast-1)
    
    Returns:
        boto3 Bedrock Runtime client instance
    """
    global _bedrock_embed_client
    if _bedrock_embed_client is None:
        region = region or os.environ.get("BEDROCK_EMBED_REGION", "ap-northeast-1")
        _bedrock_embed_client = boto3.client('bedrock-runtime', region_name=region)
        logger.info(f"Created Bedrock Embed client for region: {region}")
    return _bedrock_embed_client


class EmbeddingService:
    """
    A service for generating embeddings using Amazon Bedrock.

    This class provides functionality to generate embeddings for given text inputs
    using the Amazon Titan embedding model through Bedrock.

    Attributes:
        logger (logging.Logger): Logger for logging debug and error messages.
        bedrock_client (botocore.client.BaseClient): Bedrock runtime client for making API calls.
    """

    def __init__(self, bedrock_client: botocore.client.BaseClient = None, logger: logging.Logger = None):
        """
        Initialize the EmbeddingService.

        Args:
            bedrock_client (botocore.client.BaseClient): Bedrock runtime client for making API calls.
                                                         If None, uses singleton client.
            logger (logging.Logger): Logger for logging debug and error messages.
                                     If None, uses module logger.
        """
        self.logger = logger or logging.getLogger()
        self.bedrock_client = bedrock_client or get_bedrock_embed_client()

    def get_embedding(self, text: str) -> List[float]:
        """Generate an embedding for the given text using Amazon Bedrock.

        This method sends a request to the Amazon Titan Text Embeddings V2 model
        to generate an embedding for the provided text.

        Args:
            text (str): The text to generate an embedding for.

        Returns:
            List[float]: The generated embedding as a list of floats (1024 dimensions).

        Raises:
            Exception: If there is an error in generating the embedding.
        """
        try:
            self.logger.debug(f"Generating embedding for {text}")
            # Amazon Titan Text Embeddings V2 (supports multilingual, available in ap-northeast-1)
            response = self.bedrock_client.invoke_model(
                body=json.dumps({
                    "inputText": text,
                    "dimensions": 1024,
                    "normalize": True
                }),
                contentType="application/json",
                accept="application/json",
                modelId="amazon.titan-embed-text-v2:0"
            )
            response_body = json.loads(response["body"].read())
            # Titan V2 returns embedding directly
            embedding = response_body["embedding"]
            self.logger.debug(f"Embedding generated: {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            self.logger.error(f"Error generating embedding: {e}")
            raise
