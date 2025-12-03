#!/usr/bin/env python3

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

import aws_cdk as cdk

from cdk_meetasssit.vpc_stack import AppStack
from cdk_meetasssit.database_init_stack import DatabaseInitStack
from cdk_meetasssit.data_indexer_stack import DataIndexerStack
from cdk_meetasssit.text2sqltstack import Text2SQLStack
from cdk_meetasssit.Webhook_stack import UserMessengerBedrockStack
from cdk_nag import AwsSolutionsChecks

app = cdk.App()
env = cdk.Environment(region="ap-northeast-1")  # Tokyo region

app_stack = AppStack(app, "AppStack", env=env)
db_init_stack = DatabaseInitStack(app, "DatabaseInitStack", db_instance=app_stack.rds_instance, vpc=app_stack.vpc,
                                  security_group=app_stack.security_group, readonly_secret=app_stack.readonly_secret,
                                  data_bucket=app_stack.data_stored_bucket, env=env)
data_indexer_stack = DataIndexerStack(app, "DataIndexerStack", db_instance=app_stack.rds_instance, vpc=app_stack.vpc,
                                      security_group=app_stack.security_group, readonly_secret=app_stack.readonly_secret, env=env)

# Text2SQL stack - Lambda for converting natural language to SQL (inside VPC)
text2sql_stack = Text2SQLStack(app, "Text2SQLStack", db_instance=app_stack.rds_instance, vpc=app_stack.vpc,
                               security_group=app_stack.security_group, readonly_secret=app_stack.readonly_secret, env=env)

# Webhook stack for Messenger chat handler (outside VPC)
# Depends on Text2SQLStack because it invokes the TextToSQLFunction
webhook_stack = UserMessengerBedrockStack(app, "WebhookStack", env=env)
webhook_stack.add_dependency(text2sql_stack)

cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
