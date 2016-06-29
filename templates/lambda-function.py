#!/usr/bin/env python
from troposphere import Template, Parameter, GetAtt, Join, Ref, Output, awslambda
t = Template()

lambda_role = t.add_parameter(Parameter(
    'LambdaRole',
    Type='String',
    Description='Lambda Role'
))

bucket_name = t.add_parameter(Parameter(
    'BucketName',
    Type='String',
    Description='Lambda Code Bucket'
))

time_token = t.add_parameter(Parameter(
    'TimeToken',
    Type='String',
    Description='Time Token for last upload'
))

lambda_function = t.add_resource(
    awslambda.Function(
        "rec2",
        Code=awslambda.Code(
            S3Bucket=Ref(bucket_name),
            S3Key=Join("", ["rec2-", Ref(time_token), ".zip"])
        ),
        Handler="rec2.lambda_handler",
        MemorySize=128,
        Role=Join('', ['arn:aws:iam::', Ref("AWS::AccountId"), ':role/', Ref(lambda_role)]),
        Runtime="python2.7",
        Timeout=30
    )
)

t.add_output([
    Output(
        'LambdaFunction',
        Description='ReC2 Lambda Function ID',
        Value=Ref(lambda_function),
    ),
    Output(
        'LambdaFunctionArn',
        Description='ReC2 Lambda Function ARN',
        Value=GetAtt(lambda_function.title, 'Arn')
    )
])

if __name__ == '__main__':
    print t.to_json()
