import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    BundlingOptions,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_rds as rds,
    aws_secretsmanager as sm,
    aws_ssm as ssm,
    aws_ec2 as ec2,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_logs as logs,
)
from constructs import Construct

class UserMessengerBedrockStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            db_instance: rds.IDatabaseInstance,
            vpc: ec2.IVpc,
            security_group: ec2.ISecurityGroup,
            readonly_secret: sm.ISecret,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "code"
        )

        # 1) DynamoDB session table for user sessions
        session_table = dynamodb.Table(
            self,
            "SessionTable",
            partition_key=dynamodb.Attribute(
                name="psid",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True,
        )

        # 2) Facebook App credentials from SSM Parameter Store
        fb_app_id_param = ssm.StringParameter.from_string_parameter_name(
            self,
            "FbAppIdParam",
            string_parameter_name="/meetassist/facebook/app_id"
        )
        fb_app_id = fb_app_id_param.string_value

        fb_app_secret_param = ssm.StringParameter.from_secure_string_parameter_attributes(
            self,
            "FbAppSecretParam",
            parameter_name="/meetassist/facebook/app_secret",
            version=1
        )
        fb_app_secret = fb_app_secret_param.string_value

        # Store Facebook Page Access Token in Secrets Manager
        fb_page_token_secret = sm.Secret(
            self,
            "FacebookPageToken",
            secret_name="meetassist/facebook/page_token",
            description="Facebook Page Access Token for Messenger Bot"
        )
        

        # 3) Cognito User Pool for authentication
        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="MessengerUserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            mfa=cognito.Mfa.OPTIONAL,
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
        ) # không login qua facebook
        # Cognito Domain for Hosted UI
        cognito_domain = user_pool.add_domain(
            "CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"meetassist-{self.account}-{self.region}"
            )
        )
        # Facebook Provider
        facebook_provider = cognito.UserPoolIdentityProviderFacebook(
            self, "FacebookProvider",
            user_pool=user_pool,
            client_id=fb_app_id,
            client_secret=fb_app_secret,
            scopes=["email", "public_profile"],
            attribute_mapping=cognito.AttributeMapping(
                email=cognito.ProviderAttribute.FACEBOOK_EMAIL,
                given_name=cognito.ProviderAttribute.FACEBOOK_NAME,
            )
        )
        # 4) API Gateway for Messenger webhook
        messenger_api = apigw.RestApi(
            self,
            "MessengerApi",
            rest_api_name="MessengerWebhookApi",
            description="API Gateway for Facebook Messenger webhook",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                metrics_enabled=True,
                throttling_rate_limit=10,
                throttling_burst_limit=5,
            ),
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )
        
        # Callback URLs
        api_callback_url = f"{messenger_api.url}callback"
        cognito_callback_url = (
            f"https://{cognito_domain.domain_name}.auth.{self.region}."
            f"amazoncognito.com/oauth2/idpresponse"
        )

        # User Pool Client with proper OAuth settings
        user_pool_client = user_pool.add_client(
            "MessengerClient",
            user_pool_client_name="MessengerBotClient",
            generate_secret=False,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True,
                ),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=[
                    api_callback_url,
                    cognito_callback_url,
                ],
                logout_urls=[f"{messenger_api.url}logout"],
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.FACEBOOK
            ],
        )
        # Ensure client is created after Facebook provider
        user_pool_client.node.add_dependency(facebook_provider)

        # 5) IAM Role for Lambda function
        lambda_role = iam.Role(
            self,
            "WebhookLambdaRole",
            role_name="MessengerWebhookLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        # Grant permissions
        fb_app_id_param.grant_read(lambda_role)
        fb_app_secret_param.grant_read(lambda_role)
        fb_page_token_secret.grant_read(lambda_role)
        session_table.grant_read_write_data(lambda_role)

        # Cognito permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cognito-idp:AdminGetUser",
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminInitiateAuth",
                    "cognito-idp:AdminRespondToAuthChallenge",
                    "cognito-idp:AdminUpdateUserAttributes",
                ],
                resources=[user_pool.user_pool_arn],
            )
        )

        # 6) Lambda function for webhook processing
        webhook_receiver = lambda_.Function(
            self,
            "WebhookFunction",
            function_name="MessengerWebhookHandler",
            description="Handles Facebook Messenger webhook events",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="webhook_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                asset_path,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    platform="linux/amd64",
                    command=[
                        "bash",
                        "-c",
                        "pip install --platform manylinux2014_x86_64 "
                        "--target /asset-output --implementation cp "
                        "--python-version 3.12 --only-binary=:all: "
                        "--upgrade -r requirements.txt && "
                        "cp -au . /asset-output",
                    ],
                ),
            ),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=1024,
            environment={
                "FB_APP_ID_PARAM": fb_app_id_param.parameter_name,
                "FB_APP_SECRET_PARAM": fb_app_secret_param.parameter_name,
                "FB_PAGE_TOKEN_SECRET_ARN": fb_page_token_secret.secret_arn,
                "USER_POOL_ID": user_pool.user_pool_id,
                "CLIENT_ID": user_pool_client.user_pool_client_id,
                "SESSION_TABLE_NAME": session_table.table_name,
                "RDS_HOST": db_instance.instance_endpoint.hostname,
                "RDS_PORT": db_instance.instance_endpoint.port,
                "DB_SECRET_ARN": readonly_secret.secret_arn,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        # 7) API Gateway resources and methods
        webhook_resource = messenger_api.root.add_resource("webhook")

        # GET method for webhook verification
        webhook_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                webhook_receiver,
                proxy=True,
            ),
        )

        # POST method for webhook events (non-proxy)
        post_integration = apigw.LambdaIntegration(
            webhook_receiver,
            proxy=False,
            request_templates={"application/json": "$input.json('$')"},
            integration_responses=[
                apigw.IntegrationResponse(
                    status_code="200",
                    response_templates={"application/json": ""},
                )
            ],
        )

        webhook_resource.add_method(
            "POST",
            post_integration,
            method_responses=[apigw.MethodResponse(status_code="200")],
            authorization_type=apigw.AuthorizationType.NONE,
        )

        # Callback endpoint for OAuth
        callback_resource = messenger_api.root.add_resource("callback")
        callback_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                webhook_receiver,
                proxy=True,
            ),
        )

        # Usage plan
        usage_plan = messenger_api.add_usage_plan(
            "WebhookUsagePlan",
            name="MessengerWebhookPlan",
            throttle=apigw.ThrottleSettings(
                rate_limit=10,
                burst_limit=20,
            ),
        )

        # Grant API Gateway permission to invoke Lambda
        webhook_receiver.add_permission(
            "ApiGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=messenger_api.arn_for_execute_api(),
        )


        # 8) Outputs
        CfnOutput(
            self,
            "WebhookUrl",
            value=f"{messenger_api.url}webhook",
            description="Messenger Webhook URL - Add this to Facebook App",
        )

        CfnOutput(
            self,
            "CallbackUrl",
            value=api_callback_url,
            description="OAuth Callback URL",
        )

        CfnOutput(
            self,
            "CognitoHostedUIUrl",
            value=(
                f"https://{cognito_domain.domain_name}.auth.{self.region}."
                f"amazoncognito.com/login?client_id="
                f"{user_pool_client.user_pool_client_id}&"
                f"response_type=code&redirect_uri={api_callback_url}"
            ),
            description="Cognito Hosted UI Login URL",
        )

        CfnOutput(
            self,
            "FacebookOAuthRedirectUri",
            value=cognito_callback_url,
            description="Add this to Facebook App Valid OAuth Redirect URIs",
        )

        CfnOutput(
            self,
            "UserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID",
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID",
        )

        CfnOutput(
            self,
            "SessionTableName",
            value=session_table.table_name,
            description="DynamoDB Session Table Name",
        )

        CfnOutput(
            self,
            "DbEndpoint",
            value=db_instance.instance_endpoint.hostname,
            description="RDS Database Endpoint",
        )
