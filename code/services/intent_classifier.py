"""
Intent Classifier - Determines user intent from message.

Classification types:
- sql_query: Requires database query
- direct_answer: Can be answered from cache/knowledge base
- greeting: Casual greeting
- other: Unknown/unclear intent
"""

import logging
import re
from typing import Dict, Any

logger = logging.getLogger()


class IntentClassifier:
    """Classifies user intent to route to appropriate service."""
    def __init__(self):
         
