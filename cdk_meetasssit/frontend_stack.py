# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

"""
FrontendStack - React SPA Frontends (1 S3 Bucket, 2 CloudFront Distributions)
- Admin Dashboard: /admin prefix
- Consultant Portal: /consultant prefix
- Consultant Sync Lambda (outside VPC) for Cognito user management
"""

import os

from aws_cdk import (
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment, 
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_logs as logs,
    custom_resources as cr,
    CustomResource,
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct


class FrontendStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            # Admin
            admin_user_pool: cognito.IUserPool,
            admin_cognito_domain_url: str,
            # Consultant
            consultant_user_pool: cognito.IUserPool,
            consultant_cognito_domain_url: str,
            # Shared
            api_endpoint: str = None,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, description="Frontend Stack - Admin Dashboard & Consultant Portal", **kwargs)
        
        # Asset paths
        admin_asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist", "admin"
        )
        consultant_asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist", "consultant"
        )
        custom_resource_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "custom_resource"
        )
        
        # ==================== SHARED S3 BUCKET ====================
        frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True
        )

        # Shared OAI for CloudFront access
        oai = cloudfront.OriginAccessIdentity(
            self, "FrontendOAI",
            comment="OAI for Frontend Apps"
        )
        
        frontend_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{frontend_bucket.bucket_arn}/*"],
            principals=[iam.CanonicalUserPrincipal(
                oai.cloud_front_origin_access_identity_s3_canonical_user_id
            )]
        ))
        
        # Common error response for SPA
        spa_error_responses = [
            cloudfront.ErrorResponse(http_status=403, response_http_status=200, response_page_path="/index.html"),
            cloudfront.ErrorResponse(http_status=404, response_http_status=200, response_page_path="/index.html"),
        ]

        # ==================== ADMIN DASHBOARD ====================
        admin_distribution = cloudfront.Distribution(
            self, "AdminDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    frontend_bucket, 
                    origin_access_identity=oai,
                    origin_path="/admin"
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
            ),
            error_responses=spa_error_responses
        )

        admin_client = cognito.CfnUserPoolClient(
            self, "AdminAppClient",
            user_pool_id=admin_user_pool.user_pool_id,
            client_name="MeetAssist-AdminClient",
            generate_secret=False,
            allowed_o_auth_flows=["code"],
            allowed_o_auth_flows_user_pool_client=True,
            allowed_o_auth_scopes=["openid", "email", "profile"],
            callback_ur_ls=[
                f"https://{admin_distribution.distribution_domain_name}/callback",
                "http://localhost:5173/callback"
            ],
            logout_ur_ls=[
                f"https://{admin_distribution.distribution_domain_name}",
                "http://localhost:5173"
            ],
            supported_identity_providers=["COGNITO"],
            explicit_auth_flows=["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
        )

        # ==================== CONSULTANT PORTAL ====================
        consultant_distribution = cloudfront.Distribution(
            self, "ConsultantDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    frontend_bucket, 
                    origin_access_identity=oai,
                    origin_path="/consultant"
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
            ),
            error_responses=spa_error_responses
        )

        consultant_client = cognito.CfnUserPoolClient(
            self, "ConsultantAppClient",
            user_pool_id=consultant_user_pool.user_pool_id,
            client_name="MeetAssist-ConsultantClient",
            generate_secret=False,
            allowed_o_auth_flows=["code"],
            allowed_o_auth_flows_user_pool_client=True,
            allowed_o_auth_scopes=["openid", "email", "profile"],
            callback_ur_ls=[
                f"https://{consultant_distribution.distribution_domain_name}/callback",
                "http://localhost:5174/callback"
            ],
            logout_ur_ls=[
                f"https://{consultant_distribution.distribution_domain_name}",
                "http://localhost:5174"
            ],
            supported_identity_providers=["COGNITO"],
            explicit_auth_flows=["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"],
            read_attributes=["email", "email_verified", "custom:consultant_id"],
            write_attributes=["email"]
        )

        # ==================== CONFIG GENERATOR ====================
        config_generator_lambda = lambda_.Function(
            self, "ConfigGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="generate_config.handler",
            code=lambda_.Code.from_asset(custom_resource_path),
            timeout=Duration.seconds(30),
            description="Generate config.json for frontends"
        )
        
        config_generator_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[
                    f"{frontend_bucket.bucket_arn}/admin/config.json",
                    f"{frontend_bucket.bucket_arn}/consultant/config.json"
                ]
            )
        )
        
        config_generator_provider = cr.Provider(
            self, "ConfigGeneratorProvider",
            on_event_handler=config_generator_lambda
        )

        # ==================== CONSULTANT SYNC LAMBDA (OUTSIDE VPC) ====================
        # Lambda to manage Consultant Cognito users - runs outside VPC to access Cognito API
        # Must be created BEFORE admin config to include sync API endpoint
        sync_lambda_role = iam.Role(
            self,
            "ConsultantSyncRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        sync_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminDeleteUser",
                    "cognito-idp:AdminDisableUser",
                    "cognito-idp:AdminEnableUser",
                    "cognito-idp:AdminGetUser",
                    "cognito-idp:AdminUpdateUserAttributes",
                    "cognito-idp:AdminSetUserPassword",
                    "cognito-idp:ListUsers",
                ],
                resources=[consultant_user_pool.user_pool_arn],
            )
        )

        sync_lambda = lambda_.Function(
            self,
            "ConsultantSyncLambda",
            function_name="ConsultantCognitoSync",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="sync_consultant_cognito.lambda_handler",
            code=lambda_.Code.from_asset(custom_resource_path),
            role=sync_lambda_role,
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Sync Consultants to Cognito User Pool (outside VPC)",
            environment={
                "CONSULTANT_USER_POOL_ID": consultant_user_pool.user_pool_id,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        sync_api = apigw.RestApi(
            self,
            "ConsultantSyncApi",
            rest_api_name="ConsultantSyncAPI",
            description="API for managing Consultant Cognito users",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=["POST", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        sync_resource = sync_api.root.add_resource("sync")
        sync_integration = apigw.LambdaIntegration(sync_lambda, proxy=True)
        sync_resource.add_method("POST", sync_integration)

        # ==================== DEPLOY UI & CONFIG ====================
        # Deploy Admin UI
        admin_deployment = s3_deployment.BucketDeployment(
            self, "DeployAdminUI",
            sources=[s3_deployment.Source.asset(admin_asset_path)],
            destination_bucket=frontend_bucket,
            destination_key_prefix="admin",
            distribution=admin_distribution,
            distribution_paths=["/*"],
            memory_limit=1024,
            prune=False
        )

        # Admin config - includes SyncApiEndpoint for Cognito user management
        admin_config_cr = CustomResource(
            self, "AdminConfigResource",
            service_token=config_generator_provider.service_token,
            properties={
                "Region": self.region,
                "CognitoUserPoolId": admin_user_pool.user_pool_id,
                "CognitoClientId": admin_client.ref,
                "CognitoDomain": admin_cognito_domain_url,
                "CloudFrontUrl": f"https://{admin_distribution.distribution_domain_name}",
                "BucketName": frontend_bucket.bucket_name,
                "KeyPrefix": "admin",
                "ApiEndpoint": api_endpoint or "https://placeholder.execute-api.ap-southeast-1.amazonaws.com/prod",
                "SyncApiEndpoint": f"{sync_api.url}sync",
                "PortalType": "admin"
            }
        )
        admin_config_cr.node.add_dependency(admin_deployment)

        # Deploy Consultant UI
        consultant_deployment = s3_deployment.BucketDeployment(
            self, "DeployConsultantUI",
            sources=[s3_deployment.Source.asset(consultant_asset_path)],
            destination_bucket=frontend_bucket,
            destination_key_prefix="consultant",
            distribution=consultant_distribution,
            distribution_paths=["/*"],
            memory_limit=1024,
            prune=False
        )

        # Consultant config
        consultant_config_cr = CustomResource(
            self, "ConsultantConfigResource",
            service_token=config_generator_provider.service_token,
            properties={
                "Region": self.region,
                "CognitoUserPoolId": consultant_user_pool.user_pool_id,
                "CognitoClientId": consultant_client.ref,
                "CognitoDomain": consultant_cognito_domain_url,
                "CloudFrontUrl": f"https://{consultant_distribution.distribution_domain_name}",
                "BucketName": frontend_bucket.bucket_name,
                "KeyPrefix": "consultant",
                "ApiEndpoint": api_endpoint or "https://placeholder.execute-api.ap-southeast-1.amazonaws.com/prod",
                "PortalType": "consultant"
            }
        )
        consultant_config_cr.node.add_dependency(consultant_deployment)

        # ==================== OUTPUTS ====================
        CfnOutput(self, "FrontendBucketName",
            value=frontend_bucket.bucket_name,
            description="Frontend S3 Bucket Name")
        
        CfnOutput(self, "AdminDashboardURL",
            value=f"https://{admin_distribution.distribution_domain_name}",
            description="Admin Dashboard URL")
        CfnOutput(self, "AdminCognitoClientId",
            value=admin_client.ref,
            description="Admin Cognito App Client ID")
        
        CfnOutput(self, "ConsultantPortalURL",
            value=f"https://{consultant_distribution.distribution_domain_name}",
            description="Consultant Portal URL")
        CfnOutput(self, "ConsultantCognitoClientId",
            value=consultant_client.ref,
            description="Consultant Cognito App Client ID")
        
        CfnOutput(self, "ConsultantSyncApiEndpoint",
            value=f"{sync_api.url}sync",
            description="API endpoint for Consultant Cognito Sync")
