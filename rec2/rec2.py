import boto3
import yaml
import datetime
import pytz
from dateutil import parser


class rec2:

    def lambda_startup(self):
        self.set_vars(
            yaml.load(file('vars.yaml')), yaml.load(file('alarms.yaml')))

        self.autoscaling_client = boto3.client('autoscaling',region_name=self.vars['region'])
        self.cloudwatch_client = boto3.client('cloudwatch',region_name=self.vars['region'])

        self.now = datetime.datetime.utcnow()


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

    def success(self):
        self.result['Action'] = 'MODIFY'
        self.result['Message'] = self.reason
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
            return self.scale('to_standard', self.vars['standard_instance_size'])

        if self.vars['drag_enabled']:
            self.info("Checking drag alarm status")
            if self.alarm_status['MetricAlarms'][2]['StateValue'] == 'ALARM':
                self.info("Credit Drag Alarm in ALARM!")
                return self.scale('to_standard', self.vars['standard_instance_size'])
        else:
            self.info("Skipping drag alarm check: disabled")
        return self.abort("Nothing to do")

    def check_decrease(self):
        self.info("Checking low cpu alarm status")
        if self.alarm_status['MetricAlarms'][0]['StateValue'] == 'ALARM':
            self.info("Low CPU Alarm in ALARM!")
            return self.scale('to_credit', self.vars['credit_instance_size'])
        return self.abort("Nothing to do")

    def assert_cooldown_expired(self):
        last_rec2_change = False
        if self.reason == 'to_standard':
            return True
        self.info("Checking for last to_standard modification event")
        for tag in self.asg_details['Tags']:
            if tag['Key'] == 'rec2-modify-to-standard':
                try:
                    last_rec2_change = parser.parse(tag['Value'])
                except:
                    self.info("Unable to parse value from tag! {}".format(tag['Value']))
                    pass
                break
        if last_rec2_change:
            delta_time = self.now.replace(tzinfo=pytz.utc) - last_rec2_change
            delta_time_calculated = divmod(
                delta_time.days * 86400 + delta_time.seconds, 60)
            self.info("Last finished modification {} Diff: (Min, Sec): {}".format(
                last_rec2_change, delta_time_calculated))
            if delta_time_calculated[0] < self.vars['cooldown']:
                self.info("Not enough time has passed since last modification ({})".format(
                    self.vars['cooldown']))
                return False
        return True

    def scale(self, reason, to_index=None):
        self.reason = reason
        if not self.vars['enabled']:
            return self.abort("Launch Config Modification disabled")
        if not self.assert_cooldown_expired():
            return self.abort("{} Cooldown threshold not reached".format(self.reason))
        self.new_class = self.vars[str(self.reason[3:]+"_instance_size")]
        self.info("Modifying Launch Config to {}".format(self.new_class))
        if self.execute:
            self.info("Executing scale command")
        else:
            self.info("Skipping scale command per passed in param")
        return self.success()

    def create_launch_configuration(self):
        worked = False
        to_copy = self.config.copy()
        del(to_copy['CreatedTime'])
        del(to_copy['LaunchConfigurationARN'])
        to_copy['InstanceType'] = self.new_class
        new_name = to_copy['LaunchConfigurationName']+"-ReC2-AutoCopy"
        to_copy['LaunchConfigurationName'] = new_name
        try:
            self.autoscaling_client.create_launch_configuration(**to_copy)
            self.pending_launch_configuration = new_name
        except:
            self.info("Launch Config creation failed!")
            pass
        return worked

    def launch_config_acquired(self):
        config_copy = self.config.copy()
        del(config_copy['CreatedTime'])
        del(config_copy['LaunchConfigurationARN'])
        del(config_copy['LaunchConfigurationName'])
        config_copy['InstanceType'] = self.new_class
        for launch_config in self.launch_configurations:
            if cmp(self.config,launch_config) == 0:
                continue
            test_config = launch_config.copy()
            print "test config:"
            print test_config
            del(test_config['CreatedTime'])
            del(test_config['LaunchConfigurationARN'])
            del(test_config['LaunchConfigurationName'])
            if cmp(config_copy,launch_config) == 0:
                self.pending_launch_configuration = launch_config['LaunchConfigurationName']
                return True
        if self.create_launch_configuration():
            return True
        return False

    def add_action_tag(self):
        worked = False
        try:
            self.autoscaling_client.create_or_update_tags(
                Tags=[{
                    "ResourceId": self.vars['asg_identifier'],
                    "ResourceType": "auto-scaling-group",
                    "Key": "rec2-modify-to-standard",
                    "Value": datetime.datetime.utcnow().strftime("%a %b %d %H:%M:%S UTC %Y"),
                    "PropagateAtLaunch": False
                }])
            worked = True
        except:
            self.info("Unable to add action tag")
            pass
        return worked

    def apply_launch_config(self):
        amz_res = self.autoscaling_client.update_auto_scaling_group(
            AutoScalingGroupName=self.vars['asg_identifier'],
            LaunchConfigurationName=self.pending_launch_configuration
            )
        self.info("AMZ response {}".format(amz_res))

    def lambda_apply_action(self):
        if self.result['Action'] == 'MODIFY':
            if self.reason == 'to_standard':
                if not self.add_action_tag():
                    return self.abort("Action tag write error!")
            if self.launch_config_acquired():
                self.apply_launch_config()
            return self.abort("System Error!")

    def print_logs(self):
        for log in self.result['Logs']:
            print(log)


def lambda_handler(context, event):
    r2 = rec2()
    r2.lambda_startup()
    r2.lambda_apply_action()
    r2.print_logs()
