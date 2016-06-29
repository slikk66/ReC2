#!/usr/bin/env python

from troposphere import Template, iam, Ref, Parameter, Output, GetAtt
from awacs.aws import Action, Allow, Policy, Principal, Statement

t = Template()

lambda_arn = t.add_parameter(Parameter(
    'LambdaArn',
    Type='String',
    Description='Lambda Arn'
))

role = t.add_resource(iam.Role(
    "eventrole",
    AssumeRolePolicyDocument=Policy(
        Statement=[
            Statement(
                Effect=Allow,
                Principal=Principal('Service', 'events.amazonaws.com'),
                Action=[Action('sts', 'AssumeRole')]
            )
        ]
    ),
    Path='/',
    Policies=[iam.Policy(
        'eventpolicy',
        PolicyName='eventpolicy',
        PolicyDocument=Policy(
            Statement=[
                Statement(
                    Effect=Allow,
                    Action=[
                        Action('logs', 'CreateLogGroup'),
                    ],
                    Resource=[Ref(lambda_arn)]
                )
            ]
        )
    )]
))

t.add_output([
    Output(
        'EventRole',
        Description='ReC2 Event Role ID',
        Value=Ref(role),
    ),
    Output(
        'EventRoleArn',
        Description='ReC2 Event Role ARN',
        Value=GetAtt(role.title, 'Arn')
    )
])

if __name__ == '__main__':
    print t.to_json()
