import os
from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_rds as rds,
    aws_sm as sm,
    aws_ec2 as ec2,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_wafv2 as waf,
    custom_resources as cr,
    aws_logs as logs,
    CfnOutput,Duration,BundlingOptions
)
from cdk_nag import NagSuppressions
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

        # Secrets Manager for Facebook
        
        fb_secret = sm.Secret(self, "FbSecret", generate_secret_string=sm.SecretStringGenerator(
            generate_string_key="verify_token",
        ))
        

        # Cognito User Pool with Facebook IdP
        user_pool = cognito.UserPool(
            self, "UserPool",
            user_pool_name="MessengerUserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            mfa=cognito.Mfa.OPTIONAL,
        )
        # Add Facebook as Identity Provider (need App ID and Secret from Facebook Developer Console)
        facebook_provider = cognito.UserPoolIdentityProviderFacebook(
            self, "FacebookProvider",
            user_pool=user_pool,
            client_id="YOUR_FACEBOOK_APP_ID",  # Replace with actual
            client_secret="YOUR_FACEBOOK_APP_SECRET",  # Replace with actual or use Secrets Manager
            attribute_mapping=cognito.ProviderAttribute.other("id", "facebook_id"),
        )
        user_pool_client = user_pool.add_client(
            "MessengerClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=["https://your-messenger-bot-callback-url"],  # Webview callback
            ),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.FACEBOOK],
        )

        # WAF for API Gateway
        waf_web_acl = waf.CfnWebACL(
            self, "MessengerWAF",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            scope="REGIONAL",
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="MessengerWAF",
                sampled_requests_enabled=True,
            ),
            rules=[
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=0,
                    override_action={"none": {}},
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS", name="AWSManagedRulesCommonRuleSet"
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True, cloud_watch_metrics_enabled=True, metric_name="CommonRules"
                    ),
                ),
                # Add more rules for bot-specific protection if needed
            ],
        )

        
        # tạo IAM Role cho Lambda function
        lambda_role = iam.Role(
            self, "webhookRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )
        #tạo role cho Lambda function để truy cập Cognito 
        lambda_role.attach_inline_policy(
            iam.Policy(
                self, "LambdaCognitoPolicy",
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "cognito-idp:AdminGetUser",
                            "cognito-idp:AdminCreateUser",
                            "cognito-idp:AdminInitiateAuth",
                            "cognito-idp:AdminRespondToAuthChallenge",
                            "cognito-idp:AdminUpdateUserAttributes",
                        ],
                        resources=[user_pool.user_pool_arn]
                    )
                ]
            )
        )
        # Lambda Functions
        
        webhook_receiver =  lambda_.Function(
            self, "WebhookFunction",
            function_name="Stack-WebhookFunction",
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
                        "pip install --platform manylinux2014_x86_64 --target /asset-output --implementation cp " +
                        "--python-version 3.12 --only-binary=:all: --upgrade -r requirements.txt && cp -au . " +
                        "/asset-output",
                    ]
                )
            ),
            role=lambda_role,
            timeout=Duration.seconds(60),# có thể set lâu hơn nếu cần
            memory_size=3072,
            environment={
            "FB_VERIFY_TOKEN": fb_secret.secret_value_from_json("verify_token").to_string(),
            "USER_POOL_ID": user_pool.user_pool_id,
            "CLIENT_ID": user_pool_client.user_pool_client_id,
        },
            log_retention=logs.RetentionDays.ONE_WEEK
        ) 


        fb_secret.grant_read(webhook_receiver)#phân quyền đọc secret
        session_table.grant_read_write(webhook_receiver)#phân quyền đọc cache

        
        # API Gateway for Messenger Webhook
        messenger_api = apigw.RestApi(
            self, "MessengerApi",
            rest_api_name="MessengerWebhookApi",
            deploy_options=apigw.StageOptions(
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
            ),
        )
        webhook_resource = messenger_api.root.add_resource("webhook")
        waf_assoc = waf.CfnWebACLAssociation(self, "WafAssoc", resource_arn=messenger_api.deployment_stage.stage_arn, web_acl_arn=waf_web_acl.attr_arn)
        # API Integrations
        webhook_resource.add_method("GET", apigw.LambdaIntegration(webhook_receiver))  # Verification
        webhook_resource.add_method("POST", apigw.LambdaIntegration(webhook_receiver))  # Messages

        
    

        # Outputs
        CfnOutput(self, "MessengerApiUrl", value=messenger_api.url)
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "ClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "DbEndpoint", value=self.db.db_instance_endpoint_address)
        CfnOutput(self, "GetApiKeyCommand",
                  value=f"aws apigateway get-api-key --api-key {api_key.key_id} --include-value --query 'value' --output text",
                  description="AWS CLI command to retrieve the API key value")
# Trong app.py (CDK app entry):
# app = cdk.App()
# UserMessengerBedrockStack(app, "UserMessengerBedrockStack")
# app.synth()
        api = apigw.LambdaRestApi(
            self,
            "Text2SqlApi",
            handler=function,
            proxy=False,
            integration_options=apigw.LambdaIntegrationOptions(proxy=False),
            api_key_source_type=apigw.ApiKeySourceType.HEADER,
            default_method_options=apigw.MethodOptions(
                api_key_required=True
            ),
            endpoint_types=[apigw.EndpointType.REGIONAL]
        )
        # Create a request validator
        request_validator = api.add_request_validator("RequestValidator",
                                                      validate_request_body=True,
                                                      validate_request_parameters=True
                                                      )
        query_model = api.add_model("JsonQueryModel", schema=apigw.JsonSchema(
            type=apigw.JsonSchemaType.OBJECT,
            properties={
                "query": apigw.JsonSchema(
                    type=apigw.JsonSchemaType.STRING
                ), "conversation_context": apigw.JsonSchema(
                    type=apigw.JsonSchemaType.ARRAY,
                    items=apigw.JsonSchema(
                        type=apigw.JsonSchemaType.OBJECT,
                        properties={
                            "role": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                            "content": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING)
                        }
                    )
                )
            },
            required=["query"]
        ))
        # Define the '/text-to-sql' resource with a POST method
        text_to_sql_resource = api.root.add_resource("text-to-sql")
        integration_responses = apigw.LambdaIntegration(function, proxy=False,
                                                        integration_responses=[
                                                            apigw.IntegrationResponse(status_code="200"),
                                                            apigw.IntegrationResponse(status_code="500")
                                                        ])
        text_to_sql_resource.add_method("POST",
                                        request_models={
                                            "application/json": query_model
                                        },
                                        integration=integration_responses,
                                        method_responses=[
                                            apigw.MethodResponse(status_code="200"),
                                            apigw.MethodResponse(status_code="500")
                                        ],
                                        request_validator=request_validator)
        # Add an API token
        api_key = api.add_api_key("Text2SqlApiKey")

        # Create a usage plan and associate the API key for the Gateway
        usage_plan = api.add_usage_plan("Text2SqlUsagePlan",
                                        throttle=apigw.ThrottleSettings(
                                            burst_limit=100,
                                            rate_limit=50
                                        ))
        usage_plan.add_api_stage(stage=api.deployment_stage)
        usage_plan.add_api_key(api_key)



        
        # Add CDK Nag suppressions for Python 3.12
        NagSuppressions.add_resource_suppressions(function, [
            {"id": "AwsSolutions-L1", "reason": "Python 3.12 is the stable version tested for this solution"}
        ])

        # DynamoDB for session storage (map PSID to Cognito tokens/user_id)
        session_table = dynamodb.Table(
            self, "SessionTable",
            partition_key=dynamodb.Attribute(name="psid", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )