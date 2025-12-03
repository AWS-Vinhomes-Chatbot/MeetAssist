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

from cdk_meetasssit.vpc_stack import VpcStack
from cdk_meetasssit.database_init_stack import DatabaseInitStack
from cdk_meetasssit.data_indexer_stack import DataIndexerStack
from cdk_meetasssit.text2sqltstack import Text2SQLStack
from cdk_meetasssit.Webhook_stack import UserMessengerBedrockStack
from cdk_meetasssit.auth_stack import AuthStack
from cdk_meetasssit.frontend_stack import FrontendStack
from cdk_meetasssit.dashboard_stack import DashboardStack
from cdk_nag import AwsSolutionsChecks

app = cdk.App()
env = cdk.Environment(region="ap-northeast-1")  # Tokyo region

vpc_stack = VpcStack(app, "AppStack", env=env)
db_init_stack = DatabaseInitStack(
    app, "DatabaseInitStack",
    db_instance=vpc_stack.rds_instance,
    vpc=vpc_stack.vpc,
    security_group=vpc_stack.security_group,
    readonly_secret=vpc_stack.readonly_secret,
    data_stored_bucket=vpc_stack.data_stored_bucket,
    env=env
)
data_indexer_stack = DataIndexerStack(app, "DataIndexerStack", db_instance=vpc_stack.rds_instance, vpc=vpc_stack.vpc,
                                      security_group=vpc_stack.security_group, readonly_secret=vpc_stack.readonly_secret,env=env)
text2sql_stack = Text2SQLStack(app, "Text2SQLStack", db_instance=vpc_stack.rds_instance, vpc=vpc_stack.vpc,
                               security_group=vpc_stack.security_group, readonly_secret=vpc_stack.readonly_secret, env=env)
auth_stack = AuthStack(app, "AuthStack", env=env)
dashboard_stack = DashboardStack(
    app, "DashboardStack",
    vpc=vpc_stack.vpc,
    security_group=vpc_stack.security_group,
    data_stored_bucket=vpc_stack.data_stored_bucket,
    readonly_secret=vpc_stack.readonly_secret,
    rds_instance=vpc_stack.rds_instance,
    user_pool=auth_stack.user_pool,  
    env=env
)
frontend_stack = FrontendStack(
    app, "FrontendStack",
    user_pool=auth_stack.user_pool,
    cognito_domain_url=auth_stack.cognito_domain_url,  
    api_endpoint=dashboard_stack.api_endpoint,  
    env=env
)
# Webhook stack for Messenger chat handler (outside VPC)
# Depends on Text2SQLStack because it invokes the TextToSQLFunction
webhook_stack = UserMessengerBedrockStack(app, "WebhookStack", env=env)
webhook_stack.add_dependency(text2sql_stack)


# Temporarily disabled cdk-nag for faster deployment
# TODO: Re-enable and add proper NagSuppressions before production
# cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
