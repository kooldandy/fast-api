import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";

import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as rds from "aws-cdk-lib/aws-rds";
import * as ec2 from "aws-cdk-lib/aws-ec2";

export class ApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // 1. Define a FREE EC2 NAT Instance Provider (Eligible for 12-Month Free Tier)
    const natProvider = ec2.NatProvider.instanceV2({
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO
      ),
      defaultAllowedTraffic: ec2.NatTrafficDirection.OUTBOUND_ONLY,
    });

    // 2. Configure VPC to use the Free NAT Instance instead of a Managed NAT Gateway
    const vpc = new ec2.Vpc(this, "AppVpc", {
      maxAzs: 2,
      natGatewayProvider: natProvider, // Attaches the free EC2 NAT instance
      natGateways: 1, // Only 1 instance needed to save resource costs
      subnetConfiguration: [
        {
          name: "public",
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: "private",
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, // Allowed outbound traffic via NAT
          cidrMask: 24,
        },
      ],
    });

    const dbPassword = this.node.tryGetContext("dbPassword");

    // 3. RDS PostgreSQL Instance (t3.micro & 20GB Storage are Free Tier Eligible)
    const db = new rds.DatabaseInstance(this, "PostgresDb", {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_15,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO
      ),
      allocatedStorage: 20,
      maxAllocatedStorage: 20,
      multiAz: false,
      backupRetention: cdk.Duration.days(1),
      credentials: rds.Credentials.fromPassword(
        "postgres",
        cdk.SecretValue.unsafePlainText(dbPassword),
      ),
      databaseName: "appdb",
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, // Kept secure inside the private network
      },
      publiclyAccessible: false,
      deletionProtection: false,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      deleteAutomatedBackups: true,
    });

    // 4. FastAPI Lambda Function
    const fastApiLambda = new lambda.Function(this, "FastApiLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "main.handler",
      code: lambda.Code.fromAsset("../lambda"),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30),
      environment: {
        DB_HOST: db.dbInstanceEndpointAddress,
        DB_PORT: "5432",
        DB_ID: "postgres",
        DB_PASSWORD: dbPassword,
        DB_NAME: "appdb",
        CORS_ORIGINS: '["*"]',
        AUTH0_DOMAIN: this.node.tryGetContext("auth0Domain"),
        AUTH0_AUDIENCE: this.node.tryGetContext("auth0Audience"),
      },
      vpc,
      vpcSubnets: {
        // CRITICAL CHANGE: Routes Lambda out through the free NAT instance to reach Auth0
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, 
      },
    });

    // 5. Grant Lambda access to Database Port
    db.connections.allowDefaultPortFrom(fastApiLambda);

    // 6. API Gateway (RestApi has a generous 1 Million free requests per month tier)
    const api = new apigateway.LambdaRestApi(this, "FastApiGateway", {
      handler: fastApiLambda,
    });

    new cdk.CfnOutput(this, "ApiUrl", {
      value: api.url,
    });
  }
}