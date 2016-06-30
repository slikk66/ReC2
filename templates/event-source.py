#!/usr/bin/env python

from troposphere import Template, Output, GetAtt, Parameter, Ref, events, awslambda

t = Template()

lambda_arn = t.add_parameter(Parameter(
    'LambdaArn',
    Type='String',
    Description='Lambda Arn'
))

rule = t.add_resource(
    events.Rule(
        "ReC2Rule",
        Targets=[events.Target(
            Arn=Ref(lambda_arn),
            Id="ReC2"
        )],
        ScheduleExpression="rate(5 minutes)"
    )
    )

permission = t.add_resource(
    awslambda.Permission(
        "ReC2Perm",
        FunctionName=Ref(lambda_arn),
        Action="lambda:InvokeFunction",
        Principal="events.amazonaws.com",
        SourceArn=GetAtt(rule, "Arn")
    )
    )

t.add_output([
    Output(
        'EventRule',
        Description='ReC2 Event Rule',
        Value=Ref(rule),
    ),
    Output(
        'EventPermission',
        Description='ReC2 Lambda Permission',
        Value=Ref(permission),
    )
])

if __name__ == '__main__':
    print t.to_json()
