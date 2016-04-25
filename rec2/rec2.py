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
                    self.alarms['alarm_drag'],
                ]),

            self.autoscaling_client.describe_launch_configurations()['LaunchConfigurations']
        )

    def testing_startup(self, _vars, _alarms, _asg_details, _alarm_status, _launch_configurations):
        self.now = datetime.datetime.utcnow()
        self.set_vars(_vars, _alarms)
        self.process(_asg_details, _alarm_status, _launch_configurations, False)
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
        self.result['Action'] = 'MODIFY'
        self.result['Message'] = msg
        self.result['Logs'].append(
            "{}: {}".format(self.result['Action'], self.result['Message']))
        return self.result

    def process(self, _asg_details, _alarm_status, _launch_configurations, _execute=True):
        self.config = False

        self.result = {
            "Action": None,
            "Message": None,
            "Logs": []
        }

        self.asg_details = _asg_details
        self.alarm_status = _alarm_status
        self.launch_configurations = _launch_configurations
        self.execute = _execute

        self.info("Startup Time: {}".format(self.now.utcnow()))
        self.info("Configured instance sizes: Credit: {}, Standard: {}".format(
            self.vars['credit_instance_size'],self.vars['standard_instance_size']))

        self.info("Querying ASG: {}".format(self.vars['asg_identifier']))

        for config in self.launch_configurations:
            if config['LaunchConfigurationName'] == self.asg_details['LaunchConfigurationName']:
                self.info("Found active Launch Config: {}".format(self.asg_details['LaunchConfigurationName']))
                self.info("Config Instance Type: {}".format(config['InstanceType']))
                self.config = config
                break

        if not self.config:
            return self.abort('Config not found!')

        if config['InstanceType'] not in [self.vars['credit_instance_size'],self.vars['standard_instance_size']]:
            return self.abort("Current instance type not in allowed sizes! Current: {}, Credit: {}, Standard: {}".format(config['InstanceType'],self.vars['credit_instance_size'],self.vars['standard_instance_size']))

        if config['InstanceType'] == self.vars['credit_instance_size']:
            self.info("Checking if need to INCREASE")
            return self.check_increase()
        else:
            self.info("Checking if need to DECREASE")
            return self.check_decrease()


    def check_increase(self):
        self.info("Checking low credit alarm status")
        if self.alarm_status['MetricAlarms'][1]['StateValue'] == 'ALARM':
            self.info("Low Credit Alarm in ALARM!")
            self.scale('to_standard', self.vars['standard_instance_size'])

        if self.vars['drag_enabled']:
            self.info("Checking drag alarm status")
            if self.alarm_status['MetricAlarms'][2]['StateValue'] == 'ALARM':
                self.info("Credit Drag Alarm in ALARM!")
                self.scale('to_standard', self.vars['standard_instance_size'])
        else:
            self.info("Skipping drag alarm check: disabled")
        return self.abort("Nothing to do")

    def check_decrease(self):
        self.info("Checking low cpu alarm status")
        if self.alarm_status['MetricAlarms'][0]['StateValue'] == 'ALARM':
            self.info("Low CPU Alarm in ALARM!")
            self.scale('to_credit', self.vars['credit_instance_size'])
        return self.abort("Nothing to do")

    def assert_cooldown_expired(self, reason):
        last_rec2_change = False
        if reason == 'to_standard':
            return True
        self.info("Checking for last to_standard event")
        for tag in self.asg_details['Tags']:
            if tag['Key'] == 'rec2-modify-to-standard':
                last_rec2_change = tag['Value']
                break
        if last_rec2_change:
            # compare, if too soon return false
            return False
        return True

    def scale(self, reason, to_index=None):
        if not self.vars['enabled']:
            return self.abort("Launch Config Modification disabled")
        if not self.assert_cooldown_expired(reason):
            return self.abort("{} Cooldown threshold not reached".format(reason))
        new_class = self.vars[str(reason[3:]+"_instance")]
        self.info("Modifying Launch Config to {}".format(new_class))
        if self.execute:
            self.info("Executing scale command")
        else:
            self.info("Skipping scale command per passed in param")
        if reason == 'to_standard':
            if not self.add_action_tag():
                return self.abort("Action tag write error!")
        return self.success(self.vars['instance_sizes'][to_index])

    def lambda_apply_action(self):
        if self.result['Action'] == 'MODIFY':
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
