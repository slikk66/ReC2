import boto3
import yaml
import datetime


class rec2:

    def lambda_startup(self):
        self.autoscaling_client = boto3.client('autoscaling')
        self.cloudwatch_client = boto3.client('cloudwatch')

        self.now = datetime.datetime.utcnow()

        self.set_vars(
            yaml.load(file('vars.yaml')), yaml.load(file('alarms.yaml')))

        self.process(

            self.autoscaling_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[self.vars['asg_identifier']]
            )['AutoScalingGroups'][0],

            self.cloudwatch_client.describe_alarms(
                AlarmNames=[
                    self.alarms['alarm_low'],
                    self.alarms['alarm_credits'],
                ]),

            self.autoscaling_client.describe_launch_configurations()['LaunchConfigurations']
        )

    def testing_startup(self, _vars, _alarms, _details, _alarm_status, _launch_configurations):
        self.now = datetime.datetime.utcnow()
        self.set_vars(_vars, _alarms)
        self.process(_details, _alarm_status, _launch_configurations, False)
        self.print_logs()

    def set_vars(self, _vars, _alarms):
        self.vars = _vars
        self.alarms = _alarms

    def abort(self, msg):
        self.result['Action'] = 'NO_ACTION'
        self.result['Message'] = msg
        self.result['Logs'].append(
            "{}: {}".format(self.result['Action'], self.result['Message']))
        return self.result

    def info(self, msg):
        self.result['Logs'].append("{}: {}".format("INFO", msg))

    def success(self, msg):
        self.result['Action'] = 'RESIZE'
        self.result['Message'] = msg
        self.result['Logs'].append(
            "{}: {}".format(self.result['Action'], self.result['Message']))
        return self.result

    def process(self, _details, _alarm_status, _launch_configurations, _execute=True):
        self.config = False
        self.in_scheduled_up = False

        self.result = {
            "Action": None,
            "Message": None,
            "Logs": []
        }

        self.details = _details
        self.alarm_status = _alarm_status
        self.launch_configurations = _launch_configurations
        self.execute = _execute

        self.info("Startup Time: {}".format(self.now.utcnow()))
        self.info("Configured instance sizes: Credit: {}, Standard: {}".format(
            self.vars['credit_instance_size'],self.vars['standard_instance_size']))

        self.info("Querying ASG: {}".format(self.vars['asg_identifier']))

        for config in self.launch_configurations:
            if 'LaunchConfigurationName' not in config:
                return self.abort("No LaunchConfig found in ASG! {}".format(self.vars['asg_identifier']))
            if config['LaunchConfigurationName'] == self.details['LaunchConfigurationName']:
                self.info("Found active Launch Config: {}".format(self.details['LaunchConfigurationName']))
                self.info("Config Instance Type: {}".format(config['InstanceType']))
                self.info("Config Created: {}".format(config['CreatedTime']))
                self.config = config
                break

        if not self.config:
            self.abort('Config not found!')

        if config['InstanceType'] not in [self.vars['credit_instance_size'],self.vars['standard_instance_size']]:
            self.abort("Current instance type not in allowed sizes! Current: {}, Credit: {}, Standard: {}".format(config['InstanceType'],self.vars['credit_instance_size'],self.vars['standard_instance_size']))

        if config['InstanceType'] == self.vars['credit_instance_size']:
            self.info("Checking if need to INCREASE")
            return self.check_increase()
        else:
            self.info("Checking if need to DECREASE")
            return self.check_decrease()

    def check_increase(self):
        pass

    def check_decrease(self):
        pass

    def scale(self, reason, to_index=None):
        if not self.vars['enabled']:
            return self.abort("Resizing disabled")
        if 0 <= to_index < len(self.vars['instance_sizes']):
            if self.in_scheduled_up and to_index < self.vars['scheduled_index']:
                return self.abort("Already at bottom for size during scheduled scale up")
            self.info(
                "Scaling to {}".format(self.vars['instance_sizes'][to_index]))
            if not self.assert_cooldown_expired(reason):
                return self.abort("{} Cooldown threshold not reached".format(reason))
            if self.execute:
                self.info("Executing scale command")
            else:
                self.info("Skipping scale command per passed in param")
            return self.success(self.vars['instance_sizes'][to_index])
        else:
            return self.abort("Unable to scale - invalid to_index: {}".format(to_index))

    def lambda_apply_action(self):
        if self.result['Action'] == 'RESIZE':
            amz_res = self.autoscaling_client.modify_db_instance(
                DBInstanceIdentifier=self.vars['rds_identifier'],
                DBInstanceClass=self.result['Message'],
                ApplyImmediately=True)
            self.info("AMZ response {}".format(amz_res))

    def print_logs(self):
        for log in self.result['Logs']:
            print(log)


def lambda_handler(context, event):
    r2 = rec2()
    r2.lambda_startup()
    r2.lambda_apply_action()
    r2.print_logs()

lambda_handler({},{})
