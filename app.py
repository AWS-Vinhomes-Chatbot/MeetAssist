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

from cdk_rds_pg_memdb_text_to_sql.frontend_stack import FrontendStack
from cdk_rds_pg_memdb_text_to_sql.dashboard_stack import DashboardStack
from cdk_rds_pg_memdb_text_to_sql.vpc_stack import AppStack
from cdk_rds_pg_memdb_text_to_sql.database_init_stack import DatabaseInitStack
# from cdk_rds_pg_memdb_text_to_sql.data_indexer_stack import DataIndexerStack
# from cdk_nag import AwsSolutionsChecks

app = cdk.App()

env = cdk.Environment(region="ap-southeast-1")

# ==================== FRONTEND STACK ====================
# Deploy FrontendStack để có frontend + Cognito
frontend_stack = FrontendStack(app, "FrontendStack", env=env)

# ==================== VPC + RDS STACK ====================
vpc_stack = AppStack(app, "AppStack", env=env)

# ==================== DATABASE INIT STACK ====================
# Tự động tạo schema + import data từ CSV files trong S3
# Upload CSV vào s3://bucket-name/data/customer.csv, consultant.csv, ...
db_init_stack = DatabaseInitStack(
    app, "DatabaseInitStack",
    db_instance=vpc_stack.rds_instance,
    vpc=vpc_stack.vpc,
    security_group=vpc_stack.security_group,
    readonly_secret=vpc_stack.readonly_secret,
    data_stored_bucket=vpc_stack.data_stored_bucket,
    env=env
)
db_init_stack.add_dependency(vpc_stack)

# ==================== Dashboard Stack ====================
# Deploy Lambda AdminManager + API Gateway
dashboard_stack = DashboardStack(
    app, "DashboardStack",
    vpc=vpc_stack.vpc,
    security_group=vpc_stack.security_group,
    data_stored_bucket=vpc_stack.data_stored_bucket,
    readonly_secret=vpc_stack.readonly_secret,
    rds_instance=vpc_stack.rds_instance,
    user_pool=frontend_stack.user_pool,
    env=env
)
dashboard_stack.add_dependency(frontend_stack)
dashboard_stack.add_dependency(db_init_stack) 

# Comment tạm các stack khác
# data_indexer_stack = DataIndexerStack(app, "DataIndexerStack", db_instance=app_stack.rds_instance, vpc=app_stack.vpc,
#                                       security_group=app_stack.security_group, readonly_secret=app_stack.readonly_secret,env=env)
# cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

app.synth()
