# Copyright Notice:
# Copyright 2016-2021 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import configparser
import logging

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)

config_struct = {
    'Tool': ['verbose'],
    'Host': ['ip', 'username', 'password', 'description', 'forceauth', 'authtype', 'token'],
    'Validator': ['payload', 'logdir', 'oemcheck', 'debugging', 'schema_directory', 'uricheck']
}

config_options = [x for name in config_struct for x in config_struct[name]]


def convert_args_to_config(args):
    my_config = configparser.ConfigParser()
    for section in ['Tool', 'Host', 'Validator']:
        my_config.add_section(section)
        for option in config_struct[section]:
            if option not in ['password', 'token']:
                my_var = vars(args)[option]
                if isinstance(my_var, list):
                    my_var = ' '.join(my_var)
                    print(my_var)
                my_config.set(section, option, str(my_var) if my_var else '')
            else:
                my_config.set(section, option, '******')
    return my_config


def convert_config_to_args(args, config):
    my_config = configparser.ConfigParser()
    if isinstance(config, configparser.ConfigParser):
        my_config = config
    elif isinstance(config, str):
        with open(config, 'r') as f:
            my_config.read_file(f)
    elif isinstance(config, dict):
        my_config.read_dict(config)
    for section in config_struct:
        if section in my_config:
            for option in my_config[section]:
                if option.lower() not in config_options:
                    if option.lower() not in ['version', 'copyright']:
                        my_logger.error('Option {} not supported!'.format(option))
                elif my_config[section][option] not in ['', None]:
                    if option.lower() == 'payload':
                        setattr(args, option, my_config[section][option].split(' '))
                    else:
                        setattr(args, option, my_config[section][option])
    my_config_dict = config_parse_to_dict(my_config)
    import json
    print(json.dumps(my_config_dict, indent=4))
        

def config_parse_to_dict(config):
    my_dict = {}
    for section in config:
        my_dict[section] = {}
        for option in [x for x in config[section] if x not in ['version', 'copyright']]:
            my_dict[section][option] = {}
            my_dict[section][option]['value'] = config[section][option]
            my_dict[section][option]['description'] = "TBD"
    return my_dict