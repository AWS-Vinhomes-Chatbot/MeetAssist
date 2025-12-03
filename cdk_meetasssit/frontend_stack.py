# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  */

import os
import json

from aws_cdk import (
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment, 
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_lambda as lambda_,
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
            user_pool: cognito.IUserPool,
            cognito_domain_url: str,  # Nhận domain URL dạng string
            api_endpoint: str = None,  # Nhận từ DashboardStack
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, description="Admin Dashboard Frontend - React SPA with CloudFront", **kwargs)
        
        # Trỏ đến dist folder đã build sẵn
        frontend_asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "admin-dashboard", "dist"
        )
        
        # ==================== S3 + CLOUDFRONT ====================
        # Tạo CloudFront TRƯỚC để có domain cho Cognito callback URLs
        frontend_bucket = s3.Bucket(
            self, "AdminFrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True
        )

        oai = cloudfront.OriginAccessIdentity(
            self, "AdminOAI",
            comment="OAI for Admin Dashboard"
        )
        
        frontend_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{frontend_bucket.bucket_arn}/*"],
            principals=[iam.CanonicalUserPrincipal(
                oai.cloud_front_origin_access_identity_s3_canonical_user_id
            )]
        ))

        distribution = cloudfront.Distribution(
            self, "AdminDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    frontend_bucket,
                    origin_access_identity=oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html"
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html"
                ),
            ]
        )

        # ==================== COGNITO APP CLIENT ====================
        # Tạo Cognito client trong FrontendStack (không dùng user_pool.add_client để tránh cyclic dependency)
        # Dùng CfnUserPoolClient để tạo client trong stack này
        # Lưu ý: CDK dùng callback_ur_ls (không phải callback_urls) do cách convert từ CloudFormation
        user_pool_client = cognito.CfnUserPoolClient(
            self, "AdminAppClient",
            user_pool_id=user_pool.user_pool_id,
            client_name="MeetAssist-AdminClient",
            generate_secret=False,
            allowed_o_auth_flows=["code"],
            allowed_o_auth_flows_user_pool_client=True,
            allowed_o_auth_scopes=["openid", "email", "profile"],
            callback_ur_ls=[
                f"https://{distribution.distribution_domain_name}/callback",
                "http://localhost:5173/callback"  # Local development
            ],
            logout_ur_ls=[
                f"https://{distribution.distribution_domain_name}",
                "http://localhost:5173"
            ],
            supported_identity_providers=["COGNITO"],
            explicit_auth_flows=[
                "ALLOW_REFRESH_TOKEN_AUTH",
                "ALLOW_USER_SRP_AUTH"
            ]
        )

        # ==================== GENERATE CONFIG.JSON ====================
        # Tạo config.json với thông tin Cognito + API endpoint
        # API endpoint được truyền trực tiếp từ DashboardStack
        custom_resource_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "custom_resource"
        )
        
        config_generator_lambda = lambda_.Function(
            self, "ConfigGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="generate_config.handler",
            code=lambda_.Code.from_asset(custom_resource_path),
            timeout=Duration.seconds(30),
            description="Generate config.json for frontend"
        )
        
        # Grant permissions - chỉ cần S3, không cần SSM nữa
        config_generator_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"{frontend_bucket.bucket_arn}/config.json"]
            )
        )
        
        # Sử dụng cr.Provider để wrap Lambda
        # Provider sẽ tự động xử lý cfnresponse, Lambda chỉ cần return dict
        config_generator_provider = cr.Provider(
            self, "ConfigGeneratorProvider",
            on_event_handler=config_generator_lambda
        )
        
        # Custom Resource để generate config
        # API endpoint được truyền trực tiếp, không cần đọc SSM
        config_generator_cr = CustomResource(
            self, "ConfigGeneratorResource",
            service_token=config_generator_provider.service_token,
            properties={
                "Region": self.region,
                "CognitoUserPoolId": user_pool.user_pool_id,
                "CognitoClientId": user_pool_client.ref,  # Dùng .ref cho CfnUserPoolClient
                "CognitoDomain": cognito_domain_url,  # Nhận từ AuthStack
                "CloudFrontUrl": f"https://{distribution.distribution_domain_name}",
                "BucketName": frontend_bucket.bucket_name,
                "ApiEndpoint": api_endpoint if api_endpoint else "https://placeholder.execute-api.ap-southeast-1.amazonaws.com/prod",
            }
        )
        
        # Deploy static assets từ dist folder
        bucket_deployment = s3_deployment.BucketDeployment(
            self, "DeployAdminUI",
            sources=[s3_deployment.Source.asset(frontend_asset_path)],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            memory_limit=1024,
            prune=False  # Don't delete config.json
        )
        
        # Ensure config is generated AFTER static files are deployed
        # This prevents BucketDeployment from overwriting the config
        config_generator_cr.node.add_dependency(bucket_deployment)

        # ==================== OUTPUTS ====================
        CfnOutput(
            self, "AdminDashboardURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="Admin Dashboard CloudFront URL"
        )

        CfnOutput(
            self, "CloudFrontDistributionDomain",
            value=distribution.distribution_domain_name,
            description="CloudFront distribution domain"
        )

        CfnOutput(
            self, "CognitoAppClientId",
            value=user_pool_client.ref,  # Dùng .ref cho CfnUserPoolClient
            description="Cognito App Client ID"
        )

        CfnOutput(
            self, "Region",
            value=self.region,
            description="AWS Region"
        )
