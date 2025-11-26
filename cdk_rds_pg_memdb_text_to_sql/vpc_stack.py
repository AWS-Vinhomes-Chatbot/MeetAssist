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

import os

from aws_cdk import (
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_secretsmanager as sm,
    aws_logs as logs,
    aws_s3 as s3,       
    aws_glue as glue,
    Stack, CfnOutput, Duration, CfnParameter, BundlingOptions, RemovalPolicy
)
from cdk_nag import NagSuppressions
from constructs import Construct


class AppStack(Stack):
    vpc: ec2.IVpc
    subnet: ec2.ISubnet
    security_group: ec2.ISecurityGroup
    rds_instance: rds.IDatabaseInstance
    readonly_secret: sm.ISecret
    data_stored_bucket: s3.IBucket

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # CfnInput for S3 Bucket name
        s3_bucket_name = CfnParameter(
            self, "S3BucketName",
            type="String",
            default="your-bucket-name",
            description="Name of the S3 bucket to be used for the application"
        )



        vpc = ec2.Vpc(
            self, "AppVPC",
            max_azs=2, # Giới hạn 1 AZ để tiết kiệm chi phí cho ví dụ này
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PrivateIsolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24
                ),
            ]
        )

        


        # Output VPC và secret để dùng ở stack khác
        self.vpc = vpc
        # self.claude_secret = claude_secret

        self.vpc.add_flow_log("FlowLog")
        self.subnet = self.vpc.isolated_subnets[0]  # Sửa từ private_subnets sang isolated_subnets

        # Create a PostgreSQL DB Instance
        rds_instance = rds.DatabaseInstance(self, "AppDatabaseInstance",
                                            engine=rds.DatabaseInstanceEngine.postgres(
                                                version=rds.PostgresEngineVersion.VER_16),
                                            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3,
                                                                              ec2.InstanceSize.MICRO),  # Đổi từ SMALL sang MICRO
                                            vpc=self.vpc,
                                            storage_encrypted=True,
                                            allocated_storage=20,  # Limit storage 20GB
                                            vpc_subnets=ec2.SubnetSelection(
                                                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                                            ),
                                            )
        rds_instance.add_rotation_single_user()
        rds_instance.apply_removal_policy(RemovalPolicy.DESTROY)
        self.rds_instance = rds_instance

        NagSuppressions.add_resource_suppressions(self.rds_instance, [
            {"id": "AwsSolutions-RDS3", "reason": "Multi-AZ is not required for this example"}
        ])
        NagSuppressions.add_resource_suppressions(self.rds_instance, [
            {"id": "AwsSolutions-RDS10", "reason": "Deletion protection is not required for this example"}
        ])
        NagSuppressions.add_resource_suppressions(self.rds_instance, [
            {"id": "AwsSolutions-RDS11", "reason": "Default port is sufficient for this example"}
        ])

        # Create Secrets Manager secret for read-only user
        self.readonly_secret = sm.Secret(
            self,
            "ReadOnlyUserSecret",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"username": "readonly_user"}',
                generate_string_key="password",
            ),
        )
        NagSuppressions.add_resource_suppressions(self.readonly_secret, [
            {"id": "AwsSolutions-SMG4",
             "reason": "This read-only user is manually provisioned in the database."}
        ])
        
        database_sg = ec2.SecurityGroup(
            self, "DatabaseSecurityGroup",
            vpc=self.vpc,
            description="Security group for Lambda, RDS and VPC Endpoints"
        )
        
        # Rule 1: Cho phép traffic PostgreSQL từ chính security group này (Lambda -> RDS)
        database_sg.add_ingress_rule(
            database_sg,
            ec2.Port.tcp(5432),
            "Allow PostgreSQL traffic within the security group"
        )
        
        # Rule 2: Cho phép traffic HTTPS từ chính security group này (Lambda -> Secrets Manager/Bedrock Endpoints)
        database_sg.add_ingress_rule(
            database_sg,
            ec2.Port.tcp(443),
            "Allow HTTPS traffic for VPC Endpoints (Secrets Manager)"
        )
        
        self.security_group = database_sg
        self.rds_instance.connections.allow_default_port_from(database_sg)

        # S3 bucket để lưu CSV data - RETAIN để giữ lại khi destroy stack
        self.data_stored_bucket = s3.Bucket(
            self, "DataStoredBucket",
            bucket_name=f"meetassist-data-{Stack.of(self).account}-{Stack.of(self).region}",
            removal_policy=RemovalPolicy.RETAIN,  # Giữ lại bucket khi destroy
            auto_delete_objects=False,  # Không auto delete vì RETAIN
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True
        )




        
        # Interface VPC Endpoints với policy để restrict access (ví dụ: chỉ read/write cụ thể)
        # khởi tạo các endpoint cần thiết
        dynamo_endpoint = ec2.GatewayVpcEndpoint(
            self, "DynamoDBEndpoint",
            vpc=vpc,
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)],          
        )
        s3_endpoint = ec2.GatewayVpcEndpoint(  # Sử dụng Gateway cho S3 để tiết kiệm chi phí
            self, "S3Endpoint",
            vpc=vpc,
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)] 
        )


        # Thêm policy cho S3 Gateway Endpoint
        s3_endpoint.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            principals=[iam.AnyPrincipal()],
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=[
                self.data_stored_bucket.bucket_arn,
                self.data_stored_bucket.bucket_arn + "/*",
                f"arn:aws:s3:::{s3_bucket_name.value_as_string}", 
                f"arn:aws:s3:::{s3_bucket_name.value_as_string}/*"
            ]
        ))


        #thiết lập secrets manager endpoint
        secrets_endpoint = ec2.InterfaceVpcEndpoint(
            self, "SecretsManagerEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            private_dns_enabled=True,
            security_groups=[database_sg]  # Dùng chung SG với Lambda, rule port 443 đã được thêm ở trên
        )

        # Bedrock endpoint - COMMENT vì chưa sử dụng
        # bedrock_endpoint = ec2.InterfaceVpcEndpoint(
        #     self, "BedrockRuntimeEndpoint",
        #     vpc=vpc,
        #     service=ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
        #     subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        #     private_dns_enabled=True,
        #     security_groups=[database_sg]
        # )


        
       
        
        
        